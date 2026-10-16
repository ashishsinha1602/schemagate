# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""A definition that cites another term brings that term's definition with it.

"partner sales is revenue on partner orders" was unusable alone: the model got the channel filter
right and invented what revenue means. All six questions a full glossary still missed on the
planted-definitions benchmark had that shape; with cited definitions followed, it scored 21/21.
Visibility applies to a cited concept exactly as to a matched one.
"""
from schemagate import Catalog, Column, ObjectDoc, Principal
from schemagate.ontology import Concept, Ontology


def _onto(*concepts):
    o = Ontology()
    for c in concepts:
        o.add(c)
    return o


def test_a_cited_term_follows_the_one_that_cites_it():
    o = _onto(Concept("revenue", definition="completed orders net of refunds"),
              Concept("partner sales", definition="revenue on partner orders"))
    names = [c.name for c, _ in o.with_cited(o.match("what were partner sales"))]
    assert names == ["partner sales", "revenue"]


def test_chains_are_followed_and_loops_end():
    o = _onto(Concept("aov", definition="net revenue per order"),
              Concept("net revenue", definition="gross revenue minus refunds"),
              Concept("gross revenue", definition="sum of line amounts; see aov"))   # cites back
    names = [c.name for c, _ in o.with_cited(o.match("what is the aov"))]
    assert names == ["aov", "net revenue", "gross revenue"]


def test_depth_limits_the_chain():
    o = _onto(Concept("a", definition="uses b"), Concept("b", definition="uses c"),
              Concept("c", definition="uses d"), Concept("d", definition="plain"))
    assert [c.name for c, _ in o.with_cited(o.match("a"), depth=1)] == ["a", "b"]


def test_nothing_cited_leaves_the_match_unchanged():
    o = _onto(Concept("churn", definition="ended with no new subscription within 30 days"))
    m = o.match("how many churn")
    assert o.with_cited(m) == m


def _cat():
    cat = Catalog()
    cat.add(ObjectDoc(name="orders", columns=[Column("id", "INT"), Column("channel", "TEXT")]))
    cat.add(ObjectDoc(name="revenue_ledger", columns=[Column("order_id", "INT"), Column("amount", "REAL")]))
    cat.index()
    cat.concept("revenue", maps=["revenue_ledger"], definition="revenue is SUM(revenue_ledger.amount)")
    cat.concept("partner sales", maps=["orders"], definition="revenue on orders with channel = 'partner'")
    return cat


def test_the_cited_definition_reaches_the_prompt():
    cat = _cat()
    on = cat.select("what were partner sales", top_k=4)
    assert any("revenue_ledger.amount" in m for m in on.meanings)
    assert "revenue_ledger" in {n.split(".")[-1] for n in on.table_names}
    cat.cite_definitions = False
    off = cat.select("what were partner sales", top_k=4)
    assert not any("revenue_ledger.amount" in m for m in off.meanings)


def test_a_cited_definition_never_reveals_a_hidden_table():
    cat = _cat()
    cat.restrict("revenue_ledger", ["finance"])
    who = Principal("okta:sales", roles=frozenset({"sales"}))
    sel = cat.select("what were partner sales", top_k=4, principal=who)
    assert "revenue_ledger" not in {n.split(".")[-1] for n in sel.table_names}
    assert not any("revenue_ledger" in m for m in sel.meanings)
    assert "revenue_ledger" not in sel.prompt_fragment()
    fin = cat.select("what were partner sales", top_k=4,
                     principal=Principal("okta:fin", roles=frozenset({"finance"})))
    assert any("revenue_ledger.amount" in m for m in fin.meanings)
