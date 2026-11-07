# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""What the database's own query log says about the schema.

People's queries are the one place a warehouse's joins are written down when no
foreign key was ever declared: ``JOIN dim_customer c ON f.cust_key = c.cust_key``.
This reads the engine's statement store (or a file of SQL) and keeps three
things:

* **joins**: which table and column was joined to which, and how often;
* **together**: which tables were read in one statement;
* **filters**: the predicates a table is usually filtered by, as ``status = ?``.

``Catalog.learn_from_log`` turns a join whose far side is a primary key into an
inferred foreign key, so FK expansion in ``select()`` follows it, and keeps the
rest for ``Catalog.graph``.

**Nothing with a value in it is kept.** Every literal is replaced with ``?``
before a statement is looked at, no statement text is stored, and a predicate is
kept only as ``column OP ?``. The store is read with one bounded, read-only query.
Reading it needs a privilege on most engines (``pg_stat_statements``, MySQL's
``performance_schema``, Oracle's ``V$SQL``, SQL Server's ``dm_exec_query_stats``);
without it, ``LogUnavailable`` says what is missing and nothing else changes.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

#: One bounded, read-only query per engine, most-run statements first.
_SOURCES: Dict[str, Tuple[str, str]] = {
    "postgresql": (
        "SELECT query, calls FROM pg_stat_statements "
        "WHERE query ILIKE 'select%' OR query ILIKE 'with%' ORDER BY calls DESC LIMIT :n",
        "the pg_stat_statements extension"),
    "mysql": (
        "SELECT DIGEST_TEXT, COUNT_STAR FROM performance_schema.events_statements_summary_by_digest "
        "WHERE DIGEST_TEXT LIKE 'SELECT%' OR DIGEST_TEXT LIKE 'WITH%' ORDER BY COUNT_STAR DESC LIMIT :n",
        "performance_schema and the SELECT privilege on it"),
    "oracle": (
        "SELECT sql_fulltext, executions FROM (SELECT sql_fulltext, executions FROM v$sql "
        "WHERE command_type = 3 ORDER BY executions DESC) WHERE ROWNUM <= :n",
        "SELECT on V_$SQL"),
    "mssql": (
        "SELECT TOP (:n) st.text, qs.execution_count FROM sys.dm_exec_query_stats qs "
        "CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st ORDER BY qs.execution_count DESC",
        "the VIEW SERVER STATE permission"),
}
_SOURCES["mariadb"] = _SOURCES["mysql"]

#: Where a dialect's name differs between SQLAlchemy and sqlglot.
_SQLGLOT = {"postgresql": "postgres", "mssql": "tsql", "mariadb": "mysql"}

#: A predicate longer than this is not a filter anyone reads.
_MAX_FILTER = 100
#: Statements read from a store or a file, at most.
DEFAULT_LIMIT = 2000

Statement = Tuple[str, int]


class LogUnavailable(Exception):
    """The engine's statement store could not be read, and why."""


@dataclass
class LogFacts:
    """What the log said, with every value already gone."""
    read: int = 0                                   # statements looked at
    used: int = 0                                   # SELECTs naming at least one known table
    joins: Counter = field(default_factory=Counter)      # (qname, column, qname, column) -> statements
    together: Counter = field(default_factory=Counter)   # frozenset({qname, qname}) -> statements
    filters: Dict[str, Counter] = field(default_factory=dict)   # qname -> Counter[(column, "column = ?")]
    skipped: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.joins or self.together or self.filters)


@dataclass
class LogReport:
    facts: LogFacts
    keys_added: List[str] = field(default_factory=list)
    keys_skipped: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        f = self.facts
        out = [f"{f.read} statement(s) read, {f.used} SELECT(s) on known tables: "
               f"{len(f.joins)} join(s), {len(f.together)} table pair(s) read together, "
               f"{sum(len(c) for c in f.filters.values())} filter(s)",
               f"{len(self.keys_added)} join(s) added as inferred foreign keys"]
        out += [f"  added: {k}" for k in self.keys_added[:20]]
        out += [f"  skipped: {s}" for s in (self.keys_skipped + f.skipped)[:20]]
        return "\n".join(out)


# ------------------------------------------------------------------- reading

def read(source: Any, *, limit: int = DEFAULT_LIMIT) -> List[Statement]:
    """Statements as ``(sql, count)``: from a path (JSONL with ``sql`` and ``count``, or
    SQL text split on ``;``), an Engine (its statement store), or an iterable of SQL
    strings or ``(sql, count)`` pairs."""
    if isinstance(source, (str, os.PathLike)):
        return read_file(source, limit=limit)
    if hasattr(source, "connect") and hasattr(source, "dialect"):
        return read_engine(source, limit=limit)
    out: List[Statement] = []
    for item in source:
        if isinstance(item, str):
            out.append((item, 1))
        else:
            sql, n = item
            out.append((str(sql), int(n)))
        if len(out) >= limit:
            break
    return out


def read_file(path: Union[str, os.PathLike], *, limit: int = DEFAULT_LIMIT) -> List[Statement]:
    text = Path(path).read_text(encoding="utf-8")
    out: List[Statement] = []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines and all(ln.lstrip().startswith("{") for ln in lines):
        for ln in lines:
            row = json.loads(ln)
            sql = row.get("sql") or row.get("query") or row.get("statement") or ""
            if sql:
                out.append((str(sql), int(row.get("count") or row.get("calls") or 1)))
    else:
        out = [(s.strip(), 1) for s in text.split(";") if s.strip()]
    return out[:limit]


def read_engine(engine: Any, *, limit: int = DEFAULT_LIMIT) -> List[Statement]:
    """The engine's most-run statements. ``LogUnavailable`` when it cannot be read."""
    from sqlalchemy import text as _text
    name = engine.dialect.name
    if name not in _SOURCES:
        raise LogUnavailable(f"{name} has no statement store schemagate can read; pass a file of SQL instead")
    statement, needs = _SOURCES[name]
    try:
        with engine.connect() as conn:
            rows = conn.execute(_text(statement), {"n": int(limit)}).fetchall()
    except Exception as e:                           # noqa: BLE001 -- any driver or privilege error
        first = str(e).strip().splitlines()[0][:160] if str(e).strip() else type(e).__name__
        raise LogUnavailable(f"could not read {name}'s statement store (needs {needs}): {first}") from e
    out: List[Statement] = []
    for sql, n in rows:
        if hasattr(sql, "read"):                     # an Oracle LOB
            sql = sql.read()
        if sql:
            out.append((str(sql), int(n or 1)))
    return out


# -------------------------------------------------------------------- mining

def mine(cat, statements: Iterable[Statement], *, dialect: Optional[str] = None) -> LogFacts:
    """Joins, co-reads and filters over ``cat``'s objects. Needs sqlglot; without it
    the facts are empty and say so."""
    from .graph import _find_doc
    facts = LogFacts()
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:
        facts.skipped.append("sqlglot is not installed (pip install 'schemagate[graph]'), so no statement was read")
        return facts
    read_as = _SQLGLOT.get(dialect or "", dialect)
    query_types = getattr(exp, "Query", (exp.Select, exp.Union))
    every = cat.objects()

    def strip(node):
        return exp.Placeholder() if isinstance(node, exp.Literal) else node

    for sql, count in statements:
        facts.read += 1
        try:
            trees = [t for t in sqlglot.parse(sql, read=read_as) if t is not None]
        except Exception:                            # noqa: BLE001 -- unparsable: skip, never guess
            facts.skipped.append("a statement could not be parsed")
            continue
        for tree in trees:
            if not isinstance(tree, query_types):
                facts.skipped.append("a non-SELECT statement was skipped")
                continue
            tree = tree.transform(strip)             # every value gone before anything is looked at
            ctes = {(c.alias_or_name or "").lower() for c in tree.find_all(exp.CTE)}
            aliases: Dict[str, str] = {}
            for t in tree.find_all(exp.Table):
                if not t.name or (not t.db and t.name.lower() in ctes):
                    continue
                doc = _find_doc(every, ".".join(p for p in (t.db, t.name) if p), None)
                if doc is not None:
                    aliases[(t.alias_or_name or t.name).lower()] = doc.qname
            tables = sorted(set(aliases.values()))
            if not tables:
                continue
            facts.used += 1
            for i, a in enumerate(tables):
                for b in tables[i + 1:]:
                    facts.together[frozenset((a, b))] += count

            def owner(col) -> Optional[str]:
                if col.table:
                    return aliases.get(col.table.lower())
                return tables[0] if len(tables) == 1 else None

            for eq in tree.find_all(exp.EQ):
                left, right = eq.this, eq.expression
                if isinstance(left, exp.Column) and isinstance(right, exp.Column):
                    a, b = owner(left), owner(right)
                    if a and b and (a, left.name.lower()) != (b, right.name.lower()):
                        key = tuple(sorted([(a, left.name), (b, right.name)]))
                        facts.joins[(key[0][0], key[0][1], key[1][0], key[1][1])] += count
            where = tree.args.get("where") if isinstance(tree, exp.Select) else None
            if where is None:
                continue
            for pred in where.this.find_all(exp.Predicate):
                cols = list(pred.find_all(exp.Column))
                if len(cols) != 1:
                    continue
                q = owner(cols[0])
                if q is None:
                    continue
                bare = pred.copy()
                for c in bare.find_all(exp.Column):
                    c.set("table", None)
                rendered = " ".join(bare.sql(dialect=read_as).split())
                if len(rendered) <= _MAX_FILTER:
                    facts.filters.setdefault(q, Counter())[(cols[0].name, rendered)] += count
    return facts


def key_candidates(cat, facts: LogFacts, *, min_count: int = 2):
    """Joins worth declaring: ``(source qname, column, target qname, key column, count)``
    where the far side is that table's single-column primary key, plus the reasons the
    others were left out."""
    by_q = {d.qname: d for d in cat.objects()}
    out, skipped = [], []
    for (qa, ca, qb, cb), n in sorted(facts.joins.items(), key=lambda kv: (-kv[1], kv[0])):
        if n < min_count:
            skipped.append(f"{qa}.{ca} = {qb}.{cb}: seen {n} time(s), fewer than {min_count}")
            continue
        a, b = by_q.get(qa), by_q.get(qb)
        if a is None or b is None:
            continue

        def is_key(doc, col) -> bool:
            pk = [c.name for c in doc.columns if c.pk]
            return len(pk) == 1 and pk[0].lower() == col.lower()

        if is_key(b, cb) and not is_key(a, ca):
            out.append((qa, ca, qb, cb, n))
        elif is_key(a, ca) and not is_key(b, cb):
            out.append((qb, cb, qa, ca, n))
        else:
            skipped.append(f"{qa}.{ca} = {qb}.{cb}: neither side is a single-column primary key"
                           if not is_key(a, ca) else f"{qa}.{ca} = {qb}.{cb}: both sides are primary keys")
    return out, skipped
