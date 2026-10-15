# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Fuzz run_query's gate: no SQL it lets through may return a withheld value.

The oracle is execution, not a parser opinion, so it has no false positives.
A SQLite database holds a hidden table and a hidden column, each carrying a
sentinel value no visible row contains. SQL is assembled from tokens chosen by
the fuzzer -- hidden names in every quoting, case and qualification, joins,
CTEs, subqueries, UNIONs, comments. Whatever passes `check_read_only` and
`_check_scope` (exactly what run_query applies) is executed read-only, and if
a sentinel comes back, the gate let a withheld value out: that is a crash.

    python fuzz/fuzz_run_query_scope.py                 # atheris (Linux, CI)
    python fuzz/fuzz_run_query_scope.py --smoke 20000   # no atheris: random driver
"""
from __future__ import annotations

import os
import random
import sqlite3
import sys
import tempfile

try:                                          # coverage feedback when fuzzing for real
    import atheris
    _instrumented = atheris.instrument_imports
except ImportError:                           # --smoke and the pytest wrapper need no atheris
    import contextlib
    _instrumented = contextlib.nullcontext

with _instrumented():
    from schemagate import Catalog, Principal
    from schemagate.answer import UnsafeSQL, check_read_only
    from schemagate.mcp_server import _check_scope

SECRET_ROW = "S3CRET-ROW-7731"
SECRET_SALARY = 424242.42


def _database() -> str:
    path = os.path.join(tempfile.mkdtemp(prefix="sgfuzz-"), "fuzz.db")
    con = sqlite3.connect(path)
    con.executescript(f"""
        CREATE TABLE orders (id INTEGER PRIMARY KEY, customer TEXT, total REAL);
        CREATE TABLE staff (id INTEGER PRIMARY KEY, name TEXT, salary REAL);
        CREATE TABLE secret (id INTEGER PRIMARY KEY, note TEXT, salary REAL);
        CREATE TABLE offers (id INTEGER PRIMARY KEY, salary REAL);
        INSERT INTO orders VALUES (1, 'acme', 10.5), (2, 'zeta', 20.0);
        INSERT INTO staff VALUES (1, 'ann', {SECRET_SALARY}), (2, 'bob', {SECRET_SALARY});
        INSERT INTO secret VALUES (1, '{SECRET_ROW}', {SECRET_SALARY});
        INSERT INTO offers VALUES (1, 1000.0);
    """)
    con.commit()
    con.close()
    return path


DB = _database()
CAT = Catalog().bootstrap(f"sqlite:///{DB}")
CAT.restrict("secret", ["payroll"])
CAT.restrict_column("staff", "salary", ["payroll"])
WHO = Principal("fuzz:sales", roles=frozenset({"sales"}))

NAMES = ["secret", "SECRET", "Secret", '"secret"', '"SECRET"', "[secret]", "`secret`",
         "main.secret", '"main"."secret"', "main.[secret]", "temp.secret",
         "staff", "STAFF", '"staff"', "main.staff", "orders", "offers", "main.orders",
         "sqlite_master", "sqlite_schema", "pragma_table_info('secret')"]
COLS = ["salary", "SALARY", '"salary"', "[salary]", "staff.salary", "s.salary", "x.salary",
        "secret.note", "note", "*", "s.*", "x.*", "id", "name", "customer", "total",
        "o.id", "count(*)", "max(salary)", "group_concat(salary)", "lower(note)",
        "(select salary from staff)", "(select note from secret)"]
GLUE = ["SELECT", "FROM", "WHERE", "JOIN", "LEFT JOIN", "CROSS JOIN", "ON", "AS", "s", "x", "o",
        ",", "(", ")", "UNION", "UNION ALL", "WITH", "x AS", "1=1", "=", "AND", "OR", "IN",
        "EXISTS", "GROUP BY", "ORDER BY", "LIMIT 5", "/* c */", "-- c\n", "'secret'", "1",
        "NATURAL JOIN", "USING (id)", "VALUES (1)", "AS salary", "||", "IS NOT NULL"]
TEMPLATES = [
    "SELECT {c} FROM {t}",
    "SELECT {c} FROM {t} {a} JOIN {t2} ON 1=1",
    "SELECT {c} FROM {t} {a}, {t2}",
    "WITH x AS (SELECT {c} FROM {t}) SELECT * FROM x",
    "SELECT {c} FROM {t} UNION SELECT {c2} FROM {t2}",
    "SELECT * FROM (SELECT {c} FROM {t}) x",
    "SELECT {c} FROM {t} WHERE id IN (SELECT id FROM {t2})",
    "SELECT {c} FROM {t} NATURAL JOIN {t2}",
]


def _pick(seq, n):
    return seq[n % len(seq)]


def sql_from(ints) -> str:
    """Deterministic SQL from a stream of small ints (fuzzer bytes or a PRNG)."""
    it = iter(ints)

    def nxt():
        return next(it, 0)
    mode = nxt() % 3
    if mode < 2:
        s = _pick(TEMPLATES, nxt()).format(c=_pick(COLS, nxt()), c2=_pick(COLS, nxt()),
                                           t=_pick(NAMES, nxt()), t2=_pick(NAMES, nxt()),
                                           a=_pick(["", "s", "x", "o"], nxt()))
        for _ in range(nxt() % 4):            # splice a few extra tokens in
            words = s.split(" ")
            words.insert(nxt() % (len(words) + 1), _pick(GLUE + NAMES + COLS, nxt()))
            s = " ".join(words)
        return s
    return " ".join(_pick(GLUE + NAMES + COLS, nxt()) for _ in range(2 + nxt() % 14))


def check(sql: str) -> None:
    try:
        sql = check_read_only(sql)
    except UnsafeSQL:
        return
    except Exception:                         # noqa: BLE001 - the gate refusing is fine
        return
    if _check_scope(CAT, sql, WHO) is not None:
        return
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    steps = [0]

    def budget():
        steps[0] += 1
        return 1 if steps[0] > 2000 else 0     # abort runaway queries
    con.set_progress_handler(budget, 1000)
    try:
        rows = con.execute(sql).fetchmany(200)
    except sqlite3.Error:
        return
    finally:
        con.close()
    for r in rows:
        for v in r:
            if v == SECRET_ROW or v == SECRET_SALARY or (isinstance(v, str) and (SECRET_ROW in v or "424242" in v)):
                raise AssertionError(f"withheld value returned by allowed SQL: {sql!r} -> {r!r}")


def TestOneInput(data: bytes) -> None:       # noqa: N802 - atheris' name
    check(sql_from(data))


def smoke(n: int, seed: int = 1) -> int:
    rnd = random.Random(seed)
    allowed = 0
    for _ in range(n):
        sql = sql_from(rnd.randrange(256) for _ in range(64))
        check(sql)
        allowed += 1
    return allowed


def main() -> None:
    if "--smoke" in sys.argv:
        n = int(sys.argv[sys.argv.index("--smoke") + 1])
        smoke(n)
        print(f"smoke: {n} generated queries, no withheld value returned")
        return
    import atheris
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
