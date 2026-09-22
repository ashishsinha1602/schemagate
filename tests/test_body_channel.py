"""The body channel is `embed_text` minus the per-column comments. Asserted
at the document level, against what the index actually holds.

`_body_text` (catalog.py) is a second copy of `ObjectDoc.embed_text`
(models.py) with one part left out. The docstring says so; until this file
nothing enforced it, and the two can drift the moment someone adds a part to
one and not the other -- column types, a sampled value, the kind.

The relation is `_body_text(doc) == embed_text(doc with comments removed)`.
It is deliberately NOT written as `embed_text == _body_text + comments`:
embed_text orders its parts name, hint, description, column names, column
COMMENTS, definition -- the comments sit before the definition, not at the
end -- so on a view with both, `_body_text` is not even a prefix of
`embed_text`. A positional form passes on every table and fails only on
that view, which is why the property test's generator has to reach it.

Acceptance, run by hand before this file was committed (see the PR):
every guard here passes on the unmodified code; with `embed_text`
monkeypatched to append one more part, every guard fails; with the relation
swapped for the positional form inside the property test, the property test
fails. A guard that survives the mutation is dead and was rewritten.
"""
from __future__ import annotations

import copy

from hypothesis import example, given, settings
from hypothesis import strategies as st

from schemagate import Catalog
from schemagate.catalog import _body_text, _stem
from schemagate.embedder import tokenize
from schemagate.models import Column, ObjectDoc


def _without_comments(doc: ObjectDoc) -> ObjectDoc:
    d = copy.deepcopy(doc)
    for c in d.columns:
        c.comment = None
    return d


def _relation_holds(doc: ObjectDoc) -> None:
    assert _body_text(doc) == _without_comments(doc).embed_text()


# --- six shapes, each with a unique name so they never collapse in an index --

def test_table_without_comments():
    _relation_holds(ObjectDoc(name="bc_plain_orders", kind="TABLE", columns=[
        Column(name="order_id", type="INT"), Column(name="placed_on", type="DATE")]))


def test_table_with_comments():
    _relation_holds(ObjectDoc(name="bc_commented_orders", kind="TABLE", columns=[
        Column(name="order_id", type="INT", comment="the order"),
        Column(name="placed_on", type="DATE", comment="when it was placed")]))


def test_view_with_comments_and_definition():
    """The divergent shape: comments sit before the definition in embed_text,
    so _body_text is not a prefix of it."""
    doc = ObjectDoc(name="bc_v_open", kind="VIEW",
                    definition="SELECT order_id FROM orders WHERE reorder_point > 0",
                    columns=[Column(name="order_id", type="INT", comment="the order")])
    assert not doc.embed_text().startswith(_body_text(doc)), \
        "if this ever holds, the positional form would pass and this file would prove less"
    _relation_holds(doc)


def test_view_definition_only():
    _relation_holds(ObjectDoc(name="bc_v_totals", kind="VIEW",
                              definition="SELECT customer_id, SUM(amount) AS total FROM invoices GROUP BY customer_id"))


def test_hint_description_and_comments():
    _relation_holds(ObjectDoc(
        name="bc_hr_compensation", kind="TABLE", hint="salary history; restricted",
        description="One row per pay change per employee.",
        columns=[Column(name="employee_id", type="INT", comment="who"),
                 Column(name="annual_amount", type="NUMERIC", comment="the pay")]))


def test_no_columns():
    _relation_holds(ObjectDoc(name="bc_empty_shell", kind="TABLE"))


# --- the property, with a generator that reaches the divergent class -------

ident = st.from_regex(r"[a-z]{3,10}(_[a-z]{3,10}){0,2}", fullmatch=True)
text = st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=0, max_size=40)

columns = st.lists(st.builds(Column, name=ident, type=st.just("TEXT"),
                             comment=st.one_of(st.none(), text)),
                   min_size=0, max_size=4, unique_by=lambda c: c.name)

#: Three classes on purpose. `_identifiers` drops SQL keywords and any token
#: under three characters, so "SELECT a FROM b WHERE c > 0" reduces to ''
#: and a generator using only short identifiers never produces a definition
#: that contributes text -- the divergent shape is unreachable and the
#: positional form survives hundreds of examples. The third class carries
#: real identifiers and does reach it.
definitions = st.one_of(
    st.none(),
    st.just("SELECT a FROM b WHERE c > 0"),
    st.builds(lambda a, b: f"SELECT {a}, {b} FROM {a}_src WHERE {b} > 0", ident, ident),
)

docs = st.builds(ObjectDoc, name=ident, kind=st.sampled_from(["TABLE", "VIEW"]),
                 hint=st.one_of(st.none(), text), description=st.one_of(st.none(), text),
                 columns=columns, definition=definitions)


@settings(max_examples=200, deadline=None)
@given(doc=docs)
@example(doc=ObjectDoc(name="bc_v_open", kind="VIEW",
                       definition="SELECT reorder_point, order_id FROM orders",
                       columns=[Column(name="order_id", type="INT", comment="the order")]))
def test_body_is_embed_text_without_comments(doc):
    _relation_holds(doc)


# --- the call site: what _BM25 actually holds, after the index is built ----

def test_the_body_index_holds_exactly_that_text():
    """The index is lazy: after add_all, `_order` is empty and `_bm25` is
    None until the first select(). A loop over an empty order iterates
    nothing and passes, so the preconditions come first."""
    docs_ = [
        ObjectDoc(name="bc_idx_orders", kind="TABLE", columns=[
            Column(name="order_id", type="INT", comment="the order")]),
        ObjectDoc(name="bc_idx_v_open", kind="VIEW",
                  definition="SELECT reorder_point, order_id FROM bc_idx_orders",
                  columns=[Column(name="order_id", type="INT", comment="the order")]),
        ObjectDoc(name="bc_idx_shell", kind="TABLE"),
    ]
    cat = Catalog(name="body-channel")
    cat.add_all(docs_)
    assert cat._order == [] and cat._bm25 is None, "the index is built lazily; if not, this test's premise changed"
    cat.select("orders", top_k=3)
    assert cat._bm25 is not None
    assert set(cat._order) == {d.qname for d in docs_}          # a set, not a count
    by_name = {d.qname: d for d in docs_}
    checked = 0
    for i, qname in enumerate(cat._order):
        expected = [_stem(t) for t in tokenize(_without_comments(by_name[qname]).embed_text())]
        assert cat._bm25.docs[i] == expected, qname
        checked += 1
    assert checked == len(docs_)
