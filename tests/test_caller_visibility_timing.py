# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Two boundaries a final-prompt check cannot see.

1. A caller who may see nothing. An empty selection proves the prompt is
   clean, but an embedding or reranking call made on the way could already
   have carried catalog text to a remote service. Recording fakes for both
   show what each one is handed during that caller's select().

2. A permission change on a catalog object that is reused -- on the ROLE-LIST
   path only (`Catalog.restrict`, the config file's `restrict`). A cache keyed
   on the caller alone would miss it: the identity is the same before and
   after, only what it may see changed. Revoking must take effect on the next
   call, and granting back must give exactly what a fresh catalog gives.

   The other path, permissions read from the database's GRANTs, makes a
   different claim: a snapshot, bounded by SCHEMAGATE_CATALOG_MAX_AGE, not
   the next call. Its tests are tests/test_catalog_max_age.py (controlled
   clock) and tests/freshness_e2e.py (a real GRANT and REVOKE).
"""
from __future__ import annotations

from schemagate import Catalog, HashingEmbedder, Principal
from schemagate.models import Column, ObjectDoc

ALICE = Principal("okta:alice", roles=frozenset({"sales"}))


def _docs():
    return [
        ObjectDoc(name="vt_invoices", kind="TABLE", description="Invoices sent to customers.",
                  columns=[Column(name="invoice_id", type="INT", comment="the invoice"),
                           Column(name="amount", type="NUMERIC", comment="amount billed")]),
        ObjectDoc(name="vt_salaries", kind="TABLE", description="Pay per employee; confidential.",
                  columns=[Column(name="employee_id", type="INT", comment="who is paid"),
                           Column(name="annual_amount", type="NUMERIC", comment="yearly pay")]),
        ObjectDoc(name="vt_customers", kind="TABLE", description="Customers and their regions.",
                  columns=[Column(name="customer_id", type="INT"), Column(name="region", type="TEXT")]),
    ]


class RecordingEmbedder(HashingEmbedder):
    def __init__(self):
        super().__init__()
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return super().embed(texts)


class RecordingReranker:
    def __init__(self):
        self.calls = []

    def complete(self, system, prompt, **kw):
        self.calls.append((system, prompt))
        return "1"


CATALOG_WORDS = ("vt_invoices", "vt_salaries", "vt_customers", "invoice_id", "annual_amount",
                 "employee_id", "customer_id", "confidential", "yearly pay", "amount billed")


def test_a_caller_who_sees_nothing_sends_no_catalog_text_to_scoring_services():
    emb, rr = RecordingEmbedder(), RecordingReranker()
    cat = Catalog(embedder=emb, name="vt-empty")
    cat.add_all(_docs())
    for d in _docs():
        cat.restrict(d.name, ["payroll"])          # nothing is visible to sales
    cat.select("warm the index", principal=Principal("okta:root", roles=frozenset({"payroll"})))
    emb.calls.clear()                              # index-time embedding is not this caller's call

    question = "total amount billed by region"
    sel = cat.select(question, principal=ALICE, reranker=rr)

    assert sel.objects == []
    assert sel.prompt_fragment() == ""
    sent = " ".join(t for call in emb.calls for t in call)
    assert question in sent, "the question is the one thing the embedder is expected to see"
    for w in CATALOG_WORDS:
        assert w not in sent.replace(question, ""), w
    assert rr.calls == [], "with no eligible object the reranker must not be called at all"


def test_the_reranker_only_ever_sees_allowed_objects():
    emb, rr = RecordingEmbedder(), RecordingReranker()
    cat = Catalog(embedder=emb, name="vt-rerank")
    cat.add_all(_docs())
    cat.restrict("vt_salaries", ["payroll"])
    cat.select("amount and pay per employee", principal=ALICE, reranker=rr)
    assert rr.calls, "the reranker must actually run, or this proves nothing"
    shown = " ".join(p for _, p in rr.calls)
    assert "vt_salaries" not in shown and "annual_amount" not in shown and "yearly pay" not in shown


def _names(sel):
    return sorted(d.name for d in sel.objects)


def test_role_list_revoke_on_a_reused_catalog_takes_effect_on_the_next_call():
    """Role-list path only: `restrict` changes the catalog in place and
    visibility is evaluated per call, so the next call sees the revoke. It
    says nothing about GRANTs read from the database, which are a snapshot
    bounded by SCHEMAGATE_CATALOG_MAX_AGE (see the module docstring)."""
    q = "pay per employee and invoices"
    cat = Catalog(name="vt-reuse")
    cat.add_all(_docs())
    # carol's membership (payroll) never changes. She is checked on the SAME
    # catalog object at every step, interleaved with alice, so the test holds
    # two properties at once: alice's view follows each restrict() on the next
    # call, and changing alice's view never touches carol's. Checking carol
    # once, after the revoke, could not tell "always visible to her" from
    # "survived that one transition".
    carol = Principal("okta:carol", roles=frozenset({"payroll"}))

    def sees(principal):
        return "vt_salaries" in _names(cat.select(q, top_k=3, principal=principal))

    assert sees(ALICE), "control before any change: alice (sales) did not get vt_salaries"
    assert sees(carol), "control before any change: carol (payroll) did not get vt_salaries"

    cat.restrict("vt_salaries", ["payroll"])        # transition 1: sales removed
    revoked = cat.select(q, top_k=3, principal=ALICE)
    assert "vt_salaries" not in _names(revoked), (
        f"transition 1, sales removed from vt_salaries: the next select for alice still returned it: {_names(revoked)}")
    assert "vt_salaries" not in revoked.prompt_fragment()
    assert "annual_amount" not in revoked.prompt_fragment()
    assert sees(carol), (
        "transition 1, sales removed from vt_salaries: carol (payroll, unchanged) lost it on the same catalog object")

    cat.restrict("vt_salaries", ["payroll", "sales"])   # transition 2: sales granted back
    assert sees(carol), (
        "transition 2, sales granted back on vt_salaries: carol (payroll, unchanged) lost it on the same catalog object")
    regranted = cat.select(q, top_k=3, principal=ALICE)

    fresh = Catalog(name="vt-fresh")
    fresh.add_all(_docs())
    fresh.restrict("vt_salaries", ["payroll", "sales"])
    expected = fresh.select(q, top_k=3, principal=ALICE)
    assert _names(regranted) == _names(expected), (
        f"transition 2, sales granted back: alice's reused catalog gave {_names(regranted)}, a fresh one {_names(expected)}")
    assert regranted.prompt_fragment() == expected.prompt_fragment()
