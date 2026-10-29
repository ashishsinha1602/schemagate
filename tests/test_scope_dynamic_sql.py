# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""run_query and a query hidden in a string the database runs (GHSA-r77g-5v43-wh54).

Both gates read table names from the statement's syntax, and both empty string
literals first. PostgreSQL's `query_to_xml('SELECT * FROM payroll', ...)` and
Oracle's `DBMS_XMLGEN.GETXML('SELECT ...')` run the text inside the literal,
so a restricted table was read with neither gate seeing its name. The known
functions are now refused by name, and a string that is a query naming a
hidden table, or is exactly a hidden table's name handed to a function, is
refused whatever function receives it.
"""
from types import SimpleNamespace as NS

import pytest

from schemagate import Principal
from schemagate.answer import UnsafeSQL, check_read_only
from schemagate.mcp_server import _check_scope
from schemagate.models import allowed

NOBODY = Principal("okta:eve", roles=frozenset())
PAYROLL = Principal("okta:bob", roles=frozenset({"payroll"}))


def _doc(schema, name, roles):
    cols = [NS(name="id", roles=None), NS(name="amount", roles=None)]
    return NS(schema=schema, name=name, qname=f"{schema}.{name}", roles=roles, columns=cols,
              visible_columns=lambda who, cols=cols: list(cols))


class _Cat:
    def __init__(self, docs):
        self._d = docs

    def objects(self):
        return self._d

    def _visible(self, doc, who):
        return allowed(doc.roles, who)


CAT = _Cat([_doc("public", "orders", None), _doc("public", "hr_compensation", ["payroll"])])

ATTACKS = [
    # the report's PostgreSQL and Oracle payloads
    "SELECT query_to_xml('SELECT * FROM hr_compensation', true, true, '') AS result",
    "SELECT DBMS_XMLGEN.GETXML('SELECT * FROM hr_compensation') AS r FROM orders",
    # the rest of the family, qualified and in other cases
    "SELECT pg_catalog.query_to_xml('select * from hr_compensation', true, true, '')",
    "SELECT query_to_xml_and_xmlschema('SELECT * FROM hr_compensation', true, true, '')",
    "SELECT table_to_xml('hr_compensation', true, true, '')",
    "SELECT table_to_xml('public.hr_compensation'::regclass, true, true, '')",
    "SELECT cursor_to_xml('c', 10, true, true, '')",
    "SELECT schema_to_xml('public', true, true, '')",
    "SELECT database_to_xml(true, true, '')",
    "SELECT * FROM dblink('dbname=x', 'SELECT * FROM hr_compensation') AS t(a int)",
    "SELECT * FROM ts_stat('SELECT to_tsvector(name) FROM hr_compensation')",
    "SELECT sys.dbms_xmlgen.getxmltype('SELECT * FROM hr_compensation') FROM orders",
    "SELECT XMLQUERY('ora:view(\"HR_COMPENSATION\")' RETURNING CONTENT) FROM orders",
    "SELECT * FROM OPENQUERY(srv, 'SELECT * FROM hr_compensation')",
    "SELECT * FROM OPENROWSET('SQLNCLI', 'x', 'SELECT * FROM hr_compensation')",
    "SELECT * FROM IDENTIFIER('hr_compensation')",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT set_config('role', 'payroll', false)",
]


@pytest.mark.parametrize("sql", ATTACKS)
def test_each_attack_is_refused_by_the_read_only_gate(sql):
    with pytest.raises(UnsafeSQL):
        check_read_only(sql)


@pytest.mark.parametrize("sql", [
    # an unknown function (an extension, a user-defined one) that runs its text
    "SELECT run_sql('SELECT * FROM hr_compensation')",
    "SELECT my_exec('select amount from public.hr_compensation where id = 1')",
    "SELECT o.id, f('WITH x AS (SELECT 1) SELECT * FROM hr_compensation') FROM orders o",
    "SELECT some_export('hr_compensation', true)",
    "SELECT some_export(1, 'public.hr_compensation')",
])
def test_a_hidden_table_inside_a_string_is_refused_by_the_scope_check(sql):
    assert check_read_only(sql)          # no known function: only the scope check can catch it
    assert _check_scope(CAT, sql, NOBODY) is not None


@pytest.mark.parametrize("sql", [
    "SELECT id FROM orders WHERE note = 'hr_compensation'",          # a comparison, not a function argument
    "SELECT id FROM orders WHERE note = 'select something from the menu'",
    "SELECT replace(note, 'from', 'to') FROM orders",
    "SELECT id, 'table' AS kind FROM orders",
    "SELECT id FROM orders WHERE status IN ('open', 'closed')",
    "SELECT id FROM orders WHERE note IN ('x', 'hr_compensation')",   # a list, not a call
    "SELECT 'from hr_compensation' AS label, id FROM orders",          # a label, not a call
])
def test_ordinary_strings_still_pass(sql):
    assert check_read_only(sql)
    assert _check_scope(CAT, sql, NOBODY) is None


def test_the_entitled_caller_is_unaffected_by_the_scope_backstop():
    sql = "SELECT run_sql('SELECT * FROM hr_compensation')"
    assert _check_scope(CAT, sql, PAYROLL) is None
