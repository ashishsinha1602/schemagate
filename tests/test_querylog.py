"""Joins, co-reads and filters learned from a query log, with no value ever kept."""
import json
import sys

import pytest
from sqlalchemy import create_engine, text

from schemagate import Catalog, Principal
from schemagate.cli import main
from schemagate.models import Column, ForeignKey, ObjectDoc
from schemagate.querylog import LogUnavailable, mine, read

pytest.importorskip("sqlglot")

HR = Principal("okta:hr", roles=frozenset({"hr"}))
ANALYST = Principal("okta:a", roles=frozenset({"analyst"}))


def shop():
    cat = Catalog(name="log")
    cat.add_all([
        ObjectDoc("product", columns=[Column("id", "INT", pk=True), Column("sku", "TEXT")]),
        ObjectDoc("invoice_line", columns=[Column("id", "INT", pk=True), Column("product_id", "INT"),
                                           Column("qty", "INT")]),
        ObjectDoc("customer", columns=[Column("id", "INT", pk=True), Column("account_number", "TEXT"),
                                       Column("region", "TEXT")]),
        ObjectDoc("invoice", columns=[Column("id", "INT", pk=True), Column("id_customer", "INT"),
                                      Column("status", "TEXT")],
                  foreign_keys=[ForeignKey(["id_customer"], "customer", ["id"])]),
        ObjectDoc("payroll", columns=[Column("emp", "INT", pk=True), Column("pay", "INT")]),
        ObjectDoc("audit", columns=[Column("msg", "TEXT"), Column("emp", "INT")]),
    ])
    cat.index()
    return cat


JOIN = "SELECT l.qty, p.sku FROM invoice_line l JOIN product p ON l.product_id = p.id"
SECRET = "SELECT c.region FROM customer c WHERE c.account_number = 'SECRET-ACCT-9' AND c.region IN ('EU', 'US')"
IMPLICIT = "SELECT i.id FROM invoice i, customer c WHERE i.id_customer = c.id AND i.status = 'paid'"


# ---------------------------------------------------------------- mining

def test_a_join_in_on_is_found_with_its_columns():
    facts = mine(shop(), [(JOIN, 3)])
    assert facts.joins == {("invoice_line", "product_id", "product", "id"): 3}
    assert facts.together == {frozenset({"invoice_line", "product"}): 3}


def test_an_implicit_join_in_where_is_found_too():
    facts = mine(shop(), [(IMPLICIT, 1)])
    assert ("customer", "id", "invoice", "id_customer") in facts.joins


def test_the_same_join_written_both_ways_round_is_one_join():
    facts = mine(shop(), [(JOIN, 1), ("SELECT 1 FROM product p JOIN invoice_line l ON p.id = l.product_id", 2)])
    assert facts.joins == {("invoice_line", "product_id", "product", "id"): 3}


def test_no_value_from_a_statement_is_kept():
    facts = mine(shop(), [(SECRET, 1)])
    kept = json.dumps({"joins": list(facts.joins), "filters": {q: list(c) for q, c in facts.filters.items()},
                       "skipped": facts.skipped})
    assert "SECRET" not in kept and "EU" not in kept and "ACCT" not in kept
    assert set(facts.filters["customer"]) == {("account_number", "account_number = ?"), ("region", "region IN (?, ?)")}


def test_a_filter_is_kept_per_table_without_its_alias():
    facts = mine(shop(), [(IMPLICIT, 2)])
    assert facts.filters["invoice"] == {("status", "status = ?"): 2}


def test_a_statement_that_writes_is_skipped():
    facts = mine(shop(), [("UPDATE invoice SET status = 'paid' WHERE id = 1", 1), ("DELETE FROM payroll", 1)])
    assert not facts.joins and facts.used == 0 and len(facts.skipped) == 2


def test_a_statement_that_cannot_be_parsed_is_skipped_not_guessed():
    facts = mine(shop(), [("SELECT FROM WHERE ((", 1)])
    assert facts.used == 0 and any("parsed" in s for s in facts.skipped)


def test_an_unknown_table_is_ignored():
    facts = mine(shop(), [("SELECT 1 FROM elsewhere e JOIN product p ON e.pid = p.id", 1)])
    assert not facts.joins and facts.used == 1


def test_a_cte_is_not_a_table():
    facts = mine(shop(), [("WITH recent AS (SELECT id FROM invoice) SELECT r.id FROM recent r JOIN customer c ON r.id = c.id", 1)])
    assert all("recent" not in j for j in facts.joins) and frozenset({"customer", "invoice"}) in facts.together


def test_a_cte_named_like_a_real_table_is_still_not_that_table():
    sql = "WITH product AS (SELECT id FROM invoice) SELECT p.id FROM product p JOIN customer c ON p.id = c.id"
    facts = mine(shop(), [(sql, 1)])
    assert not any("product" in j for j in facts.joins)
    assert all("product" not in pair for pair in facts.together)


def test_a_column_compared_with_itself_is_not_a_join():
    facts = mine(shop(), [("SELECT 1 FROM product p WHERE p.id = p.id", 1)])
    assert not facts.joins


def test_a_single_table_statement_needs_no_alias_for_its_filter():
    facts = mine(shop(), [("SELECT id FROM invoice WHERE status = 'x'", 1)])
    assert facts.filters["invoice"] == {("status", "status = ?"): 1}


def test_the_count_of_a_statement_is_its_weight():
    facts = mine(shop(), [(JOIN, 40)])
    assert facts.joins[("invoice_line", "product_id", "product", "id")] == 40


def test_without_sqlglot_nothing_is_read_and_it_says_so(monkeypatch):
    monkeypatch.setitem(sys.modules, "sqlglot", None)
    facts = mine(shop(), [(JOIN, 1)])
    assert not facts and any("sqlglot" in s for s in facts.skipped)


# --------------------------------------------------------------- applying

def test_a_recurring_join_onto_a_key_becomes_an_inferred_foreign_key():
    cat = shop()
    report = cat.learn_from_log([JOIN, JOIN])
    fk = cat._docs["invoice_line"].foreign_keys
    assert [(f.columns, f.ref_table, f.ref_columns, f.inferred) for f in fk] == [(["product_id"], "product", ["id"], True)]
    assert report.keys_added == ["invoice_line.product_id -> product.id (seen 2 times)"]


def test_the_new_key_is_followed_by_fk_expansion():
    cat = shop()
    before = {h.doc.name for h in cat.select("line quantities", top_k=1).hits}
    cat.learn_from_log([JOIN, JOIN])
    after = {h.doc.name for h in cat.select("line quantities", top_k=1).hits}
    assert "product" not in before and after == {"invoice_line", "product"}


def test_a_join_seen_once_is_not_enough():
    cat = shop()
    report = cat.learn_from_log([JOIN])
    assert not cat._docs["invoice_line"].foreign_keys and any("fewer than 2" in s for s in report.keys_skipped)
    assert cat.learn_from_log([JOIN], min_count=1).keys_added


def test_a_join_between_two_non_keys_is_not_a_foreign_key():
    cat = shop()
    report = cat.learn_from_log(["SELECT 1 FROM audit a JOIN payroll p ON a.msg = p.pay"] * 2)
    assert not report.keys_added and any("neither side" in s for s in report.keys_skipped)
    assert cat.query_log.joins                      # still in the graph's facts


def test_a_declared_foreign_key_is_not_added_twice():
    cat = shop()
    report = cat.learn_from_log([IMPLICIT] * 2)
    assert len(cat._docs["invoice"].foreign_keys) == 1 and any("already" in s for s in report.keys_skipped)


def test_apply_false_changes_nothing():
    cat = shop()
    report = cat.learn_from_log([JOIN] * 2, apply=False)
    assert report.keys_added and not cat._docs["invoice_line"].foreign_keys and cat.query_log is None


def test_the_report_reads_as_a_summary():
    text_ = str(shop().learn_from_log([JOIN, JOIN, SECRET]))
    assert "3 statement(s) read" in text_ and "1 join(s) added" in text_ and "SECRET" not in text_


# ------------------------------------------------------------------ graph

def test_log_joins_and_co_reads_are_edges_with_counts():
    cat = shop()
    cat.learn_from_log([JOIN] * 3 + [IMPLICIT])
    g = cat.graph()
    joins = [e for e in g.edges if e.label == "JOINS" and e.props.get("via") == "query log"]
    assert any(e.source == "object:invoice_line" and e.target == "object:product" and e.props["count"] == 3 for e in joins)
    assert any(e.label == "QUERIED_WITH" and {e.source, e.target} == {"object:customer", "object:invoice"} for e in g.edges)
    assert g.nodes["object:invoice"].props["common_filters"] == ["status = ?"]


def test_log_edges_obey_visibility():
    cat = shop()
    cat.restrict("product", ["hr"])
    cat.restrict_column("invoice", "status", ["hr"])
    cat.learn_from_log([JOIN] * 2 + [IMPLICIT])
    g = cat.graph(ANALYST)
    assert "object:product" not in g.nodes and "sku" not in g.to_json().lower()
    assert not [e for e in g.edges if e.label in ("JOINS", "QUERIED_WITH") and "product" in e.target]
    assert "common_filters" not in g.nodes["object:invoice"].props
    assert "common_filters" in cat.graph(HR).nodes["object:invoice"].props


def test_a_join_on_a_withheld_column_is_not_an_edge():
    cat = shop()
    cat.restrict_column("invoice_line", "product_id", ["hr"])
    cat.learn_from_log([JOIN] * 2)
    assert not [e for e in cat.graph(ANALYST).edges if e.label == "JOINS"]
    assert [e for e in cat.graph(HR).edges if e.label == "JOINS"]


# ---------------------------------------------------------------- reading

def test_a_jsonl_file_and_a_sql_file_both_read(tmp_path):
    j = tmp_path / "log.jsonl"
    j.write_text(json.dumps({"sql": JOIN, "count": 5}) + "\n" + json.dumps({"query": IMPLICIT}) + "\n", encoding="utf-8")
    assert read(j) == [(JOIN, 5), (IMPLICIT, 1)]
    s = tmp_path / "log.sql"
    s.write_text(f"{JOIN};\n{IMPLICIT};\n", encoding="utf-8")
    assert read(s) == [(JOIN, 1), (IMPLICIT, 1)]


def test_the_limit_bounds_every_source(tmp_path):
    s = tmp_path / "log.sql"
    s.write_text(";\n".join([JOIN] * 10), encoding="utf-8")
    assert len(read(s, limit=3)) == 3 and len(read([JOIN] * 10, limit=4)) == 4


def test_sqlite_has_no_store_and_says_so(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/x.db")
    with pytest.raises(LogUnavailable, match="file of SQL"):
        read(engine)


def test_a_store_that_cannot_be_read_names_what_is_missing(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/x.db")
    monkeypatch.setattr(engine.dialect, "name", "postgresql")
    with pytest.raises(LogUnavailable, match="pg_stat_statements"):
        read(engine)


# ---------------------------------------------------------------- commands

@pytest.fixture
def url(tmp_path):
    u = f"sqlite:///{tmp_path}/g.db"
    engine = create_engine(u)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE product (id INTEGER PRIMARY KEY, sku TEXT)"))
        # prod_ref follows no naming convention, so only the log can say how it joins
        conn.execute(text("CREATE TABLE invoice_line (id INTEGER PRIMARY KEY, prod_ref INTEGER, qty INTEGER)"))
    engine.dispose()
    return u


JOIN_REF = "SELECT l.qty, p.sku FROM invoice_line l JOIN product p ON l.prod_ref = p.id"


def test_bootstrap_infers_a_conventional_key_by_name_so_the_log_only_confirms_it(tmp_path, capsys):
    u = f"sqlite:///{tmp_path}/n.db"
    engine = create_engine(u)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE product (id INTEGER PRIMARY KEY, sku TEXT)"))
        conn.execute(text("CREATE TABLE invoice_line (id INTEGER PRIMARY KEY, product_id INTEGER)"))
    engine.dispose()
    cat = Catalog().bootstrap(u)
    report = cat.learn_from_log([JOIN, JOIN])
    assert not report.keys_added and any("already a foreign key" in s for s in report.keys_skipped)
    assert len(cat._docs["main.invoice_line"].foreign_keys) == 1


def test_the_graph_command_learns_from_a_log_file(url, tmp_path, capsys):
    log = tmp_path / "log.sql"
    log.write_text(f"{JOIN_REF};\n{JOIN_REF};\n", encoding="utf-8")
    assert main(["graph", "--url", url, "--query-log", str(log)]) == 0
    out = capsys.readouterr()
    assert '"via": "query log"' in out.out and "1 join(s) added" in out.err


def test_the_graph_command_reports_an_unreadable_store_and_carries_on(url, capsys):
    assert main(["graph", "--url", url, "--query-log"]) == 0
    assert "query log:" in capsys.readouterr().err


def test_ontology_pull_takes_the_log_too(url, tmp_path, capsys):
    log = tmp_path / "log.sql"
    log.write_text(f"{JOIN_REF};\n{JOIN_REF};\n", encoding="utf-8")
    cfg = tmp_path / "catalog.json"
    cfg.write_text("{}", encoding="utf-8")
    assert main(["ontology", "pull", "--url", url, "--config", str(cfg), "--query-log", str(log)]) == 0
    assert "1 join(s) added" in capsys.readouterr().err


def test_the_server_reads_the_store_only_when_asked_and_survives_its_absence(url, monkeypatch, caplog):
    from schemagate import mcp_server
    monkeypatch.delenv("SCHEMAGATE_QUERY_LOG", raising=False)
    with caplog.at_level("WARNING", logger="schemagate.mcp"):
        assert mcp_server._reflect(url, None).query_log is None
    assert not any("query log" in r.getMessage() for r in caplog.records), "the store was read without being asked"
    monkeypatch.setenv("SCHEMAGATE_QUERY_LOG", "1")
    with caplog.at_level("WARNING", logger="schemagate.mcp"):
        assert mcp_server._reflect(url, None).query_log is None
    assert any("query log" in r.getMessage() for r in caplog.records)
