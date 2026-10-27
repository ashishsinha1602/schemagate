# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Answer a question in steps instead of in one shot.

`answer.generate_sql` asks once and runs what comes back. That is the right
default, and on most questions it is enough. It fails in three recognisable
ways, and each one is something a person would fix by looking before writing:

* a literal the question names is spelled differently in the data -- the
  question says "Germany", the column holds ``DE``; the query is valid, runs,
  and returns nothing;
* the database rejects the query (a misspelt column, a dialect habit) and the
  model never sees why;
* the tables it was shown are not quite the ones the question needs.

So the model works in steps here. Each reply is one of:

``EXPLORE``  a small read to look at real data first (distinct values, a date
             range, whether a join matches); it sees the first rows.
``TABLES``   a request for more tables on a topic; it gets the DDL of objects
             the caller may see and it has not been shown yet.
``FINAL``    the query that answers the question.

A query the database rejects is handed back with the database's own message,
and a final query that returns no rows is handed back once, so an empty
answer is a decision rather than an accident.

What does not change is the boundary. This module never touches a database
or a catalogue itself: the caller passes `run`, which must apply the same
read-only and scope checks as any other query (the MCP tool passes
`run_query`), and `more_tables`, which must only ever return objects the
caller may see. Every step's SQL goes through `run`; nothing is executed on
the model's say-so alone.

One thing *does* change, and it is the reason this is opt-in wherever it is
exposed: the rows an exploring query returns are sent to the model. The plain
answer path sends schema only.
"""
from __future__ import annotations

import contextvars as _contextvars
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from .answer import _flavour, _strip_fences

__all__ = ["DeepResult", "deep_answer", "adaptive_answer", "ExploreCache", "DEEP_SYSTEM"]

DEEP_SYSTEM = (
    "You answer a question about a database by working in steps. Each reply is exactly one step, "
    "in one of these forms and nothing else:\n"
    "EXPLORE: <one line: what you want to check>\n<one SELECT>\n"
    "TABLES: <a few words: what the tables shown are missing>\n"
    "FINAL: <one line: what the query returns>\n<one SELECT>\n"
    "INSUFFICIENT\n\n"
    "EXPLORE runs a small query and shows you its first rows. Use it when the question names a value "
    "(a status, a country, a product, a category) whose exact spelling or code you have not seen, "
    "when you are unsure how two tables join, or to see the format of a date or an id. Keep it small: "
    "a DISTINCT, a GROUP BY with a count, or a LIMIT. When the question is clear from the tables "
    "alone, go straight to FINAL. "
    "TABLES asks for more tables; you will be shown the ones you may use, if there are any. "
    "INSUFFICIENT means the tables you may use cannot answer the question at all.\n"
    "Before FINAL, if the query will filter on a text value taken from the question (a name, a "
    "region, a status) and you have not seen that column's values, EXPLORE them first: text "
    "comparisons are often case-sensitive and codes are often abbreviated. "
    "The FINAL query returns only what the question asks for: the values themselves, no labels, "
    "sentences or extra columns.\n"
    "Every query is one read-only SELECT (CTEs, joins, window functions and subqueries are fine), "
    "against only the tables shown, with no trailing semicolon and no code fences. Never invent a "
    "table, a column or a join: every column you name must appear above under the table you attach "
    "it to. If a query was rejected, read the database's message and fix that query."
)

#: How many model calls one question may take. Each EXPLORE, TABLES, repair and
#: FINAL is one; a straightforward question uses one.
DEFAULT_STEPS = 6

#: Corrections asked for when the database rejects a plain query, before anything else is tried.
#: Measured on Spider 2.0-lite: without them, step mode fell below a plain query with repairs
#: (39.3% vs 45.2%), because a rejected first or last query was given up on rather than fixed.
DEFAULT_REPAIRS = 2


#: Rows of an exploring query the model sees, and characters per cell.
PREVIEW_ROWS = 10
_CELL = 60

#: Room for the step plus the model's reasoning (see answer._SQL_TOKENS).
_STEP_TOKENS = 2000

#: True while deep mode runs an EXPLORE query -- set here, read by whatever `run` does (the cache,
#: a time limit). Row count cannot say which kind of read it is: a final answer asked for with
#: ``max_rows=5`` is as small as any exploration.
EXPLORING: "_contextvars.ContextVar[bool]" = _contextvars.ContextVar("schemagate_exploring", default=False)

_STEP = re.compile(r"^\s*\**\s*(EXPLORE|TABLES|FINAL)\s*\**\s*:\s*(.*)$", re.I)


@dataclass
class DeepResult:
    """What came out, and how it got there."""
    question: str
    sql: Optional[str] = None
    columns: List[str] = field(default_factory=list)
    rows: List[List[Any]] = field(default_factory=list)
    #: one entry per model call: kind, note, sql/topic, and what happened
    steps: List[Dict[str, Any]] = field(default_factory=list)
    #: set when no final answer was reached; the steps say why
    error: Optional[str] = None
    #: the final query had more rows than were returned
    truncated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        out = {"question": self.question, "sql": self.sql, "columns": self.columns,
               "rows": self.rows, "row_count": len(self.rows), "truncated": self.truncated,
               "steps": self.steps, "model_calls": len(self.steps)}
        if self.error:
            out["error"] = self.error
        return out


def _parse(reply: str):
    """(kind, note, body). A reply that is plain SQL is read as FINAL."""
    text = (reply or "").strip()
    if _strip_fences(text).upper() == "INSUFFICIENT":
        return "INSUFFICIENT", "", ""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _STEP.match(line)
        if m:
            kind, rest = m.group(1).upper(), m.group(2).strip()
            body = "\n".join(lines[i + 1:]).strip()
            # "FINAL: SELECT ..." on one line: the note is the SQL
            if kind != "TABLES" and not body and re.match(r"(?i)(select|with)\b", rest):
                return kind, "", rest
            return kind, rest, body
    if re.match(r"(?i)\s*(```[a-z]*\s*)?(select|with)\b", text):
        return "FINAL", "", text
    return "UNKNOWN", "", text


def _looks_empty(rows: Sequence[Sequence[Any]]) -> bool:
    """No rows, or one row of zeros and NULLs -- what COUNT or SUM over a filter that matched
    nothing returns. The same silent failure as no rows, so it is questioned the same way."""
    return not rows or (len(rows) == 1 and all(v is None or v == 0 for v in rows[0]))


def _cell(v: Any) -> str:
    s = "NULL" if v is None else str(v)
    return s if len(s) <= _CELL else s[:_CELL - 1] + "…"


def _preview(cols: Sequence[str], rows: Sequence[Sequence[Any]], cap: int, more: bool = False) -> str:
    shown = list(rows)[:cap]
    lines = [" | ".join(str(c) for c in cols)]
    lines += [" | ".join(_cell(v) for v in r) for r in shown]
    more = more or len(rows) > cap
    lines.append(f"({len(shown)} row{'s' if len(shown) != 1 else ''}{', more not shown' if more else ''})")
    return "\n".join(lines)


class ExploreCache:
    """Short-lived memory of exploring reads, so the same look at the data is not paid for twice.

    Deep mode asks the same small questions again and again -- what values does this status
    column hold, what does a date look like -- across questions and across users. Only exploring
    reads are kept (``EXPLORING`` is set; a final answer is never served from here), of at most
    ``max_limit`` rows, only successful ones, for ``ttl`` seconds.

    ``scope`` is part of every key and must say who is asking and which catalogue answered: the
    caller's identity and roles, and a catalogue version. Two callers with different grants can
    send the same SQL and be entitled to different rows -- a row filter, a column mask -- so an
    entry is never shared across scopes.
    """

    def __init__(self, ttl: float = 300.0, max_entries: int = 2000, max_limit: int = PREVIEW_ROWS):
        import threading
        self.ttl, self.max_entries, self.max_limit = ttl, max_entries, max_limit
        self._data: Dict[Any, Any] = {}
        self._lock = threading.Lock()
        self.hits = self.misses = 0

    def wrap(self, run: Callable[[str, int], Dict[str, Any]], scope: Any) -> Callable[[str, int], Dict[str, Any]]:
        import copy
        import time

        def cached(sql: str, limit: int) -> Dict[str, Any]:
            if not EXPLORING.get() or limit > self.max_limit:
                return run(sql, limit)
            key = (scope, " ".join(sql.split()), limit)
            now = time.monotonic()
            with self._lock:
                hit = self._data.get(key)
                if hit and now - hit[0] < self.ttl:
                    self.hits += 1
                    return copy.deepcopy(hit[1])
                self.misses += 1
            out = run(sql, limit)
            if "error" not in out:
                with self._lock:
                    if len(self._data) >= self.max_entries:
                        for k in sorted(self._data, key=lambda k: self._data[k][0])[:self.max_entries // 10 or 1]:
                            del self._data[k]
                    self._data[key] = (now, copy.deepcopy(out))
            return out
        return cached

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


def adaptive_answer(provider, question: str, ddl: str,
                    run: Callable[[str, int], Dict[str, Any]],
                    more_tables: Optional[Callable[[str], str]] = None,
                    dialect: str = "", max_steps: int = DEFAULT_STEPS,
                    max_rows: int = 50, preview_rows: int = PREVIEW_ROWS,
                    repairs: int = DEFAULT_REPAIRS) -> DeepResult:
    """One plain query first (corrected up to ``repairs`` times if the database rejects it); the
    step-by-step path only when that still looks wrong.

    Most questions are answered by the first query, and paying for exploration on all of them
    costs time for nothing. The plain query's result decides: it is accepted unless the database
    rejected it, the model declined, or it came back empty or all zero/NULL -- the cases deep mode
    exists for. Then deep mode starts, with that first attempt already in its trace.
    """
    res = DeepResult(question=question)
    tries = _plain_with_repair(provider, question, ddl, run, dialect, max_rows, repairs)
    last = tries[-1]
    if last.get("_rows") is not None and not _looks_empty(last["_rows"]):
        res.sql, res.columns = last["sql"], last.pop("_columns")
        rows = last.pop("_rows")
        res.rows, res.truncated = rows[:max_rows], last.pop("_truncated") or len(rows) > max_rows
        res.steps = [_public(t) for t in tries]
        return res
    deep = deep_answer(provider, question, ddl, run, more_tables, dialect=dialect,
                       max_steps=max(1, max_steps - len(tries)), max_rows=max_rows, preview_rows=preview_rows,
                       history=[_history_line(t) for t in tries], repairs=repairs)
    for s in deep.steps:
        s["step"] += len(tries)
    if deep.sql is None and last.get("_rows") is not None:
        # The steps found nothing better. The first query ran, and its empty or zero result
        # is an answer (a count can be 0); returning nothing instead would lose it.
        deep.sql, deep.columns = last["sql"], last.get("_columns") or []
        rows = last["_rows"]
        deep.rows, deep.truncated = rows[:max_rows], bool(last.get("_truncated")) or len(rows) > max_rows
        deep.error = None
    deep.steps = [_public(t) for t in tries] + deep.steps
    return deep


def _plain_with_repair(provider, question: str, schema: str, run, dialect: str, max_rows: int,
                       repairs: int, notes: str = "", kind: str = "plain") -> List[Dict[str, Any]]:
    """One plain query, and up to ``repairs`` corrections when the database rejects it.

    Returns the attempts in order. The last carries private ``_rows`` / ``_columns`` / ``_truncated``
    when it executed (``_rows`` is None when it did not)."""
    from .answer import UnsafeSQL, generate_sql

    attempts: List[Dict[str, Any]] = []
    asked = question + (notes and "\n\n" + notes)
    for i in range(max(0, repairs) + 1):
        a: Dict[str, Any] = {"step": len(attempts) + 1, "kind": kind if i == 0 else "repair", "_rows": None}
        attempts.append(a)
        try:
            sql = generate_sql(provider, asked, schema, dialect, attempts=1)
        except UnsafeSQL as e:
            a["outcome"] = f"declined or refused: {e}"
            return attempts
        out = run(sql, max_rows)
        a["sql"] = out.get("sql") or sql
        if "error" not in out:
            rows = [list(r) for r in out.get("rows") or []]
            a.update(_rows=rows, _columns=list(out.get("columns") or []), _truncated=bool(out.get("truncated")))
            a["outcome"] = (f"{len(rows)} row(s)" if not _looks_empty(rows) else
                            "returned no rows" if not rows else "returned only zero or NULL")
            return attempts
        a["outcome"] = out["error"]
        asked = (question + (notes and "\n\n" + notes) +
                 f"\n\nThis query was rejected by the database:\n{a['sql']}\nError: {out['error']}\n"
                 "Write a corrected query for the same question.")
    return attempts


def _public(step: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in step.items() if not k.startswith("_")}


def _history_line(step: Dict[str, Any]) -> str:
    label = "An earlier attempt" if step.get("kind") == "repair" else "A first attempt"
    if step.get("sql"):
        return f"{label}:\n{step['sql']}\n-> {step.get('outcome', '')}"
    return f"{label} produced no query: {step.get('outcome', '')}"


def deep_answer(provider, question: str, ddl: str,
                run: Callable[[str, int], Dict[str, Any]],
                more_tables: Optional[Callable[[str], str]] = None,
                dialect: str = "", max_steps: int = DEFAULT_STEPS,
                max_rows: int = 50, preview_rows: int = PREVIEW_ROWS,
                history: Sequence[str] = (), repairs: int = DEFAULT_REPAIRS) -> DeepResult:
    """Work a question out in steps, and return the answer with its trace.

    ``ddl`` is the schema the caller may use, already scoped. ``run(sql, limit)``
    executes one query and returns ``{"columns", "rows", "truncated"}`` with at
    most ``limit`` rows, or ``{"error"}``; it
    is where the read-only and scope checks live, and every query goes through
    it. ``more_tables(topic)`` returns DDL for objects not shown yet (``""``
    when there are none); without it a TABLES step is answered "none".
    """
    res = DeepResult(question=question)
    system = DEEP_SYSTEM + _flavour(dialect)
    schema = ddl.strip()
    log: List[str] = list(history)
    asked_empty = asked_insufficient = False
    steps = max(1, int(max_steps))

    for left in range(steps, 0, -1):
        prompt = (f"Tables you may use:\n\n{schema}\n\nQuestion: {question}\n\n"
                  + ("Steps so far:\n\n" + "\n\n".join(log) + "\n\n" if log else "")
                  + f"Model calls left, including this one: {left}. "
                  + ("This is the last one: reply with FINAL or INSUFFICIENT." if left == 1
                     else "Reply with the next step."))
        reply = provider.complete(system, prompt, max_tokens=_STEP_TOKENS)
        kind, note, body = _parse(reply)
        step: Dict[str, Any] = {"step": len(res.steps) + 1, "kind": kind.lower()}
        if note:
            step["note"] = note
        res.steps.append(step)

        if kind == "INSUFFICIENT":
            # Questioned once, like an empty FINAL: on Oracle 9 of the 15 questions a plain
            # query got right were lost here, the model giving up on tables that did answer
            # them. A second INSUFFICIENT stands; the tables shown are the same either way.
            if not asked_insufficient and left > 1:
                asked_insufficient = True
                step["outcome"] = "said the tables cannot answer this; asked to check"
                log.append("INSUFFICIENT\n-> Check again before giving up. Name the part of the "
                           "question that no table or column above covers. If every part is covered "
                           "by some column above, write the FINAL query instead.")
                continue
            step["outcome"] = "the model said the tables it may use cannot answer this"
            res.error = step["outcome"]
            return res

        if kind == "UNKNOWN":
            step["outcome"] = "reply was not a step"
            log.append("Your reply was not one of EXPLORE, TABLES, FINAL or INSUFFICIENT. "
                       "Reply with exactly one step.")
            continue

        if kind == "TABLES":
            step["topic"] = note or body
            extra = (more_tables(step["topic"]) if more_tables else "").strip()
            if extra:
                schema += "\n\n" + extra
                step["outcome"] = "added tables"
                log.append(f"TABLES: {step['topic']}\n-> more tables were added above.")
            else:
                step["outcome"] = "no further tables available"
                log.append(f"TABLES: {step['topic']}\n-> there are no further tables you may use. "
                           "Answer from the tables shown, or reply INSUFFICIENT.")
            continue

        sql = body
        step["sql"] = sql
        token = EXPLORING.set(kind == "EXPLORE")
        try:
            out = run(sql, preview_rows if kind == "EXPLORE" else max_rows)
        finally:
            EXPLORING.reset(token)
        if "error" in out:
            step["outcome"] = out["error"]
            # the checked SQL when the runner returned it, so the trace shows what was judged
            step["sql"] = out.get("sql") or sql
            log.append(f"{kind}: {note}\n{sql}\n-> rejected: {out['error']}")
            continue

        cols, rows = list(out.get("columns") or []), [list(r) for r in out.get("rows") or []]
        more = bool(out.get("truncated"))
        step["sql"] = out.get("sql") or sql
        if kind == "EXPLORE":
            step["outcome"] = f"{min(len(rows), preview_rows)} row(s) seen"
            log.append(f"EXPLORE: {note}\n{step['sql']}\n-> {_preview(cols, rows, preview_rows, more)}")
            continue

        # FINAL
        if _looks_empty(rows) and not asked_empty and left > 1:
            asked_empty = True
            what = "no rows" if not rows else "only zero or NULL"
            step["outcome"] = f"returned {what}; asked to confirm"
            log.append(f"FINAL: {note}\n{step['sql']}\n-> returned {what}. If that is the right "
                       "answer, reply FINAL with the same query. If a filter value may not match "
                       "the data, EXPLORE the column's actual values first.")
            continue
        res.sql, res.columns = step["sql"], cols
        res.truncated = more or len(rows) > max_rows
        res.rows = rows[:max_rows]
        step["outcome"] = f"{len(res.rows)} row(s)"
        return res

    # Out of steps without a final query. Rather than return nothing -- which loses questions a
    # single plain query would have answered -- ask once for the query itself, with what the
    # exploring found as notes. Measured on Spider 2.0: 24 to 33 of 135 tasks ended here.
    return _last_chance(provider, question, schema, log, run, res, dialect=dialect, max_rows=max_rows,
                        reason=f"no final query after {steps} model calls", repairs=repairs)


def _last_chance(provider, question: str, schema: str, log: List[str], run, res: DeepResult, *,
                 dialect: str, max_rows: int, reason: str, repairs: int = DEFAULT_REPAIRS) -> DeepResult:
    notes = "\n\n".join(log[-6:])
    notes = "What was learned by looking at the data (use it):\n" + notes if notes else ""
    tries = _plain_with_repair(provider, question, schema, run, dialect, max_rows, repairs,
                               notes=notes, kind="final")
    for t in tries:
        t["step"] = len(res.steps) + 1
        if t["kind"] == "final":
            t["note"] = "out of steps: one plain query"
        res.steps.append(_public(t))
    last = tries[-1]
    if last.get("_rows") is None:
        res.error = reason
        return res
    rows = last["_rows"]
    res.sql, res.columns = last["sql"], last["_columns"]
    res.rows, res.truncated = rows[:max_rows], last["_truncated"] or len(rows) > max_rows
    return res
