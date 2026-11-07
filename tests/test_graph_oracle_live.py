"""The CREATE PROPERTY GRAPH schemagate writes, run on a real Oracle and queried through.

    SCHEMAGATE_ORACLE_URL=oracle+oracledb://app:pw@host:1521/?service_name=FREEPDB1 \\
    pytest tests/test_graph_oracle_live.py

The user needs CREATE TABLE, CREATE VIEW and CREATE PROPERTY GRAPH. Everything is named
SGPG_* and dropped after.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from schemagate import Catalog, Principal

URL = os.environ.get("SCHEMAGATE_ORACLE_URL")
pytestmark = [pytest.mark.live,
              pytest.mark.skipif(not URL, reason="set SCHEMAGATE_ORACLE_URL to run")]

ANALYST = Principal("okta:a", roles=frozenset({"analyst"}))
HR = Principal("okta:h", roles=frozenset({"hr"}))

SETUP = [
    "CREATE TABLE sgpg_customer (id NUMBER PRIMARY KEY, region VARCHAR2(50), secret_note VARCHAR2(50))",
    # No declared foreign key: only the view says how these join.
    "CREATE TABLE sgpg_invoice (inv_id NUMBER PRIMARY KEY, cust_ref NUMBER, status VARCHAR2(50))",
    "CREATE TABLE sgpg_employee (id NUMBER PRIMARY KEY, manager_id NUMBER REFERENCES sgpg_employee(id), salary NUMBER)",
    'CREATE TABLE "SGPG_ORDER" (order_id NUMBER PRIMARY KEY, customer_id NUMBER REFERENCES sgpg_customer(id))',
    "CREATE TABLE sgpg_tag (tag_id NUMBER PRIMARY KEY, label VARCHAR2(50))",
    'CREATE TABLE sgpg_order_tag (order_id NUMBER REFERENCES "SGPG_ORDER"(order_id), '
    "tag_id NUMBER REFERENCES sgpg_tag(tag_id), PRIMARY KEY (order_id, tag_id))",
    "CREATE TABLE sgpg_payroll (emp NUMBER PRIMARY KEY, pay NUMBER)",
    "CREATE VIEW sgpg_v_paid AS SELECT i.inv_id, c.region FROM sgpg_invoice i "
    "JOIN sgpg_customer c ON i.cust_ref = c.id WHERE i.status = 'paid'",
    "INSERT INTO sgpg_customer VALUES (1, 'EU', 'vip')",
    "INSERT INTO sgpg_customer VALUES (2, 'US', 'x')",
    "INSERT INTO sgpg_invoice VALUES (10, 1, 'paid')",
    "INSERT INTO sgpg_invoice VALUES (11, 2, 'draft')",
    "INSERT INTO sgpg_employee VALUES (1, NULL, 500)",
    "INSERT INTO sgpg_employee VALUES (2, 1, 100)",
    'INSERT INTO "SGPG_ORDER" VALUES (100, 1)',
    "INSERT INTO sgpg_tag VALUES (7, 'rush')",
    "INSERT INTO sgpg_order_tag VALUES (100, 7)",
    "INSERT INTO sgpg_payroll VALUES (1, 999)",
]
TEARDOWN = ["DROP PROPERTY GRAPH sgpg_analyst", "DROP PROPERTY GRAPH sgpg_hr", "DROP VIEW sgpg_v_paid",
            "DROP TABLE sgpg_order_tag", 'DROP TABLE "SGPG_ORDER"', "DROP TABLE sgpg_tag", "DROP TABLE sgpg_invoice",
            "DROP TABLE sgpg_customer", "DROP TABLE sgpg_employee", "DROP TABLE sgpg_payroll"]


def _statement(sql: str) -> str:
    return sql[sql.index("\nCREATE PROPERTY GRAPH") + 1:].rstrip().rstrip(";")


@pytest.fixture(scope="module")
def live():
    engine = create_engine(URL)

    def drop():
        for s in TEARDOWN:
            try:
                with engine.begin() as conn:
                    conn.execute(text(s))
            except Exception:                            # noqa: BLE001 -- it may not exist yet
                pass

    drop()
    with engine.begin() as conn:
        for s in SETUP:
            conn.execute(text(s))
    cat = Catalog().bootstrap(engine, include=["SGPG_*", "sgpg_*"])
    cat.restrict("sgpg_payroll", ["hr"])
    cat.restrict_column("sgpg_employee", "salary", ["hr"])
    cat.restrict_column("sgpg_customer", "secret_note", ["hr"])
    with engine.begin() as conn:
        conn.execute(text(_statement(cat.create_graph_sql(ANALYST, dialect="oracle", name="sgpg_analyst"))))
    yield engine, cat
    drop()
    engine.dispose()


def _rows(engine, match, columns, graph="sgpg_analyst"):
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT * FROM GRAPH_TABLE ({graph} MATCH {match} COLUMNS ({columns}))"))
        return sorted(tuple(int(v) if isinstance(v, (int, float)) or hasattr(v, "as_integer_ratio") else v for v in r)
                      for r in rows)


def test_a_join_known_only_from_a_view_can_be_traversed(live):
    engine, _ = live
    assert _rows(engine, "(i IS sgpg_invoice)-[e IS sgpg_invoice_cust_ref_sgpg_customer]->(k IS sgpg_customer)",
                 "i.inv_id, k.region") == [(10, "EU"), (11, "US")]


def test_a_table_pointing_at_itself_can_be_traversed(live):
    engine, _ = live
    assert _rows(engine, "(a IS sgpg_employee)-[e IS sgpg_employee_manager_id_sgpg_employee]->(b IS sgpg_employee)",
                 "a.id AS who, b.id AS boss") == [(2, 1)]


def test_a_bridge_table_can_be_traversed_in_two_hops(live):
    engine, _ = live
    assert _rows(engine, "(t IS sgpg_tag)<-[x IS sgpg_order_tag_tag_id_sgpg_tag]-(b IS sgpg_order_tag)"
                         "-[y IS sgpg_order_tag_order_id_sgpg_order]->(o IS sgpg_order)",
                 "t.label, o.customer_id") == [("rush", 1)]


@pytest.mark.parametrize("match, columns", [
    ("(a IS sgpg_employee)", "a.salary"),
    ("(a IS sgpg_employee)-[e IS sgpg_employee_manager_id_sgpg_employee]->(b IS sgpg_employee)", "e.salary"),
    ("(k IS sgpg_customer)", "k.secret_note"),
    ("(p IS sgpg_payroll)", "p.pay"),
])
def test_the_database_refuses_what_the_caller_may_not_see(live, match, columns):
    engine, _ = live
    with pytest.raises(Exception, match=r"ORA-40983|ORA-40954"):       # property never defined, unknown label
        _rows(engine, match, columns)


def test_a_caller_who_may_see_it_gets_a_graph_that_reads_it(live):
    engine, cat = live
    with engine.begin() as conn:
        conn.execute(text(_statement(cat.create_graph_sql(HR, dialect="oracle", name="sgpg_hr"))))
    assert _rows(engine, "(p IS sgpg_payroll)", "p.pay", graph="sgpg_hr") == [(999,)]
