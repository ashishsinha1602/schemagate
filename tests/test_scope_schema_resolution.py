# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""run_query's scope check when one table name means two objects.

The check used to fall back from a qualified name to its bare table name, so
with `public.salary` visible and `hr.salary` restricted, `SELECT * FROM
hr.salary` passed: `salary` was a visible name. The same fold let a quoted
name that differs only in case from a visible one through. A reference must
now resolve to visible objects only; anything that might mean a hidden one is
refused.
"""
from types import SimpleNamespace as NS

import pytest

from schemagate import Principal
from schemagate.mcp_server import _check_scope
from schemagate.models import allowed

SALES = Principal("okta:alice", roles=frozenset({"sales"}))
PAYROLL = Principal("okta:bob", roles=frozenset({"payroll"}))


def _doc(schema, name, roles, hidden_col=None):
    cols = [NS(name="id", roles=None), NS(name="amount", roles=None)]
    if hidden_col:
        cols.append(NS(name=hidden_col, roles=["payroll"]))
    return NS(schema=schema, name=name, qname=f"{schema}.{name}", roles=roles, columns=cols,
              visible_columns=lambda who, cols=cols: [c for c in cols if allowed(c.roles, who)])


class _Cat:
    def __init__(self, docs):
        self._d = docs

    def objects(self):
        return self._d

    def _visible(self, doc, who):
        return allowed(doc.roles, who)


TWO_SCHEMAS = _Cat([_doc("public", "salary", None), _doc("hr", "salary", ["payroll"]),
                    _doc("public", "orders", None)])


@pytest.mark.parametrize("sql", [
    "SELECT * FROM hr.salary",
    'SELECT * FROM "hr"."salary"',
    "SELECT * FROM [hr].[salary]",
    "SELECT * FROM HR.SALARY",
    "SELECT * FROM mydb.hr.salary",
    "SELECT o.id FROM public.orders o JOIN hr.salary s ON s.id = o.id",
    "SELECT o.id FROM public.orders o, hr.salary s",
    "SELECT * FROM salary",  # may resolve to hr.salary on the search path
])
def test_a_restricted_table_is_refused_when_another_schema_has_the_same_name(sql):
    assert _check_scope(TWO_SCHEMAS, sql, SALES) is not None


@pytest.mark.parametrize("sql", ["SELECT * FROM public.salary", "SELECT * FROM orders",
                                 "SELECT * FROM public.orders"])
def test_the_visible_twin_still_works(sql):
    assert _check_scope(TWO_SCHEMAS, sql, SALES) is None


def test_the_caller_with_the_role_reads_both():
    for sql in ("SELECT * FROM hr.salary", "SELECT * FROM public.salary", "SELECT * FROM salary"):
        assert _check_scope(TWO_SCHEMAS, sql, PAYROLL) is None


def test_an_ambiguous_bare_name_says_to_qualify_it():
    msg = _check_scope(TWO_SCHEMAS, "SELECT * FROM salary", SALES)
    assert "qualify it with its schema" in msg


CASE_TWINS = _Cat([_doc("public", "payroll", None), _doc("public", "Payroll", ["payroll"])])


@pytest.mark.parametrize("sql", ['SELECT * FROM "Payroll"', "SELECT * FROM payroll",
                                 'SELECT * FROM public."Payroll"'])
def test_names_that_differ_only_in_case_fail_closed(sql):
    assert _check_scope(CASE_TWINS, sql, SALES) is not None


def test_column_rules_apply_to_the_object_the_name_resolves_to():
    cat = _Cat([_doc("public", "staff", None, hidden_col="ssn"), _doc("hr", "notes", ["payroll"])])
    assert _check_scope(cat, "SELECT ssn FROM public.staff", SALES) is not None
    assert _check_scope(cat, "SELECT * FROM public.staff", SALES) is not None
    assert _check_scope(cat, "SELECT id FROM public.staff", SALES) is None
