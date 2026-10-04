"""The ontology: concepts with synonyms, column mappings, rules, definitions and a hierarchy."""
import json

import pytest

from schemagate import Principal
from schemagate import config as sgconfig
from schemagate.demo_schema import demo_catalog
from schemagate.ontology import Ontology, Concept


def names(sel):
    return [h.doc.name for h in sel.hits]


def revenue_catalog():
    cat = demo_catalog()
    cat.concept("money in", maps=["v_monthly_revenue"])
    cat.concept("revenue", synonyms=["sales", "turnover"], maps=["billing_invoice.total_net"],
                filter="billing_invoice.status = 'issued'",
                definition="Invoiced net amount; drafts excluded.", broader=["money in"])
    return cat


def test_a_synonym_finds_the_concept_and_its_table():
    sel = revenue_catalog().select("turnover by month", top_k=6)
    assert names(sel)[0] == "billing_invoice"


def test_the_meaning_is_written_above_the_ddl():
    frag = revenue_catalog().select("turnover by month", top_k=6).prompt_fragment()
    head = frag.split("\n\n")[0]
    assert "billing_invoice.total_net" in head and "status = 'issued'" in head
    assert frag.index("only where") < frag.index("TABLE main.billing_invoice")


def test_a_broader_concept_adds_a_weaker_signal():
    cat = revenue_catalog()
    sel = cat.select("turnover by month", top_k=6)
    assert "v_monthly_revenue" in names(sel)
    # neighbours both ways
    c = cat.ontology.get("money in")
    assert [n.name for n in cat.ontology.neighbours(c)] == ["revenue"]


def test_no_meaning_line_when_the_question_uses_no_concept():
    sel = revenue_catalog().select("late shipments by carrier", top_k=6)
    assert sel.meanings == [] and not sel.prompt_fragment().startswith("-- What")


def test_an_unused_ontology_changes_nothing():
    plain, rich = demo_catalog(), revenue_catalog()
    for q in ("late shipments by carrier", "headcount per department", "who hasn't paid us yet"):
        assert [(h.doc.qname, h.reason) for h in plain.select(q, top_k=6).hits] == \
               [(h.doc.qname, h.reason) for h in rich.select(q, top_k=6).hits], q


def test_a_concept_never_reveals_a_hidden_table():
    cat = demo_catalog()                              # hr_compensation needs payroll
    cat.concept("pay", synonyms=["salary"], maps=["hr_compensation"], definition="Base pay per year.")
    analyst = cat.select("salary by employee", top_k=6, principal=Principal("okta:a"))
    assert "hr_compensation" not in names(analyst) and analyst.meanings == []
    payroll = cat.select("salary by employee", top_k=6, principal=Principal("okta:p", roles={"payroll"}))
    assert "hr_compensation" in names(payroll) and payroll.meanings


def test_a_meaning_never_names_a_withheld_column():
    cat = demo_catalog()
    cat.restrict_column("hr_compensation", "annual_amount", ["hr"])
    cat.concept("pay", synonyms=["salary"], maps=["hr_compensation.annual_amount"])
    payroll = Principal("okta:p", roles={"payroll"})
    sel = cat.select("salary by employee", top_k=6, principal=payroll)
    assert sel.meanings == [] and "annual_amount" not in sel.prompt_fragment()
    hr = Principal("okta:h", roles={"payroll", "hr"})
    assert cat.select("salary by employee", top_k=6, principal=hr).meanings


def test_a_definition_naming_a_withheld_column_is_dropped_too():
    cat = demo_catalog()
    cat.restrict_column("hr_compensation", "annual_amount", ["hr"])
    cat.concept("headcount", maps=["v_employee_headcount"],
                definition="Joins hr_compensation.annual_amount for cost")
    sel = cat.select("headcount by department", top_k=6, principal=Principal("okta:p", roles={"payroll"}))
    assert sel.meanings == []
    assert "annual_amount" not in sel.prompt_fragment()


def test_a_definition_naming_a_hidden_table_is_dropped():
    cat = demo_catalog()
    cat.concept("headcount", maps=["v_employee_headcount"], definition="See hr_compensation for pay.")
    sel = cat.select("headcount by department", top_k=6, principal=Principal("okta:a"))
    assert sel.meanings == []


def test_unknown_object_column_and_empty_name_are_errors():
    cat = demo_catalog()
    with pytest.raises(KeyError):
        cat.concept("revenue", maps=["billing_invoce"])
    with pytest.raises(KeyError):
        cat.concept("revenue", maps=["billing_invoice.total_nett"])
    with pytest.raises(ValueError):
        cat.concept(" -- ", maps=["billing_invoice"])


def test_concepts_merge_and_terms_are_concepts():
    cat = demo_catalog()
    cat.term("revenue", "billing_invoice")
    cat.concept("revenue", synonyms=["turnover"], maps=["v_monthly_revenue"])
    c = cat.ontology.get("revenue")
    assert c.synonyms == ["turnover"] and c.objects == ["main.billing_invoice", "main.v_monthly_revenue"]
    assert cat.terms() == {"revenue": ["main.billing_invoice", "main.v_monthly_revenue"]}


def test_check_reports_typos_loops_and_shared_phrases():
    o = Ontology()
    o.add(Concept("a", broader=["b"]))
    o.add(Concept("b", broader=["a"]))
    o.add(Concept("c", synonyms=["shared"], broader=["nope"]))
    o.add(Concept("d", synonyms=["shared"]))
    problems = " | ".join(o.check())
    assert "'nope' is not defined" in problems
    assert "broader than itself" in problems
    assert "claimed by" in problems


def test_round_trip_through_to_dict(tmp_path):
    cat = revenue_catalog()
    block = cat.ontology.to_dict()
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps({"ontology": block}), encoding="utf-8")
    again = demo_catalog()
    sgconfig.apply(again, sgconfig.load(str(p)))
    assert again.ontology.to_dict() == block


def _write(tmp_path, obj):
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


def test_the_config_block(tmp_path):
    cat = demo_catalog()
    sgconfig.apply(cat, sgconfig.load(_write(tmp_path, {"ontology": {"concepts": {
        "revenue": {"synonyms": ["turnover"], "maps": "billing_invoice.total_net",
                    "filter": "billing_invoice.status = 'issued'"}}}})))
    assert names(cat.select("turnover by month", top_k=6))[0] == "billing_invoice"


def test_the_config_block_refuses_typos(tmp_path):
    bad = [
        {"ontology": {"concepts": {"revenue": {"mapz": ["billing_invoice"]}}}},
        {"ontology": {"concepts": {"revenue": {"maps": ["billing_invoice"], "broader": ["money inn"]}}}},
        {"ontology": {"concepts": {"revenue": 42}}},
    ]
    for obj in bad:
        with pytest.raises(ValueError):
            sgconfig.apply(demo_catalog(), sgconfig.load(_write(tmp_path, obj)))
    with pytest.raises(KeyError):
        sgconfig.apply(demo_catalog(), sgconfig.load(_write(tmp_path,
                       {"ontology": {"concepts": {"revenue": {"maps": ["no_such_table"]}}}})))


def test_meanings_are_in_the_audit_record():
    d = revenue_catalog().select("turnover by month", top_k=6).to_dict()
    assert d["meanings"] and "total_net" in d["meanings"][0]
