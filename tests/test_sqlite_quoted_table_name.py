# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""run_query and a table named with a single-quoted string.

SQLite reads a single-quoted string as an identifier where only an identifier
fits, so `FROM 'payroll'` reads the table payroll. The scope check emptied
every string literal before reading table names, so such a reference named
nothing and the hidden table was read without a check. Found by the fuzz
harness (fuzz/fuzz_run_query_scope.py) within two minutes:

    SELECT "salary" FROM orders NATURAL JOIN 'secret' orders

Each attack below is checked twice: the gate must refuse it, and SQLite
must really execute it, so the test fails if it ever stops being an attack.
"""
import sqlite3

import pytest

from schemagate import Catalog, Principal
from schemagate.mcp_server import _check_scope

SALES = Principal("okta:sales", roles=frozenset({"sales"}))
PAYROLL = Principal("okta:pay", roles=frozenset({"payroll"}))


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("q") / "q.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE orders (id INTEGER PRIMARY KEY, total REAL);
        CREATE TABLE secret (id INTEGER PRIMARY KEY, salary REAL);
        INSERT INTO orders VALUES (1, 10.0);
        INSERT INTO secret VALUES (1, 424242.0);
    """)
    con.commit()
    con.close()
    cat = Catalog().bootstrap(f"sqlite:///{path}")
    cat.restrict("secret", ["payroll"])
    return path, cat


ATTACKS = [
    """SELECT "salary" FROM orders NATURAL JOIN 'secret' orders""",
    "SELECT * FROM 'secret'",
    "SELECT salary FROM 'secret'",
    "SELECT * FROM main.'secret'",
    "SELECT * FROM 'main'.'secret'",
    "SELECT * FROM 'main'.secret",
    "SELECT s.salary FROM orders o, 'secret' s",
    "SELECT s.salary FROM orders o JOIN 'secret' s ON 1=1",
    "SELECT (SELECT salary FROM 'secret') FROM orders",
    "WITH x AS (SELECT * FROM 'secret') SELECT * FROM x",
    "SELECT * FROM 'SECRET'",
]


@pytest.mark.parametrize("sql", ATTACKS)
def test_a_single_quoted_hidden_table_is_refused(db, sql):
    path, cat = db
    rows = sqlite3.connect(path).execute(sql).fetchall()
    assert any(424242.0 in r for r in rows), "no longer an attack on this SQLite"
    assert _check_scope(cat, sql, SALES) is not None


@pytest.mark.parametrize("sql", ATTACKS)
def test_the_role_that_may_read_it_still_can(db, sql):
    _, cat = db
    assert _check_scope(cat, sql, PAYROLL) is None


@pytest.mark.parametrize("sql", [
    "SELECT * FROM orders WHERE total > 1 AND 'secret' = 'secret'",
    "SELECT 'from secret' AS label, total FROM orders",
    "SELECT * FROM orders WHERE id IN (1, 2) AND 'x' IN ('a', 'secret')",
])
def test_a_string_that_only_mentions_the_name_is_not_a_table(db, sql):
    _, cat = db
    assert _check_scope(cat, sql, SALES) is None
