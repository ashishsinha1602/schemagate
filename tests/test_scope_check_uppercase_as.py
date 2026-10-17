# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""`FROM t AS T1` must not read `T1` as a table.

The FROM-list reader matched its alias pattern case-sensitively, so `as` worked and `AS`
did not: `students AS T1` read `AS` as the alias and `T1` as a second table, and run_query
refused an ordinary aliased query as "not available to this caller: T1". Found on the
Spider-ACL benchmark, where it caused 32 of 33 wrong refusals in a 200-question sample.
"""
import pytest

from schemagate import Catalog, Column, ObjectDoc, Principal
from schemagate.mcp_server import _check_scope, _referenced_tables

WHO = Principal("okta:ana", roles=frozenset({"analyst"}))


def _catalog():
    cat = Catalog(name="t")
    cat.add(ObjectDoc(name="students", schema="main", kind="table",
                      columns=[Column("student_id", "INT"), Column("name", "TEXT")]))
    cat.add(ObjectDoc(name="reg", schema="main", kind="table",
                      columns=[Column("student_id", "INT"), Column("course", "INT")]))
    cat.add(ObjectDoc(name="payroll", schema="main", kind="table",
                      columns=[Column("student_id", "INT"), Column("salary", "INT")]))
    cat.restrict("payroll", roles=["hr"])
    cat.index()
    return cat


@pytest.mark.parametrize("sql", [
    "SELECT T1.name FROM students AS T1",
    "SELECT T1.name FROM main.students AS T1",
    "select t1.name from students As t1",
    "SELECT T1.student_id, COUNT(T2.course) FROM main.students AS T1 "
    "INNER JOIN main.reg AS T2 ON T1.student_id = T2.student_id GROUP BY T1.student_id",
    "SELECT a.name FROM students AS a, reg AS b WHERE a.student_id = b.student_id",
])
def test_an_uppercase_as_alias_is_not_a_table(sql):
    assert _check_scope(_catalog(), sql, WHO) is None
    assert {t.lower().split(".")[-1] for t in _referenced_tables(sql)} <= {"students", "reg"}


@pytest.mark.parametrize("sql", [
    "SELECT T1.salary FROM payroll AS T1",
    "SELECT s.name FROM students AS s JOIN main.payroll AS p ON s.student_id = p.student_id",
    "SELECT x.name FROM students AS payroll_copy JOIN payroll AS x ON 1 = 1",
    "SELECT payroll.name FROM students AS payroll",     # a hidden table's name used as an alias
])
def test_a_hidden_table_behind_an_alias_is_still_refused(sql):
    assert _check_scope(_catalog(), sql, WHO) is not None
