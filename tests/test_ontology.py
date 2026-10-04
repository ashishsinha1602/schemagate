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


# ------------------------------------------------------------------ learning

HISTORY = [
    ("refunds we issued last month", "SELECT * FROM billing_credit_note"),
    ("refunds per customer", "SELECT c.name FROM billing_credit_note n JOIN crm_customer c ON c.id = n.id_customer"),
    ("total refunds this year", "SELECT SUM(amount) FROM billing_credit_note"),
    ("how many orders this year", "SELECT COUNT(*) FROM sales_order"),
    ("how many invoices this year", "SELECT COUNT(*) FROM billing_invoice"),
]


def test_learning_suggests_the_domain_word_not_the_filler():
    cat = demo_catalog()
    found = cat.learn_concepts(HISTORY)
    pairs = {(s["phrase"], s["object"]) for s in found}
    assert ("refunds", "main.billing_credit_note") in pairs
    assert not any(s["phrase"] in ("how many", "this year", "year") for s in found)
    assert cat.ontology.get("refunds") is None          # nothing applied without apply=True


def test_learning_skips_words_the_name_already_has():
    cat = demo_catalog()
    found = cat.learn_concepts(HISTORY + [("invoices overdue", "SELECT * FROM billing_invoice")])
    assert not any(s["phrase"] == "invoices" for s in found)


def test_learning_applies_as_learned_concepts_that_obey_access():
    cat = demo_catalog()
    cat.learn_concepts([("salary bands", "SELECT * FROM hr_compensation"),
                        ("salary rises", "SELECT * FROM hr_compensation")], apply=True)
    assert cat.ontology.get("salary").source == "learned"
    assert "hr_compensation" not in names(cat.select("salary by employee", top_k=6, principal=Principal("okta:a")))


def test_learning_reads_a_memory(tmp_path):
    from schemagate.learn import Memory
    cat = demo_catalog()
    mem = Memory(cat.embedder, path=tmp_path / "mem.jsonl")
    for q, sql in HISTORY:
        mem.remember(q, sql)
    assert any(s["object"] == "main.billing_credit_note" for s in cat.learn_concepts(mem))


def test_unknown_tables_in_history_are_skipped():
    cat = demo_catalog()
    assert cat.learn_concepts([("ghost rows", "SELECT * FROM no_such_table")] * 3) == []


def test_names_resolve_in_either_case():
    cat = demo_catalog()
    cat.concept("revenue", maps=["BILLING_INVOICE.TOTAL_NET", "Main.V_Monthly_Revenue"])
    c = cat.ontology.get("revenue")
    assert c.columns == [("main.billing_invoice", "total_net")] and c.objects == ["main.v_monthly_revenue"]


def test_history_sql_in_every_dialects_quoting():
    from schemagate.learn import referenced_tables as refs
    assert refs('SELECT * FROM "main"."billing_credit_note"') == ["billing_credit_note"]
    assert refs("SELECT * FROM [dbo].[billing_credit_note] n JOIN [dbo].[crm_customer] c ON 1=1") == \
        ["billing_credit_note", "crm_customer"]
    assert refs("select * from `db`.`billing_credit_note`") == ["billing_credit_note"]
    assert refs('SELECT * FROM "Order Details" o') == ["order details"]
