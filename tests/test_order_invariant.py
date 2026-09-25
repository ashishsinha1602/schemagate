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
import pathlib
import subprocess

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


@pytest.mark.parametrize("mutate", [
    pytest.param(lambda c: c.add(_doc("late_arrival")), id="add"),
    pytest.param(lambda c: c.collapse_partitions(), id="collapse_partitions"),
])
def test_both_docs_mutators_mark_the_index_stale(mutate):
    """The runtime half of the writer obligation, over both mutators.

    The AST rule above says every `_docs` writer assigns `_stale`. This says
    the two that exist actually leave the catalogue marked, so `_ordered()`
    will rebuild. `add()` had no test under it before.
    """
    cat = Catalog()
    cat.add_all([_doc("events_202401"), _doc("events_202402"),
                 _doc("events_202403"), _doc("events_202404"),
                 _doc("customers", ("id", "name"))])
    cat.index()
    assert cat._stale is False, "index() must leave the catalogue clean"
    mutate(cat)
    assert cat._stale is True, "a mutation of _docs must mark the index stale"
    cat.select("monthly events", top_k=3)
    assert [q for q in cat._order if q not in cat._docs] == []
    assert [q for q in cat._docs if q not in cat._order] == []


# Files that read the derived state on purpose. tests/ is exempt because
# several tests assert on `_order` itself -- that is their subject. Anything
# added here is a deliberate, named exception, not a silent one.
_READER_EXEMPT_DIRS = ("tests/",)

# In catalog.py, `index()` assigns `_order` and `_ordered()` guards it.
_READER_EXEMPT_FUNCS = {"index", "_ordered", "__init__"}

# Mutating dict methods, for the writer rule. Subscript assignment and `del`
# are not the only ways `_docs` moves.
_MUTATING_DICT_METHODS = {"pop", "popitem", "clear", "update", "setdefault"}


def _repo_root():
    # <repo>/src/schemagate/catalog.py -> parents[2] is <repo>
    return pathlib.Path(catalog_mod.__file__).resolve().parents[2]


def _tracked_python_files():
    """The tracked sources, and the two counts that say which set that is.

    `rglob` walks the working tree, which is not the repository: this
    project's .gitignore declares certify_oracle.py, complex_atp_test.py and
    drop_complex.py as local-only, and a reader in one of those would fail
    here as a red CI could not reproduce. `git ls-files` puts both rules on
    one definition, and returns (parsed, exempt) so the domain is stated
    rather than assumed -- a rule whose population is silent is the same
    failure as a comparison whose population is silent.
    """
    root = _repo_root()
    out = subprocess.run(["git", "-C", str(root), "ls-files", "*.py"],
                         capture_output=True, text=True, check=True)
    parsed, exempt = [], 0
    for rel in out.stdout.split("\n"):
        rel = rel.strip()
        if not rel:
            continue
        if rel.startswith(_READER_EXEMPT_DIRS):
            exempt += 1
            continue
        parsed.append((rel, root / rel))
    return parsed, exempt


def test_no_one_reads_order_without_the_rebuild():
    """The property that keeps the dirty window safe.

    Fails when anything reads `_order` directly instead of going through
    `_ordered()` -- the only way the divergence above can become observable.

    The walk covers the repository, not just catalog.py. An earlier version
    parsed this one module, which made it assert a property of a file while
    claiming one about the codebase: `benchmarks/fixture_1200.py` read
    `cat._order` with no guard and the green tick could not report it.

    This rule cannot see `getattr(self, "_order")` or any other dynamic
    access. No rule of this shape can.
    """
    files, exempt = _tracked_python_files()
    assert files, "the walk parsed no files -- a rule over an empty domain passes vacuously"
    offenders = {}
    for rel, path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        in_catalog = rel.endswith("src/schemagate/catalog.py")
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if in_catalog and node.name in _READER_EXEMPT_FUNCS:
                continue
            hits = [n.lineno for n in ast.walk(node)
                    if isinstance(n, ast.Attribute) and n.attr == "_order"
                    and isinstance(n.value, (ast.Name, ast.Attribute))]
            if hits:
                offenders[f"{rel}::{node.name}"] = hits
    assert not offenders, (
        f"({len(files)} parsed, {exempt} exempt) these read _order without going "
        f"through _ordered(), so they can see qnames that _docs no longer has: "
        + repr(offenders))


def test_every_writer_of_docs_marks_the_index_stale():
    """The other half, which the reader rule cannot imply.

    `_ordered()` rebuilds a catalogue somebody marked stale. It cannot rebuild
    an unmarked one, so "every reader rebuilds" is only safe while "every
    writer marks" also holds.

    Two things this rule got wrong on the first pass, both raised by howcani:

    Its domain was one module while the obligation is a property of the class.
    `rls.apply_policies` deletes from `catalog._docs` and was invisible to it
    -- the benchmark reader again, in the half that shipped with the fix. It
    now walks the same tracked file list the reader rule does.

    And it accepted any assignment to `_stale` as a mark, so `_stale = False`
    counted. A `_docs` mutation added to `index()` -- the one function that
    assigns False -- passed cleanly. The mark must now raise the flag: a bare
    `True`, not a name, a call, or a condition that may be false.

    A dict is also not only mutated by subscript. `catalog.py:586` calls
    `self._docs.pop(old, None)`, and counting only subscripts missed it --
    which is why howcani's own probe, a `.pop()` added to `index()`, still
    passed after the mark-side hardening he proposed for it.
    """
    files, exempt = _tracked_python_files()
    assert files, "the walk parsed no files -- a rule over an empty domain passes vacuously"
    offenders = {}
    for rel, path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            writes, marks = [], []
            for n in ast.walk(node):
                targets = getattr(n, "targets", []) if isinstance(n, (ast.Assign, ast.Delete)) else []
                for t in targets:
                    if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Attribute)
                            and t.value.attr == "_docs"):
                        writes.append(n.lineno)
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr in _MUTATING_DICT_METHODS
                        and isinstance(n.func.value, ast.Attribute)
                        and n.func.value.attr == "_docs"):
                    writes.append(n.lineno)
                if isinstance(n, ast.Assign):
                    raised = isinstance(n.value, ast.Constant) and n.value.value is True
                    for t in n.targets:
                        if isinstance(t, ast.Attribute) and t.attr == "_stale" and raised:
                            marks.append(n.lineno)
            if writes and not marks:
                offenders[f"{rel}::{node.name}"] = writes
    assert not offenders, (
        f"({len(files)} parsed, {exempt} exempt) these mutate _docs without "
        f"raising _stale, so _ordered() will not rebuild after them: "
        + repr(offenders))


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
