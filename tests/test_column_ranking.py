"""Columns over the budget are chosen, not just truncated.

`render_ddl` kept `visible[:max_columns]` -- the first 40 columns in
declaration order, whatever was asked. On a wide fact table the column the
question needs can be number 147 and is cut entirely, while the prompt pays
for 40 nobody asked about.

The three properties worth pinning are that it finds the far column, that it
does not change anything when it has no question or no need to cut, and that
it cannot reach a column the caller may not see.
"""
from __future__ import annotations

import pytest

from schemagate.identity import Principal
from schemagate.models import Column, ForeignKey, ObjectDoc


def wide(n=200, restricted=None):
    """A table whose interesting column is last, which is the whole problem."""
    cols = [Column(name="id", type="INTEGER", pk=True)]
    cols += [Column(name=f"filler_{i:03d}", type="INTEGER") for i in range(n)]
    cols.append(Column(name="reorder_point", type="NUMERIC"))
    cols.append(Column(name="shortfall_qty", type="NUMERIC",
                       roles=restricted))
    return ObjectDoc(name="inv_stock", kind="TABLE", columns=cols)


def names(ddl):
    return [l.strip().split()[0].rstrip(",")
            for l in ddl.splitlines() if l.startswith("  ") and "--" not in l]


# ------------------------------------------------- it finds the far column

def test_the_column_the_question_needs_survives_the_budget():
    ddl = wide().render_ddl(max_columns=10, question="reorder point")
    assert "reorder_point" in ddl, (
        "the column the question named is at position 201 and was cut, which "
        "is the bug this ranking exists to fix")


def test_without_a_question_it_is_still_the_first_n():
    """The old behaviour, unchanged. Every caller that does not pass a
    question -- `bench.py`, anything rendering a catalog rather than an
    answer -- must see exactly what it saw before."""
    ddl = wide().render_ddl(max_columns=10)
    assert "reorder_point" not in ddl
    assert names(ddl) == ["id"] + [f"filler_{i:03d}" for i in range(9)]


def test_a_table_inside_the_budget_is_untouched_by_the_question():
    doc = wide(n=5)
    assert (doc.render_ddl(max_columns=40, question="reorder point")
            == doc.render_ddl(max_columns=40))


def test_a_question_that_matches_nothing_falls_back_to_the_first_n():
    ddl = wide().render_ddl(max_columns=10, question="!!! ??? ...")
    assert names(ddl) == ["id"] + [f"filler_{i:03d}" for i in range(9)]


# ------------------------------------------------------- keys are not cut

def test_keys_are_kept_even_when_the_question_ignores_them():
    """Dropping a foreign key does not cost a column, it costs a join. An
    unjoinable table in the prompt is worse than a missing one."""
    doc = wide()
    doc.columns.append(Column(name="id_warehouse", type="INTEGER"))
    doc.foreign_keys.append(
        ForeignKey(columns=["id_warehouse"], ref_table="inv_warehouse"))
    ddl = doc.render_ddl(max_columns=5, question="reorder point")
    assert "id_warehouse" in ddl, "the FK column was cut"
    assert "id" in names(ddl), "the primary key was cut"
    assert "reorder_point" in ddl


def test_the_fk_line_survives_with_its_column():
    doc = wide()
    doc.columns.append(Column(name="id_warehouse", type="INTEGER"))
    doc.foreign_keys.append(
        ForeignKey(columns=["id_warehouse"], ref_table="inv_warehouse"))
    ddl = doc.render_ddl(max_columns=5, question="reorder point")
    assert "FK inv_stock(id_warehouse) -> inv_warehouse" in ddl


# -------------------------------------------------------- order and count

def test_chosen_columns_are_rendered_in_declaration_order():
    """Selection reorders; rendering must not. The DDL should still read like
    the DDL."""
    ddl = wide().render_ddl(max_columns=10, question="reorder point shortfall")
    got = names(ddl)
    assert got == sorted(got, key=lambda n: (n != "id", n)), got
    assert got.index("reorder_point") > got.index("filler_000")


def test_the_omitted_count_is_the_truth():
    doc = wide()                       # 1 pk + 200 filler + 2 = 203 columns
    ddl = doc.render_ddl(max_columns=10, question="reorder point")
    assert len(names(ddl)) == 10
    assert "...193 more columns" in ddl


def test_the_note_says_which_kind_of_omission_it_was():
    doc = wide()
    assert "(least relevant to the question)" in doc.render_ddl(
        max_columns=10, question="reorder point")
    assert "(least relevant to the question)" not in doc.render_ddl(
        max_columns=10)


def test_the_same_question_always_chooses_the_same_columns():
    doc = wide()
    once = doc.render_ddl(max_columns=12, question="reorder point")
    for _ in range(5):
        assert doc.render_ddl(max_columns=12, question="reorder point") == once


# ------------------------------------------------------------- the boundary

RESTRICTED = ["payroll"]


def test_ranking_cannot_surface_a_column_the_caller_may_not_see():
    """The property that matters most. Ranking runs *after* visible_columns,
    so a question naming a restricted column must not pull it back."""
    doc = wide(restricted=RESTRICTED)
    anon = Principal(subject="okta:nobody")
    ddl = doc.render_ddl(max_columns=10, principal=anon,
                         question="shortfall_qty shortfall qty")
    assert "shortfall_qty" not in ddl, "A RESTRICTED COLUMN WAS RANKED IN"


def test_the_authorised_caller_still_gets_it():
    doc = wide(restricted=RESTRICTED)
    boss = Principal(subject="okta:boss", roles=frozenset({"payroll"}))
    ddl = doc.render_ddl(max_columns=10, principal=boss,
                         question="shortfall qty")
    assert "shortfall_qty" in ddl


def test_a_restricted_column_is_not_even_counted_as_omitted():
    """The count is over what this caller could have seen. Counting the
    restricted one would tell an unauthorised reader it exists."""
    doc = wide(restricted=RESTRICTED)
    anon = Principal(subject="okta:nobody")
    boss = Principal(subject="okta:boss", roles=frozenset({"payroll"}))
    a = doc.render_ddl(max_columns=10, principal=anon, question="reorder point")
    b = doc.render_ddl(max_columns=10, principal=boss, question="reorder point")
    assert "...192 more columns" in a
    assert "...193 more columns" in b


# --------------------------------------------------- through the Selection

def test_prompt_fragment_passes_the_question_down():
    from schemagate import Catalog
    from schemagate.models import Scored, Selection

    doc = wide()
    sel = Selection(question="reorder point",
                    hits=[Scored(doc=doc, score=1.0, reason="lexical")])
    assert "reorder_point" in sel.prompt_fragment(max_columns=10)
    # and the same selection asked without its question would not have it
    assert "reorder_point" not in doc.render_ddl(max_columns=10)
