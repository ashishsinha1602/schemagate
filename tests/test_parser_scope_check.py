# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""run_query's scope check reads SQL with a real parser as well as its patterns.

Three bypasses in one week were each a dialect's own way of writing a name the pattern readers
did not expect: a schema-qualified twin (GHSA-c258), a column shadowed by a visible one of the
same name (GHSA-2mmx), SQLite's single-quoted table name (GHSA-qhcw). sqlglot knows each
dialect's grammar. Its findings are added to the patterns', so a statement is refused if either
sees a name the caller may not use.

The first tests switch the pattern readers OFF and check the parser alone still refuses every
one of those attacks: two independent locks, not one.
"""
from types import SimpleNamespace as NS

import pytest

from schemagate import Principal
from schemagate import mcp_server as M
from schemagate.models import allowed

pytest.importorskip("sqlglot")

SALES = Principal("okta:s", roles=frozenset({"sales"}))


def _doc(schema, name, roles=None, cols=(("id", None), ("amount", None))):
    cs = [NS(name=c, roles=r) for c, r in cols]
    return NS(schema=schema, name=name, qname=f"{schema}.{name}", roles=roles, columns=cs,
              visible_columns=lambda who, cs=cs: [c for c in cs if allowed(c.roles, who)])


class _Cat:
    def __init__(self, docs):
        self._d = docs

    def objects(self):
        return self._d

    def _visible(self, doc, who):
        return allowed(doc.roles, who)


CAT = _Cat([
    _doc("public", "orders"),
    _doc("public", "salary"),
    _doc("hr", "salary", roles=["payroll"]),
    _doc("main", "secret", roles=["payroll"]),
    _doc("public", "staff", cols=(("id", None), ("salary", ["payroll"]))),
    _doc("public", "offers", cols=(("id", None), ("salary", None))),
])

ATTACKS = [
    ("postgresql", "SELECT * FROM hr.salary"),                                   # GHSA-c258
    ("postgresql", 'SELECT * FROM "hr"."salary"'),
    ("mssql", "SELECT * FROM [hr].[salary]"),
    ("mysql", "SELECT * FROM `hr`.`salary`"),
    ("postgresql", "SELECT s.salary FROM staff s CROSS JOIN offers"),            # GHSA-2mmx
    ("postgresql", "SELECT * FROM staff CROSS JOIN offers"),
    ("postgresql", "WITH x AS (SELECT (SELECT salary FROM staff) FROM offers) SELECT * FROM x"),
    ("sqlite", """SELECT "salary" FROM orders NATURAL JOIN 'secret' orders"""),   # GHSA-qhcw
    ("sqlite", "SELECT * FROM main.'secret'"),
]


@pytest.fixture
def dialect(monkeypatch):
    def set_(name):
        monkeypatch.setattr(M, "_dialect_name", lambda: name)
    return set_


@pytest.mark.parametrize("name,sql", ATTACKS)
def test_the_parser_alone_refuses_every_attack(monkeypatch, dialect, name, sql):
    dialect(name)
    monkeypatch.setattr(M, "_referenced_tables", lambda s: [])      # pattern readers off
    monkeypatch.setattr(M, "_identifiers", lambda s: set())
    monkeypatch.setattr(M, "_STAR", NS(search=lambda s: None))
    assert M._check_scope(CAT, sql, SALES) is not None, sql


@pytest.mark.parametrize("name,sql", ATTACKS)
def test_both_layers_together_refuse_every_attack(dialect, name, sql):
    dialect(name)
    assert M._check_scope(CAT, sql, SALES) is not None


@pytest.mark.parametrize("name,sql", [
    ("postgresql", "SELECT id, amount FROM public.orders"),
    ("postgresql", "SELECT o.id FROM orders o JOIN offers f ON f.id = o.id"),
    ("postgresql", "SELECT COUNT(*) FROM staff"),
    ("postgresql", "WITH x AS (SELECT id FROM orders) SELECT * FROM x"),
    ("mssql", "SELECT TOP 5 id FROM [public].[orders]"),
    ("oracle", "SELECT id FROM orders WHERE ROWNUM <= 5"),
    ("sqlite", "SELECT id FROM orders WHERE amount > 1 LIMIT 5"),
])
def test_ordinary_queries_still_run(dialect, name, sql):
    dialect(name)
    assert M._check_scope(CAT, sql, SALES) is None, M._check_scope(CAT, sql, SALES)


def test_a_statement_the_parser_cannot_read_is_refused(dialect):
    dialect("postgresql")
    out = M._check_scope(CAT, "SELECT id FROM orders WHERE (", SALES)
    assert out is not None and "could not be parsed" in out


def test_without_sqlglot_the_pattern_readers_still_guard(monkeypatch, dialect):
    dialect("postgresql")
    monkeypatch.setattr(M, "_parsed_refs", lambda sql: None)
    assert M._check_scope(CAT, "SELECT * FROM hr.salary", SALES) is not None
    assert M._check_scope(CAT, "SELECT id FROM orders", SALES) is None


def test_the_payroll_role_can_still_read_what_it_may():
    payroll = Principal("okta:p", roles=frozenset({"payroll"}))
    assert M._check_scope(CAT, "SELECT * FROM hr.salary", payroll) is None
