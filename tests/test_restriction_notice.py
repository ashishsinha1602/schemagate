# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""A caller who sees part of the database is told so -- that, never what.

On the RBAC Text-to-SQL benchmark a model given only the columns a role may read
did not refuse a question that needed the rest: it approximated the answer from
what was left. One line saying the view is partial took answers to denied
questions on a 100-question BIRD pilot from 16% to 5% (BENCHMARKS.md). The line
must not name the withheld objects, or the restriction would leak through it.
"""
from schemagate import Catalog, Column, ObjectDoc, Principal
from schemagate.models import RESTRICTED_NOTICE

ANALYST = Principal("okta:ana", roles=frozenset({"analyst"}))
HR = Principal("okta:hr", roles=frozenset({"analyst", "payroll"}))


def _catalog():
    cat = Catalog(name="t")
    cat.add(ObjectDoc(name="employee", schema="hr", kind="table",
                      columns=[Column("id", "INT", pk=True), Column("name", "TEXT"),
                               Column("salary_band", "TEXT")]))
    cat.add(ObjectDoc(name="payroll_run", schema="hr", kind="table",
                      columns=[Column("id", "INT", pk=True), Column("gross_pay", "NUMERIC")]))
    cat.index()
    return cat


def test_no_restriction_no_notice():
    sel = _catalog().select("employee names", principal=ANALYST)
    assert not sel.restricted
    assert RESTRICTED_NOTICE not in sel.prompt_fragment()


def test_a_hidden_table_adds_the_notice_and_names_nothing():
    cat = _catalog()
    cat.restrict("payroll_run", roles=["payroll"])
    frag = cat.select("employee names", principal=ANALYST).prompt_fragment()
    assert frag.startswith(RESTRICTED_NOTICE + "\n")
    assert "payroll_run" not in frag and "gross_pay" not in frag


def test_a_hidden_column_adds_the_notice_and_names_nothing():
    cat = _catalog()
    cat.restrict_column("employee", "salary_band", roles=["payroll"])
    frag = cat.select("employee names", principal=ANALYST).prompt_fragment()
    assert frag.startswith(RESTRICTED_NOTICE + "\n")
    assert "salary_band" not in frag


def test_a_caller_who_sees_everything_gets_no_notice():
    cat = _catalog()
    cat.restrict("payroll_run", roles=["payroll"])
    cat.restrict_column("employee", "salary_band", roles=["payroll"])
    assert not cat.select("employee names", principal=HR).restricted


def test_it_can_be_turned_off():
    cat = _catalog()
    cat.restrict("payroll_run", roles=["payroll"])
    cat.restriction_notice = False
    sel = cat.select("employee names", principal=ANALYST)
    assert not sel.restricted and RESTRICTED_NOTICE not in sel.prompt_fragment()


def test_the_notice_is_the_one_the_benchmark_measured():
    # benchmarks/rbac_text2sql.py prepended exactly this line when it was measured; the
    # published figures describe the library only while the two stay identical.
    assert RESTRICTED_NOTICE.startswith("-- This caller may read only part of this database")
    assert RESTRICTED_NOTICE.endswith("do not approximate it from other columns.")
