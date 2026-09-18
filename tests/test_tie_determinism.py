"""The same database, reflected in a different order, must answer the same.

Ties in every ranked list were broken by insertion order, and insertion order
is reflection order -- `ALL_TABLES` with no ORDER BY, a changed `search_path`,
one table created later than the rest. So the same schema read twice could
return a different set of tables, with nothing in the output to say why.

Two fixes, and they are not one fix at half strength:

  A  shared ranks for equal scores inside `_rank` (competition ranking)
  B  the qname as the final sort key on the fused scores

A alone freezes the fused scores and the selection can still move, because a
tie survives into the final sort with nothing left to break it. B alone leaves
the inputs to that sort order-dependent. Both tests below are written so that
reverting either one fails something.
"""
from __future__ import annotations

import itertools

import pytest

from schemagate import Catalog
from schemagate.catalog import _competition_rank


# --------------------------------------------------- fix A, in isolation

def test_equal_scores_share_a_rank():
    got = _competition_rank([("a", 3.0), ("b", 1.0), ("c", 1.0), ("d", 0.5)])
    assert got["b"] == got["c"], "tied scores were given different ranks"
    assert got["a"] == 0 and got["d"] == 3, "competition ranking skips, 1-2-2-4"


def test_the_rank_does_not_depend_on_the_order_it_was_given():
    """The precondition first: this input really does contain a tie. A test
    that asserts stability over a list with no ties asserts nothing."""
    pairs = [("a", 3.0), ("b", 1.0), ("c", 1.0), ("d", 0.5)]
    assert len({s for _, s in pairs}) < len(pairs), "no tie in the fixture"
    first = _competition_rank(pairs)
    for permutation in itertools.permutations(pairs):
        assert _competition_rank(list(permutation)) == first


def test_an_empty_list_is_not_a_crash():
    assert _competition_rank([]) == {}


# ------------------------------------------------ both fixes, end to end

#: A genuine all-channel tie: the SAME table name in several schemas, with
#: identical descriptions and columns. This is not contrived -- the complex
#: fixture already ships three tables called `account` in three schemas, and
#: any warehouse with a bronze/silver/gold layout has hundreds of them.
#:
#: The schema names are deliberately the same length and a single token each,
#: so the documents are the same length and the term frequencies identical.
#: That makes every channel tie exactly, which is the state fix A converts
#: into equal ranks and fix B then has to order.
SCHEMAS = ["auditx", "crmxxx", "opsxxx", "salesx"]


def _catalog_in(order):
    from schemagate.models import Column, ObjectDoc
    docs = [ObjectDoc(
        name="crm_contact", schema=s, kind="TABLE",
        description="Operational record in the customer contact platform.",
        columns=[Column(name="id", type="INTEGER"),
                 Column(name="amount", type="NUMERIC")]) for s in order]
    cat = Catalog(name="ties")
    cat.add_all(docs)
    cat.index()
    return cat


def test_the_fixture_actually_ties():
    """Precondition, asserted before any conclusion is drawn from it.

    The first version of this module used objects with different names and
    they did not tie at all -- the tests passed against a build with the fix
    reverted, which is a test that measures nothing.
    """
    sel = _catalog_in(SCHEMAS).select("contact", top_k=4)
    scores = [round(h.score, 12) for h in sel.hits]
    assert len(scores) > 1, "nothing was selected"
    assert len(set(scores)) == 1, (
        f"the fixture does not tie, so it cannot detect the bug: {scores}")


@pytest.mark.parametrize("question", ["contact", "contact record",
                                      "customer contact platform"])
def test_the_selection_does_not_depend_on_reflection_order(question):
    """The bug as a user meets it: same database, read in a different order,
    different tables come back."""
    orders = [
        SCHEMAS,
        list(reversed(SCHEMAS)),
        SCHEMAS[2:] + SCHEMAS[:2],
        [SCHEMAS[i] for i in (2, 0, 3, 1)],
        [SCHEMAS[i] for i in (1, 3, 0, 2)],
        sorted(SCHEMAS, key=lambda n: n[::-1]),
    ]
    results = {tuple(d.qname for d in _catalog_in(o)
                     .select(question, top_k=2).objects) for o in orders}
    assert len(results) == 1, (
        f"{len(results)} different answers to {question!r} from the same "
        f"objects in different orders: {sorted(results)}")


@pytest.mark.parametrize("question", ["contact", "contact record"])
def test_the_scores_do_not_depend_on_reflection_order(question):
    """Fix A's half specifically: the fused scores themselves."""
    orders = [SCHEMAS, list(reversed(SCHEMAS)), SCHEMAS[2:] + SCHEMAS[:2]]
    seen = set()
    for o in orders:
        sel = _catalog_in(o).select(question, top_k=4)
        seen.add(tuple(sorted((h.doc.qname, round(h.score, 12))
                              for h in sel.hits)))
    assert len(seen) == 1, "fused scores moved with reflection order"


def test_ties_are_broken_by_name_so_the_order_is_stated_not_accidental():
    """Fix B's half specifically.

    With fix A every one of these scores is identical, so fix A has nothing
    left to say about their order. What decides it must be a rule someone can
    read -- the qualified name -- and not whichever row the database happened
    to hand back first.
    """
    sel = _catalog_in(list(reversed(SCHEMAS))).select("contact", top_k=4)
    names = [h.doc.qname for h in sel.hits]
    assert len({round(h.score, 12) for h in sel.hits}) == 1, "not all tied"
    assert names == sorted(names), f"tied group not in name order: {names}"


def test_a_tie_that_straddles_the_top_k_boundary_is_stable():
    """Where the bug actually bites. If four objects tie and only two fit,
    the two that survive are decided entirely by the tie-break -- so this is
    the case where reflection order changed the answer rather than merely
    reshuffling it."""
    orders = [SCHEMAS, list(reversed(SCHEMAS)),
              [SCHEMAS[i] for i in (3, 1, 2, 0)]]
    picked = {tuple(d.qname for d in _catalog_in(o)
                    .select("contact", top_k=2).objects) for o in orders}
    assert len(picked) == 1, f"top-2 of a 4-way tie moved: {sorted(picked)}"
