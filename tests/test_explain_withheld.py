"""`explain()` has to say a column was withheld, and must not say which.

`to_dict()` reported `columns_withheld` and `explain()` reported nothing, so
the one thing someone checking a column restriction wants to see -- that it
fired at all -- was only in the JSON. The rule `to_dict` states applies just
as much here, and more so: explain() output is what gets pasted into an issue.
"""
from __future__ import annotations

import pytest

from schemagate import Catalog, Column, ObjectDoc, Principal

SECRET = "salary"
TABLE = "hr_employee"


@pytest.fixture
def cat() -> Catalog:
    c = Catalog(name="explain-withheld")
    c.add(ObjectDoc(
        name=TABLE, schema="main", kind="TABLE",
        description="people and what they are paid",
        columns=[Column("id", "INTEGER", False, None, True),
                 Column("display_name", "TEXT", True, None, False),
                 Column("department", "TEXT", True, None, False),
                 Column(SECRET, "NUMERIC", True, None, False)]))
    c.add(ObjectDoc(
        name="hr_department", schema="main", kind="TABLE",
        description="teams people belong to",
        columns=[Column("id", "INTEGER", False, None, True),
                 Column("name", "TEXT", True, None, False)]))
    c.restrict_column(TABLE, SECRET, ["payroll"])
    return c.index()


def _explain(cat, principal):
    return cat.select("who works here and what do they earn",
                      top_k=4, principal=principal).explain()


def test_the_count_is_shown_when_a_column_is_withheld(cat):
    out = _explain(cat, Principal("okta:analyst"))
    assert TABLE in out, out
    assert "1 column withheld" in out, out


def test_the_restricted_column_name_appears_nowhere(cat):
    """The whole point. A name in a log is a disclosure to every reader of it."""
    out = _explain(cat, Principal("okta:analyst"))
    assert SECRET not in out.lower(), out


def test_nothing_is_annotated_for_a_caller_who_may_see_it_all(cat):
    out = _explain(cat, Principal("okta:hr", roles={"payroll"}))
    assert "withheld" not in out, out


def test_rows_with_nothing_withheld_are_left_alone(cat):
    """Otherwise every line carries "(0 columns withheld)" and the annotation
    stops meaning anything."""
    out = _explain(cat, Principal("okta:analyst"))
    for line in out.splitlines():
        if "hr_department" in line:
            assert "withheld" not in line, line


def test_it_is_singular_for_one_and_plural_for_more():
    c = Catalog(name="plural")
    c.add(ObjectDoc(
        name="t", schema="main", kind="TABLE",
        columns=[Column("id", "INTEGER", False, None, True),
                 Column("a", "TEXT", True, None, False),
                 Column("b", "TEXT", True, None, False)]))
    c.restrict_column("t", "a", ["x"])
    c.restrict_column("t", "b", ["x"])
    out = c.index().select("t", top_k=2, principal=Principal("okta:nobody")).explain()
    assert "2 columns withheld" in out, out


def test_to_dict_still_reports_the_count_and_not_the_names(cat):
    """The record explain() is the human face of; kept honest alongside it."""
    sel = cat.select("who works here and what do they earn",
                     top_k=4, principal=Principal("okta:analyst"))
    d = sel.to_dict()
    hit = next(h for h in d["hits"] if h["object"].endswith(TABLE))
    assert hit["columns_withheld"] == 1
    assert SECRET not in repr(d).lower()
