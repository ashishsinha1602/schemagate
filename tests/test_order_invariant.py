"""The guard on `_order`, stated as a property rather than a value.

`len(_order) == len(_docs)` is FALSE by design in the window between a
mutation and the next index(): `collapse_partitions()` deletes merged
members from `_docs` and re-keys the survivor, and `_order` is assigned
only inside `index()`. Asserting the equality at rest would pin a state
the catalogue deliberately passes through.

What actually keeps that window safe is that every reader of `_order`
rebuilds a stale index first. That is the thing a future commit can break,
so that is what these tests assert.

Reported by howcani on the dev.to thread for the 1,245-table post.
"""
import ast
import inspect

import pytest

from schemagate import Catalog
from schemagate import catalog as catalog_mod
from schemagate.models import Column, ObjectDoc


def _doc(name, cols=("id", "amount")):
    return ObjectDoc(schema="main", name=name, kind="table",
                     columns=[Column(name=c, type="TEXT") for c in cols],
                     description="daily event rows")


def _merged_catalog():
    """A catalogue in the dirty window: indexed, then merged, not re-indexed."""
    cat = Catalog()
    cat.add_all([_doc("events_202401"), _doc("events_202402"),
                 _doc("events_202403"), _doc("events_202404"),
                 _doc("customers", ("id", "name")),
                 _doc("invoices", ("id", "total"))])
    cat.index()
    removed = cat.collapse_partitions()
    assert removed == 3, "fixture must actually collapse a family"
    return cat


def test_the_dirty_window_is_real_and_is_not_what_we_assert():
    """Pin the divergence itself, so the tests below are known to be exercised."""
    cat = _merged_catalog()
    dangling = [q for q in cat._order if q not in cat._docs]
    unindexed = [q for q in cat._docs if q not in cat._order]
    assert dangling, "fixture no longer produces a stale _order"
    assert unindexed, "fixture no longer produces an unindexed doc"
    assert cat._stale is True, "a mutation that moved _docs must mark the index stale"


def test_no_one_reads_order_without_the_rebuild():
    """The property that keeps the dirty window safe.

    Fails when a new method reads `self._order` directly instead of going
    through `_ordered()` -- which is the only way the divergence above can
    become observable. `index()` assigns it; `_ordered()` guards it.
    """
    tree = ast.parse(inspect.getsource(catalog_mod))
    allowed = {"index", "_ordered", "__init__"}
    offenders = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in allowed:
            continue
        hits = [n.lineno for n in ast.walk(node)
                if isinstance(n, ast.Attribute) and n.attr == "_order"
                and isinstance(n.value, ast.Name) and n.value.id == "self"]
        if hits:
            offenders[node.name] = hits
    assert not offenders, (
        "these read self._order without going through _ordered(), so they can "
        "see qnames that _docs no longer has: " + repr(offenders))


@pytest.mark.parametrize("call", [
    pytest.param(lambda c: c.select("monthly events", top_k=3), id="select"),
    pytest.param(lambda c: c.shadows(), id="shadows"),
])
def test_every_entry_point_heals_the_window(call):
    """Called first on a dirtied catalogue, a reader re-indexes, not reads dead names."""
    cat = _merged_catalog()
    call(cat)
    assert [q for q in cat._order if q not in cat._docs] == []
    assert [q for q in cat._docs if q not in cat._order] == []


def test_select_after_merge_returns_the_survivor_not_the_dead_members():
    """The observable consequence, if the guard is ever lost."""
    cat = _merged_catalog()
    sel = cat.select("monthly events", top_k=3)
    names = [h.doc.qname for h in sel.hits]
    assert "main.events_*" in names, "the merged survivor must be retrievable"
    assert not any(n.startswith("main.events_2024") for n in names), \
        "a deleted partition member must not be returned"
    assert sel.total_objects == len(cat._docs)
