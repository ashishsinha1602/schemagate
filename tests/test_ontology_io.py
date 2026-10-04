"""Importing an existing ontology: dbt semantic manifest, Snowflake semantic model, CSV glossary."""
import json

import pytest

from schemagate.demo_schema import demo_catalog
from schemagate.ontology_io import import_csv, import_dbt, import_snowflake, _dbt_filter

DBT = {
    "semantic_models": [
        {"name": "invoices", "description": "One row per invoice.",
         "node_relation": {"alias": "billing_invoice", "schema_name": "main"},
         "entities": [{"name": "invoice", "type": "primary", "expr": "id"}],
         "measures": [{"name": "net_revenue", "label": "Net revenue", "agg": "sum", "expr": "total_net",
                       "description": "Invoiced amount before tax."}]},
        {"name": "ghosts", "node_relation": {"alias": "no_such_table"}, "measures": []},
    ],
    "metrics": [
        {"name": "issued_revenue", "label": "Issued revenue", "type": "simple",
         "type_params": {"measure": {"name": "net_revenue"}},
         "filter": {"where_filters": [{"where_sql_template": "{{ Dimension('invoice__status') }} = 'issued'"}]},
         "description": "Revenue from issued invoices only."},
    ],
}

SNOWFLAKE = {
    "name": "commerce",
    "tables": [
        {"name": "invoices", "synonyms": ["bills"], "description": "Customer invoices.",
         "base_table": {"database": "DB", "schema": "main", "table": "billing_invoice"},
         "facts": [{"name": "net amount", "synonyms": ["turnover"], "expr": "total_net"}],
         "measures": [{"name": "gross revenue", "expr": "SUM(total_gross)"}],
         "filters": [{"name": "issued", "synonyms": ["final invoices"], "expr": "status = 'issued'"}]},
        {"name": "ghosts", "base_table": {"table": "no_such_table"}},
    ],
    "verified_queries": [{"name": "q1", "question": "turnover last month",
                          "sql": "SELECT SUM(total_net) FROM billing_invoice"}],
}


def test_dbt_measures_metrics_and_entities(tmp_path):
    p = tmp_path / "semantic_manifest.json"
    p.write_text(json.dumps(DBT), encoding="utf-8")
    cat = demo_catalog()
    rep = import_dbt(cat, p)
    assert {"invoice", "Net revenue", "Issued revenue"} <= set(rep.added)
    assert any("no_such_table" in s for s in rep.skipped)
    c = cat.ontology.get("issued revenue")
    assert c.columns == [("main.billing_invoice", "total_net")] and c.filter == "status = 'issued'"
    assert c.source == "dbt"
    sel = cat.select("issued revenue by month", top_k=6)
    assert sel.hits[0].doc.name == "billing_invoice" and "status = 'issued'" in sel.prompt_fragment()


def test_dbt_filter_templates_become_sql():
    assert _dbt_filter("{{ Dimension('order__status') }} = 'paid'") == "status = 'paid'"
    assert _dbt_filter(None) is None


def test_snowflake_json(tmp_path):
    p = tmp_path / "model.json"
    p.write_text(json.dumps(SNOWFLAKE), encoding="utf-8")
    cat = demo_catalog()
    rep = import_snowflake(cat, p)
    assert {"invoices", "net amount", "gross revenue", "issued"} <= set(rep.added)
    assert rep.examples == [("turnover last month", "SELECT SUM(total_net) FROM billing_invoice")]
    assert cat.ontology.get("net amount").columns == [("main.billing_invoice", "total_net")]
    assert "computed as SUM(total_gross)" in cat.ontology.get("gross revenue").definition
    assert cat.select("turnover by month", top_k=6).hits[0].doc.name == "billing_invoice"


def test_snowflake_yaml(tmp_path):
    yaml = pytest.importorskip("yaml")
    p = tmp_path / "model.yaml"
    p.write_text(yaml.safe_dump(SNOWFLAKE), encoding="utf-8")
    rep = import_snowflake(demo_catalog(), p)
    assert "issued" in rep.added


def test_csv_with_purview_headers(tmp_path):
    p = tmp_path / "glossary.csv"
    p.write_text(
        "Name,Nick Name,Status,Definition,Parent Term Name,Table,Column\n"
        "Money in,,Approved,All incoming money,,v_monthly_revenue,\n"
        "Refund,Credit note;Money back,Approved,Money returned to a customer,Money out,billing_credit_note,\n"
        "Net revenue,Turnover,Approved,Issued invoices before tax,Money in,billing_invoice,total_net\n"
        "Ghost,,Draft,Not in this database,,no_such_table,\n"
        "Money out,,Approved,All outgoing money,,,\n",
        encoding="utf-8")
    cat = demo_catalog()
    rep = import_csv(cat, p)
    assert {"Money in", "Refund", "Net revenue", "Money out"} <= set(rep.added)
    assert any("no_such_table" in s for s in rep.skipped)
    assert cat.ontology.get("refund").synonyms == ["Credit note", "Money back"]
    assert cat.ontology.get("net revenue").broader == ["Money in"]
    assert cat.ontology.check() == []
    assert cat.select("money back to customers", top_k=6).hits[0].doc.name == "billing_credit_note"


def test_csv_without_a_term_column_is_an_error(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text("Foo,Bar\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no term column"):
        import_csv(demo_catalog(), p)
