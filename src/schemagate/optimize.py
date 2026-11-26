# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Make a slow read faster, and prove the rewrite returns the same rows.

Three layers, each usable on its own:

* `compare(engine, original, candidate)` -- do the two queries return the
  same rows, and how long does each take? Rows are compared inside the
  database where it can (PostgreSQL: a row count plus an order-insensitive
  sum of row hashes, so a million-row result never leaves the server), and
  in Python otherwise, up to `MAX_VERIFY_ROWS`.
* `explain(engine, sql)` -- the plan, with real timings where the database
  gives them (`EXPLAIN (ANALYZE, BUFFERS)` on PostgreSQL).
* `optimize(engine, sql, provider)` -- ask a model for rewrites, keep only the
  ones `compare` proves identical, return the fastest. If nothing is both
  identical and faster, the original comes back unchanged.

Everything runs as a read: `check_read_only` on every statement, inside a
transaction that is always rolled back (and declared READ ONLY on
PostgreSQL), under a statement timeout. Only the query text changes -- no
index, no data, no setting outlives the call.

Two limits are worth knowing before you use the answer:

* "Identical" means identical **on the data as it is now**. A rewrite can
  match today and be wrong tomorrow -- the classic case is a constant taken
  from the data (``WHERE id < 6000033`` to split a scan). The model is told
  never to do that, and any literal a rewrite adds that the original did not
  have is reported in `new_literals` and keeps that rewrite from being chosen.
  Review a rewrite before it replaces production SQL.
* Every check runs the slow query again. `optimize` is bounded by
  ``time_budget`` seconds and a statement timeout; point it at a replica if
  the original is expensive.

Timing on PostgreSQL is the server's own ``Execution Time`` from
``EXPLAIN (ANALYZE, FORMAT JSON)`` -- the measure the Effi-SQL benchmark uses.
Other databases are timed on the wall clock, fetch included.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

from .answer import UnsafeSQL, _clear_time, _limit_time, check_read_only

__all__ = ["OptimizeError", "Fingerprint", "Comparison", "Attempt", "OptimizeResult",
           "compare", "explain", "fingerprint", "measure_ms", "new_literals", "optimize"]

#: Rows fetched into Python to compare results on databases without an
#: in-database hash. More than this and `compare` refuses to call two results
#: identical rather than guess.
MAX_VERIFY_ROWS = 200_000
#: Characters of plan text handed to the model.
MAX_PLAN_CHARS = 8000
#: Literals a rewrite may add without being flagged: LIMIT 1, ROW_NUMBER() = 1, COALESCE(x, 0).
_HARMLESS_LITERALS = frozenset({"0", "1"})


class OptimizeError(RuntimeError):
    """The comparison could not be made (too many rows to verify, a database error)."""


@dataclass
class Fingerprint:
    rows: int
    digest: str                      # order-insensitive
    ordered: Optional[str] = None    # order-sensitive, only when the query has a top-level ORDER BY


@dataclass
class Comparison:
    identical: bool
    reason: str
    original_rows: int
    candidate_rows: int
    original_ms: Optional[float] = None
    candidate_ms: Optional[float] = None
    speedup: Optional[float] = None
    timing: str = ""                 # "database" (server execution time) or "wall-clock"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Attempt:
    sql: str
    identical: Optional[bool] = None
    candidate_ms: Optional[float] = None
    speedup: Optional[float] = None
    new_literals: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class OptimizeResult:
    original_sql: str
    sql: str                         # the fastest identical query found; the original if none
    improved: bool
    original_ms: float
    optimized_ms: float
    speedup: float
    timing: str
    attempts: List[Attempt] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# Running reads safely
# --------------------------------------------------------------------------

def _dialect(engine) -> str:
    return getattr(getattr(engine, "dialect", None), "name", "") or ""


def _body(sql: str) -> str:
    """The statement without trailing semicolons, so it can sit inside a subquery."""
    return sql.strip().rstrip(";").strip()


@contextmanager
def _read_session(engine, timeout: Optional[float]) -> Iterator[Any]:
    """A connection inside a transaction that is always rolled back."""
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            if conn.dialect.name == "postgresql":
                conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            if timeout:
                _limit_time(conn, timeout)
            yield conn
        finally:
            try:
                trans.rollback()
            finally:
                if timeout:
                    _clear_time(conn)


def _execute(conn, sql: str):
    from sqlalchemy import text
    return conn.execute(text(sql))


def _has_top_level_order_by(sql: str) -> bool:
    """True when the outermost query ends in ORDER BY (outside brackets, strings and comments)."""
    s = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)
    s = re.sub(r"'(?:[^']|'')*'", "''", s)
    s = re.sub(r'"(?:[^"]|"")*"', '""', s)
    depth, flat = 0, []
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            flat.append(ch)
            continue
        flat.append(" ")
    return re.search(r"\border\s+by\b", "".join(flat), re.I) is not None


# --------------------------------------------------------------------------
# Same rows?
# --------------------------------------------------------------------------

def fingerprint(engine, sql: str, timeout: Optional[float] = None) -> Fingerprint:
    """Row count and digests of a read's result. Same digest, same rows."""
    sql = _body(check_read_only(sql, _dialect(engine)))
    ordered = _has_top_level_order_by(sql)
    with _read_session(engine, timeout) as conn:
        if conn.dialect.name == "postgresql":
            n, h = _execute(conn, "SELECT count(*), coalesce(sum(hashtextextended(t::text, 0)), 0) "
                                  f"FROM ({sql}) AS t").one()
            od = None
            if ordered:
                od = _execute(conn, "SELECT md5(coalesce(string_agg(x, chr(10)), '')) "
                                    f"FROM (SELECT t::text AS x FROM ({sql}) AS t) AS s").scalar()
            return Fingerprint(int(n), str(h), od)
        result = _execute(conn, sql)
        rows = result.fetchmany(MAX_VERIFY_ROWS + 1)
    if len(rows) > MAX_VERIFY_ROWS:
        raise OptimizeError(f"more than {MAX_VERIFY_ROWS:,} rows: too many to verify on this database")
    keyed = [hashlib.sha1(repr(tuple(r)).encode("utf-8")).hexdigest() for r in rows]
    digest = hashlib.sha1("\n".join(sorted(keyed)).encode()).hexdigest()
    od = hashlib.sha1("\n".join(keyed).encode()).hexdigest() if ordered else None
    return Fingerprint(len(rows), digest, od)


def _same(a: Fingerprint, b: Fingerprint, ordered: bool) -> Tuple[bool, str]:
    if a.rows != b.rows:
        return False, f"different row count ({a.rows} vs {b.rows})"
    if a.digest != b.digest:
        return False, "same row count, different rows"
    if ordered and a.ordered != b.ordered:
        return False, "same rows in a different order (the original has ORDER BY)"
    return True, "same rows"


# --------------------------------------------------------------------------
# How long?
# --------------------------------------------------------------------------

def _timing_kind(engine) -> str:
    return "database" if _dialect(engine) == "postgresql" else "wall-clock"


def _one_run_ms(conn, sql: str) -> float:
    if conn.dialect.name == "postgresql":
        plan = _execute(conn, f"EXPLAIN (ANALYZE, FORMAT JSON) {sql}").scalar()
        if isinstance(plan, str):
            plan = json.loads(plan)
        return float(plan[0]["Execution Time"])
    t0 = time.perf_counter()
    result = _execute(conn, sql)
    while result.fetchmany(10_000):
        pass
    return (time.perf_counter() - t0) * 1000.0


def measure_ms(engine, sql: str, runs: int = 2, timeout: Optional[float] = None) -> float:
    """Best of ``runs`` timed executions after one warm-up, in milliseconds."""
    sql = _body(check_read_only(sql, _dialect(engine)))
    with _read_session(engine, timeout) as conn:
        _one_run_ms(conn, sql)
        return min(_one_run_ms(conn, sql) for _ in range(max(1, runs)))


def explain(engine, sql: str, timeout: Optional[float] = None, analyze: bool = True) -> str:
    """The plan as text. On PostgreSQL with ``analyze``, real row counts and timings (the query runs)."""
    sql = _body(check_read_only(sql, _dialect(engine)))
    name = _dialect(engine)
    if name == "postgresql":
        stmt = f"EXPLAIN (ANALYZE, BUFFERS) {sql}" if analyze else f"EXPLAIN {sql}"
    elif name == "sqlite":
        stmt = f"EXPLAIN QUERY PLAN {sql}"
    elif name in ("mysql", "mariadb"):
        stmt = f"EXPLAIN ANALYZE {sql}" if analyze and name == "mysql" else f"EXPLAIN {sql}"
    else:
        stmt = f"EXPLAIN {sql}"
    with _read_session(engine, timeout) as conn:
        rows = _execute(conn, stmt).fetchall()
    return "\n".join(" | ".join(str(v) for v in r) for r in rows)[:MAX_PLAN_CHARS]


def compare(engine, original: str, candidate: str, runs: int = 2, timeout: Optional[float] = None,
            _original: Optional[Tuple[Fingerprint, float]] = None) -> Comparison:
    """Do ``original`` and ``candidate`` return the same rows, and how fast is each?

    Raises `UnsafeSQL` if either is not a single read. Timing only happens when
    the rows match: a wrong answer's speed is not worth the database's time.
    """
    name = _dialect(engine)
    original = _body(check_read_only(original, name))
    candidate = _body(check_read_only(candidate, name))
    if _original is None:
        fo = fingerprint(engine, original, timeout)
        o_ms = None
    else:
        fo, o_ms = _original
    fc = fingerprint(engine, candidate, timeout)
    same, why = _same(fo, fc, _has_top_level_order_by(original))
    kind = _timing_kind(engine)
    if not same:
        return Comparison(False, why, fo.rows, fc.rows, timing=kind)
    c_ms = measure_ms(engine, candidate, runs, timeout)
    if o_ms is None:
        o_ms = measure_ms(engine, original, runs, timeout)
    return Comparison(True, why, fo.rows, fc.rows, round(o_ms, 3), round(c_ms, 3),
                      round(o_ms / max(c_ms, 0.001), 2), kind)


# --------------------------------------------------------------------------
# Rewrites that only hold for today's data
# --------------------------------------------------------------------------

_LITERAL = re.compile(r"'(?:[^']|'')*'|(?<![\w.])\d+(?:\.\d+)?(?![\w.])")


def _literals(sql: str) -> set:
    s = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)
    s = re.sub(r'"(?:[^"]|"")*"', '""', s)               # quoted identifiers are names, not values
    return {m.group(0) for m in _LITERAL.finditer(s)}


def new_literals(original: str, candidate: str) -> List[str]:
    """Constants in ``candidate`` that ``original`` does not have (0 and 1 excepted).

    A rewrite that brings in a value it read from the data -- a key boundary,
    a row count, a date -- can return the same rows today and the wrong rows
    after the next insert. This is how such a rewrite is spotted.
    """
    return sorted(_literals(candidate) - _literals(original) - _HARMLESS_LITERALS)


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------

_SYSTEM = """You are a database performance expert. You rewrite one slow SQL query so it returns exactly the same result and runs faster.

Rules for every rewrite:
- Same rows, same columns in the same order with the same names, same NULL and duplicate behaviour.
- If the original has ORDER BY, keep the same ordering.
- Only the query text may change. No DDL, no index, no setting, no write, one statement.
- Never put in a constant you would have to look up in the data (a key boundary, a row count, a date, an id). The rewrite must stay correct when the data changes.
- Use only the tables and columns the original query uses.

Find where the time goes (repeated subqueries, correlated subqueries, scans that an index could avoid, sorting or aggregating far more rows than needed, OR chains, DISTINCT or UNION where they are not needed) and remove it. A rewrite that is only slightly faster is not worth much; look for the change that removes the dominant cost.

Reply with up to {n} candidate rewrites, best first, each in its own ```sql block. If you see no rewrite that is both correct and faster, reply with no SQL at all."""

_SQL_BLOCK = re.compile(r"```sql\s*(.*?)```", re.S | re.I)


def _blocks(text: str) -> List[str]:
    out = []
    for b in _SQL_BLOCK.findall(text or ""):
        b = _body(b)
        if b and b not in out:
            out.append(b)
    return out


def _prompt(dialect: str, sql: str, ms: float, kind: str, plan: str, context: str,
            attempts: Sequence[Attempt]) -> str:
    parts = [f"Database: {dialect or 'unknown'}",
             f"Original query ({ms:.1f} ms, {kind} time):\n```sql\n{sql}\n```"]
    if context:
        parts.append(f"Schema of the tables it reads:\n{context}")
    if plan:
        parts.append(f"Its plan:\n{plan}")
    if attempts:
        lines = []
        for i, a in enumerate(attempts, 1):
            if a.error:
                verdict = f"rejected: {a.error}"
            elif not a.identical:
                verdict = "rejected: different result"
            elif a.new_literals:
                verdict = f"rejected: adds data-dependent constants {', '.join(a.new_literals)}"
            else:
                verdict = f"same result, {a.candidate_ms:.1f} ms ({a.speedup}x)"
            lines.append(f"Attempt {i}: {verdict}\n```sql\n{a.sql}\n```")
        parts.append("Earlier attempts and how they did:\n\n" + "\n\n".join(lines) +
                     "\n\nDo better than the best of these, or reply with no SQL.")
    return "\n\n".join(parts)


def optimize(engine, sql: str, provider, *, rounds: int = 3, per_round: int = 2,
             runs: int = 2, timeout: Optional[float] = 120.0, time_budget: float = 600.0,
             min_speedup: float = 1.1, target_speedup: float = 10.0, context: str = "",
             check: Optional[Callable[[str], Optional[str]]] = None,
             max_tokens: int = 4000) -> OptimizeResult:
    """Ask ``provider`` for faster rewrites of ``sql``; keep the fastest that returns the same rows.

    ``check(candidate)`` is the caller's own gate -- return a reason string to
    refuse a candidate (the MCP server passes its table-scope check, so a
    rewrite can never read a table the caller may not see). ``context`` is
    schema text for the model (DDL, indexes). A candidate is chosen only if it
    is identical, adds no new constants, and is at least ``min_speedup`` times
    faster than the original. Stops after ``rounds`` model calls, at
    ``target_speedup``, or when ``time_budget`` seconds have passed.
    """
    started = time.monotonic()
    name = _dialect(engine)
    sql = _body(check_read_only(sql, name))
    if check is not None:
        refused = check(sql)
        if refused:
            raise UnsafeSQL(refused)
    kind = _timing_kind(engine)
    base_fp = fingerprint(engine, sql, timeout)
    base_ms = measure_ms(engine, sql, runs, timeout)
    warnings: List[str] = []
    try:
        plan = explain(engine, sql, timeout)
    except Exception as e:                                # noqa: BLE001 -- a plan helps, it is not required
        plan = ""
        warnings.append(f"no plan: {str(e).splitlines()[0][:200] if str(e) else type(e).__name__}")

    best_sql, best_ms = sql, base_ms
    attempts: List[Attempt] = []
    for _ in range(max(1, rounds)):
        if time.monotonic() - started > time_budget:
            warnings.append("stopped at the time budget")
            break
        try:
            reply = provider.complete(_SYSTEM.replace("{n}", str(per_round)),
                                      _prompt(name, sql, base_ms, kind, plan, context, attempts),
                                      max_tokens=max_tokens)
        except Exception as e:                            # noqa: BLE001 -- keep what was found so far
            warnings.append(f"model call failed: {str(e).splitlines()[0][:200] if str(e) else type(e).__name__}")
            break
        candidates = [c for c in _blocks(reply) if c != sql and c not in {a.sql for a in attempts}]
        if not candidates:
            break
        for cand in candidates[:per_round]:
            if time.monotonic() - started > time_budget:
                break
            a = Attempt(sql=cand, new_literals=new_literals(sql, cand))
            attempts.append(a)
            try:
                check_read_only(cand, name)
                refused = check(cand) if check is not None else None
                if refused:
                    a.error = f"refused: {refused}"
                    continue
                c = compare(engine, sql, cand, runs, timeout, _original=(base_fp, base_ms))
            except UnsafeSQL as e:
                a.error = f"refused: {e}"
                continue
            except Exception as e:                        # noqa: BLE001 -- a bad candidate is not fatal
                msg = str(getattr(e, "orig", e)).strip().splitlines()
                a.error = msg[0][:300] if msg else type(e).__name__
                continue
            a.identical, a.candidate_ms, a.speedup = c.identical, c.candidate_ms, c.speedup
            if (c.identical and not a.new_literals and c.candidate_ms is not None
                    and c.candidate_ms * min_speedup <= base_ms and c.candidate_ms < best_ms):
                best_sql, best_ms = cand, c.candidate_ms
        if best_ms > 0 and base_ms / best_ms >= target_speedup:
            break

    if any(a.identical and a.new_literals for a in attempts):
        warnings.append("a faster rewrite was set aside because it adds constants from the data; "
                        "it would only be correct for today's rows")
    improved = best_sql != sql
    return OptimizeResult(original_sql=sql, sql=best_sql, improved=improved,
                          original_ms=round(base_ms, 3), optimized_ms=round(best_ms, 3),
                          speedup=round(base_ms / max(best_ms, 0.001), 2) if improved else 1.0,
                          timing=kind, attempts=attempts, warnings=warnings)
