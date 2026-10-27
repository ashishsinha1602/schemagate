# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Turn a selection into an answer.

Selection is the part this library is careful about; answering is the part
everyone actually wants, and leaving it out made the pipeline look like it
stopped halfway. It genuinely does stop halfway -- a model has to write the
SQL -- so this module is the thin, explicit piece that closes the loop:

    question -> select() -> SQL from a model -> rows

Two things are deliberate here.

The SQL only ever sees the objects ``select()`` returned. That is what makes
the identity boundary mean something: a table the caller may not see is not
in the prompt, so the model cannot write SQL against it, and there is nothing
to filter out afterwards.

And the SQL is checked before it runs. A model asked for a query usually
writes a query, but "usually" is not a basis for handing generated text to a
database, so anything that is not a single read is refused rather than run.
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Sequence, Tuple

__all__ = ["UnsafeSQL", "check_read_only", "sql_prompt", "generate_sql", "run_sql"]

SYSTEM = (
    "You write SQL and nothing else. You are given the only tables you may "
    "use. Answer with one SELECT statement, no prose, no code fences, no "
    "trailing semicolon. Use only the tables and columns shown. "
    # Without this the model answered from one table and called the rest
    # insufficient, with the join tables sitting in the prompt. "One
    # statement" constrains statements, not complexity: a CTE, a window
    # function and a five-table join are all still one SELECT.
    "One statement does not mean one table: join as many of the tables shown "
    "as the question needs, and use CTEs (WITH), window functions, subqueries "
    "and aggregates freely. "
    # The DDL marks the edges the database does not enforce. They are still
    # the intended join, and saying so is what stopped "the contacts of
    # xmagnet" being refused with `contacts` and `tenants` both in the prompt.
    "The -- FK lines give you the joins. A line marked inferred was read from "
    "the column name rather than a declared constraint; it is still the "
    "intended join, so use it. "
    # Asked to rank suppliers by the stock they supply, against a schema whose
    # product table has no supplier column at all, the model wrote a confident
    # three-table query joining on a column it made up. The database caught
    # that one; a hallucinated column that happens to exist would not be
    # caught by anything, and would answer the wrong question quietly.
    "Never invent a column, a table or a join. Every column you name must "
    "appear above, under the table you attach it to. If the tables shown do "
    "not contain the link the question needs, that is not a question you can "
    "answer. "
    "If the tables genuinely cannot answer the question, reply with exactly: "
    "INSUFFICIENT"
)

#: Anything that is not a single read. Checked as whole words so a column
#: named `updated_at` or a table named `deleted_rows` is not mistaken for a
#: statement -- the first version of this rejected `SELECT updated_at ...`.
_FORBIDDEN = re.compile(
    r"\b(?:insert|update|delete|drop|alter|create|truncate|grant|revoke|"
    r"attach|detach|pragma|vacuum|merge|call|execute|commit|"
    r"rollback|savepoint)\b"
    # REPLACE is the one word in this list that is also an ordinary scalar
    # function, in every dialect: REPLACE(email, '@old', '@new'). Refusing it
    # stopped the model normalising a string inside a join or a GROUP BY --
    # exactly the sort of query someone wants complex SQL for. As a statement
    # it reads `REPLACE INTO t ...` or `REPLACE t ...`, where a table name
    # follows and never an open bracket, so the bracket separates the two.
    # (Those two forms are already refused a line earlier for not starting
    # with SELECT or WITH; this keeps the word barred in the middle as well.)
    r"|\breplace\b(?!\s*\()",
    re.I,
)


class UnsafeSQL(RuntimeError):
    """Generated SQL that would do something other than read."""


#: The first fenced block anywhere in the reply, not only at the very start.
_FENCE = re.compile(r"```[a-zA-Z]*[ \t]*\r?\n(.*?)```", re.S)

#: A statement keyword at the start of a line, used only to find where prose
#: ends and SQL begins in an unfenced reply.
_STATEMENT_START = re.compile(r"(?im)^[ \t]*(select|with)\b")

#: Where an explanation can start after the query: a semicolon, or a blank line.
_TAIL_BREAK = re.compile(r";|\n[ \t]*\n")

#: Words a SQL continuation line starts with. A tail that starts with one of these is still SQL.
_SQL_CONTINUES = re.compile(
    r"(?i)^\W*(select|with|from|where|join|left|right|inner|outer|full|cross|natural|group|order|"
    r"having|limit|offset|fetch|union|intersect|except|minus|and|or|not|on|using|as|case|when|then|"
    r"else|end|values|qualify|window|over|partition|top|distinct|into|lateral|pivot|unpivot)\b")


def _balanced(sql: str) -> bool:
    """Parentheses closed and quotes paired, so the text can be a whole statement."""
    bare = re.sub(r"'(?:[^']|'')*'", "''", sql)
    bare = re.sub(r'"[^"]*"', '""', bare)
    return bare.count("(") == bare.count(")") and "'" not in bare.replace("''", "") \
        and '"' not in bare.replace('""', "")


def _is_prose(tail: str) -> bool:
    """Does this read as an explanation rather than more SQL?

    A sentence: at least four words, mostly plain words, no SQL punctuation
    (`(`, `=`, `,` at the end of a line, `*`), not starting with a SQL keyword,
    and no statement anywhere in it. Deliberately strict: a CTE split by a
    blank line (`b AS (...)`) fails on the parenthesis and stays in the query.
    """
    first = tail.strip().splitlines()[0] if tail.strip() else ""
    # `=` quoted in backticks is prose about SQL, not SQL ("SQLite's `=` on TEXT is case-sensitive")
    first = re.sub(r"`[^`]*`", "x", first)
    words = first.split()
    # "Case sensitivity: ..." is a label, not CASE WHEN: one to three words then ': ' is never SQL
    # (a bind variable is ':name' with no space after the colon, so `CASE WHEN :x` stays SQL)
    if len(words) < 4 or (_SQL_CONTINUES.match(first)
                          and not re.match(r"^\W*[A-Za-z]+(?:\s+[A-Za-z]+){0,2}:\s", first)):
        return False
    if re.search(r"[(=*]|,\s*$|^\s*\)", first) or _STATEMENT_START.search(tail):
        return False
    plain = sum(1 for w in words if re.fullmatch(r"[A-Za-z][A-Za-z'’-]*[.,:;!?]?", w))
    return plain >= 0.7 * len(words)


def _cut_prose_tail(s: str) -> str:
    """Drop an explanation the model wrote after the query.

    Measured: in the Spider-ACL audit, 2 of 8,128 answered queries failed only
    because a sentence followed the SQL. Unlike dropping a prefix, dropping a
    tail cannot hide a write -- the cut text is discarded, not run -- but a tail
    that names a statement keyword or anything forbidden is left in place so
    `check_read_only` still rejects it loudly ("more than one statement",
    "contains DELETE") instead of the reply being quietly trimmed.
    """
    for m in _TAIL_BREAK.finditer(s):
        head, tail = s[:m.start()], s[m.end():]
        if not tail.strip() or not head.strip() or not _balanced(head):
            continue
        if _FORBIDDEN.search(tail):
            return s
        if _is_prose(tail):
            return head
    return s


def _strip_fences(sql: str) -> str:
    """Pull the SQL out of whatever the model wrapped around it.

    The old version only stripped a fence when the reply *began* with one, so
    two ordinary model habits broke it outright: a sentence of preamble before
    the block, and -- more often on a hard question -- a paragraph of
    second-guessing after it. Measured on eight complex questions against a
    live database, three failed here with "not a SELECT: 'I'" while the model
    had in fact written correct SQL a line further down.

    Safety is not relaxed. Whatever this returns still goes through
    `check_read_only` in full; this only decides which span of the reply is
    offered to it. The one place that could go wrong is skipping a prose
    prefix -- if the "prose" were really `DELETE FROM t;` then cutting to the
    SELECT after it would hide the write from the semicolon check. So the
    prefix is only dropped when it holds no statement separator and nothing
    forbidden, and otherwise the text is handed over untouched to be rejected.
    """
    s = sql.strip()

    fenced = _FENCE.search(s)
    if fenced:
        return fenced.group(1).strip().rstrip(";").strip()

    match = _STATEMENT_START.search(s)
    if match and match.start() > 0:
        prefix = s[:match.start()]
        if ";" not in prefix and not _FORBIDDEN.search(prefix):
            s = s[match.start():]

    if _STATEMENT_START.match(s):
        s = _cut_prose_tail(s)

    return s.strip().rstrip(";").strip()


def check_read_only(sql: str) -> str:
    """Return ``sql`` if it is a single read, otherwise raise ``UnsafeSQL``.

    Conservative on purpose. This runs on text a model produced, so the
    question is not "is this probably fine" but "is there any reading of it
    that writes". Comments are stripped first: `-- ` and `/* */` are the
    obvious place to hide a second statement from a naive scan.
    """
    s = _strip_fences(sql)
    if not s:
        raise UnsafeSQL("the model returned nothing")

    bare = re.sub(r"--[^\n]*", " ", s)
    bare = re.sub(r"/\*.*?\*/", " ", bare, flags=re.S)

    # A string literal can legitimately contain any word at all, so blank
    # literals out before looking for statement keywords.
    scan = re.sub(r"'(?:[^']|'')*'", "''", bare)

    if ";" in scan.strip().rstrip(";"):
        raise UnsafeSQL("more than one statement")
    if not re.match(r"^\s*(select|with)\b", scan, re.I):
        raise UnsafeSQL(f"not a SELECT: {s.split()[0][:20]!r}")
    bad = _FORBIDDEN.search(scan)
    if bad:
        raise UnsafeSQL(f"contains {bad.group(0).upper()}")
    return s


def _prompt_body(question: str, fragment: str,
                 examples: Sequence[Tuple[str, str]] = ()) -> str:
    """DDL, then any remembered (question, SQL) pairs, then the question.

    With no examples this is byte-for-byte the prompt from before memory
    existed, which is what keeps the bench gate honest: memory can only add
    text, never change what an un-taught catalogue sends.
    """
    from .learn import format_examples
    block = format_examples(examples)
    return "Tables you may use:\n\n%s\n%sQuestion: %s\n" % (
        fragment, (block + "\n") if block else "", question)


#: What a model gets wrong about a dialect, said once in the system prompt.
#:
#: Measured, not guessed: on UniQL's Oracle dialect (1,534 BIRD questions), Gemini 2.5 Flash's
#: first query failed 694 times, and two mistakes were 651 of them -- `FROM t AS x` (ORA-03048,
#: 551) and a bare reserved word as a column name, `DATE`, `NUMBER` (ORA-03050, 100). The rest of
#: each entry covers the next most common habits carried over from SQLite and MySQL.
DIALECT_RULES = {
    "oracle": (
        "Oracle rules: never write AS before a table alias (FROM account a, not FROM account AS a); "
        "AS is only for column aliases. A column named like a reserved word (DATE, NUMBER, LEVEL, SIZE, "
        "COMMENT, USER, UID, ACCESS, MODE, ROWS, START, TYPE) must be double-quoted in upper case, e.g. "
        "t.\"DATE\". Write every identifier exactly as the tables show it, quotes and case included. "
        "No LIMIT: use FETCH FIRST n ROWS ONLY. No boolean literals. Use NVL or COALESCE, not IFNULL; "
        "|| to concatenate; SUBSTR and INSTR; EXTRACT(YEAR FROM d) or TO_CHAR(d, 'YYYY') for dates; "
        "TO_DATE('2012-08-23', 'YYYY-MM-DD') for date literals. With DISTINCT, ORDER BY only selected "
        "expressions. GROUP BY repeats expressions, not column aliases."
    ),
}


def _flavour(dialect: str) -> str:
    """The dialect line of the system prompt, plus that dialect's rules if there are any."""
    if not dialect:
        return ""
    rules = DIALECT_RULES.get(dialect.strip().lower().split("+")[0], "")
    return f" Target dialect: {dialect}." + (f"\n{rules}" if rules else "")


def sql_prompt(question: str, fragment: str, dialect: str = "",
               examples: Sequence[Tuple[str, str]] = ()) -> str:
    """The prompt to paste into any chat window when there is no API key."""
    return f"{SYSTEM}{_flavour(dialect)}\n\n" + _prompt_body(question, fragment, examples)


#: How many times to ask before believing "these tables cannot answer this".
#:
#: The model is not deterministic and cannot be made so -- claude-sonnet-5
#: rejects a `temperature` parameter outright -- so the same prompt over the
#: same tables answers once and declines the next time. Measured against a
#: 1,245-object schema: twenty runs of four questions that all have answers,
#: 35% refused, and one of them produced three different queries in five runs.
#:
#: A refusal is evidence, not a verdict. Asking twice more costs a second on
#: the rare path and turns "it does not work" into "it works", which is the
#: difference between a tool someone keeps and one they close.
_ASK_ATTEMPTS = 3


#: Room for the reply, and for whatever the model does before the reply.
#:
#: 500 was sized for the SQL alone, and that is not what the budget pays for
#: any more. claude-sonnet-5 answers with a `thinking` block first: on a hard
#: nine-table question it spent all 500 tokens thinking, returned no text at
#: all, and `check_read_only` reported "the model returned nothing" -- which
#: reads as a broken model rather than a budget. The same question with 1,500
#: finished in 822. The failure is silent, it only hits the complicated
#: questions, and the tokens are charged either way, so the budget is set
#: where a long query plus its reasoning fits.
_SQL_TOKENS = 2000


def generate_sql(provider, question: str, fragment: str,
                 dialect: str = "", max_tokens: int = _SQL_TOKENS,
                 attempts: int = _ASK_ATTEMPTS,
                 examples: Sequence[Tuple[str, str]] = ()) -> str:
    """Ask a provider for one SELECT. Raises ``UnsafeSQL`` if it is not one.

    A model that answers INSUFFICIENT is asked again, up to `attempts` times.
    Nothing else is retried: a reply that is not a SELECT, or that contains a
    write, is raised at once. Those are not flakiness, and re-rolling them
    would be asking a model repeatedly until it gets past a safety check.
    """
    flavour = _flavour(dialect)
    prompt = _prompt_body(question, fragment, examples)
    tries = max(1, attempts)
    for _ in range(tries):
        reply = provider.complete(SYSTEM + flavour, prompt, max_tokens=max_tokens)
        if _strip_fences(reply).upper() != "INSUFFICIENT":
            return check_read_only(reply)
    raise UnsafeSQL(
        "the model said the selected tables cannot answer this, %d times. "
        "That is usually selection, not the model: try --top-k higher, or a "
        "hint." % tries
    )


def _limit_time(conn, seconds: float) -> None:
    """Best-effort statement time limit on this connection, per dialect. Unknown dialects: none."""
    name = conn.dialect.name
    ms = max(1, int(seconds * 1000))
    raw = conn.connection.driver_connection
    if name == "postgresql":
        conn.exec_driver_sql(f"SET statement_timeout = {ms}")
    elif name == "oracle":
        raw.call_timeout = ms
    elif name == "sqlite":
        import time
        stop = time.monotonic() + seconds
        raw.set_progress_handler(lambda: 1 if time.monotonic() > stop else 0, 10000)
    elif name in ("mysql", "mariadb"):
        conn.exec_driver_sql(f"SET SESSION MAX_EXECUTION_TIME = {ms}")


def _clear_time(conn) -> None:
    name = conn.dialect.name
    raw = conn.connection.driver_connection
    try:
        if name == "postgresql":
            conn.exec_driver_sql("SET statement_timeout = 0")
        elif name == "oracle":
            raw.call_timeout = 0
        elif name == "sqlite":
            raw.set_progress_handler(None, 0)
        elif name in ("mysql", "mariadb"):
            conn.exec_driver_sql("SET SESSION MAX_EXECUTION_TIME = 0")
    except Exception:                                     # noqa: BLE001 -- the pool resets it anyway
        pass


def run_sql(engine, sql: str, limit: int = 50, timeout: Optional[float] = None
            ) -> Tuple[List[str], List[Sequence[Any]]]:
    """Execute a checked read and return ``(column names, rows)``.

    ``check_read_only`` runs again here rather than trusting the caller: this
    is the function that hands text to a database, so it is the one that has
    to be sure. ``timeout`` (seconds) caps the statement where the dialect
    allows it; deep mode uses it so a slow exploring read cannot hold a
    question for minutes.
    """
    from sqlalchemy import text

    sql = check_read_only(sql)
    with engine.connect() as conn:
        if timeout:
            _limit_time(conn, timeout)
        try:
            result = conn.execute(text(sql))
            cols = list(result.keys())
            rows = result.fetchmany(limit)
        finally:
            if timeout:
                _clear_time(conn)
    return cols, [tuple(r) for r in rows]


def format_rows(cols: Sequence[str], rows: Sequence[Sequence[Any]],
                width: int = 28) -> str:
    """A small fixed-width table. No dependency, and readable in a terminal."""
    if not cols:
        return "(no columns)"
    def cell(v: Any) -> str:
        s = "" if v is None else str(v)
        return s if len(s) <= width else s[: width - 1] + "…"
    head = [cell(c) for c in cols]
    body = [[cell(v) for v in r] for r in rows]
    widths = [max(len(head[i]), *(len(r[i]) for r in body)) if body else len(head[i])
              for i in range(len(head))]
    out = ["  ".join(h.ljust(w) for h, w in zip(head, widths)).rstrip(),
           "  ".join("-" * w for w in widths)]
    out += ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in body]
    if not body:
        out.append("(no rows)")
    return "\n".join(out)
