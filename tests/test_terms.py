"""The glossary: business words mapped to objects with ``Catalog.term`` or the ``terms`` config block."""
import json

import pytest

from schemagate import Principal
from schemagate import config as sgconfig
from schemagate.demo_schema import demo_catalog

Q = "money we gave back to shoppers"


def names(cat, q, principal=None, top_k=6):
    return [h.doc.name for h in cat.select(q, top_k=top_k, principal=principal).hits]


def test_a_term_brings_its_object_in():
    cat = demo_catalog()
    assert "billing_credit_note" not in names(cat, Q)
    cat.term("gave back", "billing_credit_note")
    assert names(cat, Q)[0] == "billing_credit_note"


def test_plurals_fold_like_the_index():
    cat = demo_catalog()
    cat.term("refund", "billing_credit_note")
    assert "billing_credit_note" in names(cat, "refunds issued last quarter")


def test_a_phrase_must_appear_in_order():
    cat = demo_catalog()
    cat.term("gave back", "billing_credit_note")
    assert cat._terms_in("back we gave") == []
    assert [p for p, _ in cat._terms_in(Q)] == ["gave back"]


def test_only_the_most_specific_term_counts():
    cat = demo_catalog()
    cat.term("late", "billing_invoice")
    cat.term("arrived late", "ship_shipment")
    assert [p for p, _ in cat._terms_in("parcels that arrived late")] == ["arrived late"]
    assert [p for p, _ in cat._terms_in("invoices paid late")] == ["late"]


def test_a_term_never_widens_access():
    cat = demo_catalog()                     # hr_compensation needs payroll
    cat.term("salary", "hr_compensation")
    assert "hr_compensation" not in names(cat, "salary by employee", Principal("okta:analyst"))
    assert "hr_compensation" in names(cat, "salary by employee", Principal("okta:x", roles={"payroll"}))


def test_unknown_object_and_empty_phrase_are_errors():
    cat = demo_catalog()
    with pytest.raises(KeyError):
        cat.term("refund", "billing_credit_nte")
    with pytest.raises(ValueError):
        cat.term("  --  ", "billing_credit_note")


def test_a_glossary_the_question_does_not_use_changes_nothing():
    plain, glossed = demo_catalog(), demo_catalog()
    glossed.term("gave back", "billing_credit_note")
    glossed.term("depot", "inv_stock_level")
    for q in ("total revenue by month last year", "late shipments by carrier", "headcount per department"):
        a = [(h.doc.qname, h.reason) for h in plain.select(q, top_k=6).hits]
        b = [(h.doc.qname, h.reason) for h in glossed.select(q, top_k=6).hits]
        assert a == b, q


def test_the_budget_holds():
    cat = demo_catalog()
    for phrase, obj in (("gave back", "billing_credit_note"), ("shoppers", "crm_customer"),
                        ("money", "v_monthly_revenue")):
        cat.term(phrase, obj)
    ranked = [h for h in cat.select(Q, top_k=3).hits if h.reason != "fk"]
    assert len(ranked) <= 3


def test_terms_lists_the_glossary_and_repeats_merge():
    cat = demo_catalog()
    cat.term("revenue", "billing_invoice")
    cat.term("revenue", ["v_monthly_revenue", "billing_invoice"])
    assert cat.terms() == {"revenue": ["main.billing_invoice", "main.v_monthly_revenue"]}


def _write(tmp_path, obj):
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


def test_the_config_block_reaches_the_catalog(tmp_path):
    cat = demo_catalog()
    sgconfig.apply(cat, sgconfig.load(_write(tmp_path, {"terms": {"gave back": "billing_credit_note",
                                                                   "revenue": ["v_monthly_revenue"]}})))
    assert names(cat, Q)[0] == "billing_credit_note"


def test_the_config_block_rejects_typos(tmp_path):
    with pytest.raises(KeyError):
        sgconfig.apply(demo_catalog(), sgconfig.load(_write(tmp_path, {"terms": {"refund": "no_such_table"}})))
    with pytest.raises(ValueError, match="object name"):
        sgconfig.apply(demo_catalog(), sgconfig.load(_write(tmp_path, {"terms": {"refund": {"x": 1}}})))
