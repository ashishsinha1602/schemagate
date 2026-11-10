"""`schemagate certify URL --golden`: a question set for the user's own schema.

Every table gets a question from its own words, every foreign key one that
needs both ends, every view one on the view; the answers are known by
construction. The report's job is the list of tables that cannot be found
even from their own description.
"""
import json
import sqlite3
import subprocess
import sys

import pytest

from schemagate import Catalog, Column, ForeignKey, ObjectDoc, Principal
from schemagate import golden


def _catalog():
    cat = Catalog(name="g")
    cat.add(ObjectDoc(name="customers", schema="s", columns=[
        Column("id", "INT", pk=True), Column("account_number", "TEXT"),
        Column("segment", "TEXT", comment="Market segment of the account"), Column("created_at", "TS")]))
    cat.add(ObjectDoc(name="invoices", schema="s", columns=[
        Column("id", "INT", pk=True), Column("customer_id", "INT"), Column("total_gross", "NUM"),
        Column("status", "TEXT")], foreign_keys=[ForeignKey(["customer_id"], "customers", ["id"])]))
    cat.add(ObjectDoc(name="payroll", schema="s", roles=["hr"], columns=[
        Column("id", "INT", pk=True), Column("annual_amount", "NUM")]))
    cat.add(ObjectDoc(name="v_paid", schema="s", kind="VIEW", definition="SELECT id FROM invoices WHERE status='paid'",
                      columns=[Column("id", "INT")]))
    return cat.index()


def test_one_question_per_table_join_and_view():
    items = golden.synthesize(_catalog())
    kinds = {(g.kind, tuple(g.tables)) for g in items}
    assert ("table", ("s.customers",)) in kinds
    assert ("table", ("s.invoices",)) in kinds
    assert ("join", ("s.invoices", "s.customers")) in kinds
    assert ("view", ("s.v_paid",)) in kinds
    assert ("table", ("s.payroll",)) not in kinds       # restricted: an anonymous caller never sees it


def test_questions_use_the_tables_words_and_distinctive_columns():
    by = {g.tables[0]: g for g in golden.synthesize(_catalog()) if g.kind == "table"}
    q = by["s.customers"].question
    assert q.startswith("customers:")
    assert "Market segment" in q and "account number" in q
    assert "id" not in q.split() and "created" not in q          # keys and housekeeping never
    assert by["s.invoices"].question == "invoices: total gross, status" or "total gross" in by["s.invoices"].question


def test_a_hint_or_description_beats_the_name():
    cat = _catalog()
    cat.hint("customers", "Customer master records. One row per account.")
    q = {g.tables[0]: g for g in golden.synthesize(cat) if g.kind == "table"}["s.customers"].question
    assert q.startswith("Customer master records:")


def test_a_hidden_table_gets_no_question_for_that_caller():
    analyst = Principal("db:A", roles=frozenset({"analyst"}))
    hr = Principal("db:H", roles=frozenset({"hr"}))
    assert not any("s.payroll" in g.tables for g in golden.synthesize(_catalog(), analyst))
    assert any("s.payroll" in g.tables for g in golden.synthesize(_catalog(), hr))


def test_run_reports_what_was_found_and_what_is_unreachable():
    cat = _catalog()
    items = golden.synthesize(cat) + [golden.Golden("nothing here", ["s.customers", "s.no_such"], "user")]
    rep = golden.run(cat, items, top_k=3)
    assert rep.found == len(items) - 1
    bad = [r for r in rep.results if not r.found]
    assert len(bad) == 1 and bad[0].missing == ["s.no_such"]
    assert rep.unreachable() == []                    # the miss was a user question, not a table's own
    text = str(rep)
    assert f"{rep.found} of {len(items)}" in text and "missing s.no_such" in text


def test_a_table_that_misses_its_own_question_is_named():
    cat = _catalog()
    # a table-kind question whose words all belong to another table: budget 1 goes to customers
    item = golden.Golden("customers account number market segment", ["s.invoices"], "table")
    rep = golden.run(cat, [item], top_k=1, expand_fks=False)
    assert rep.unreachable() == ["s.invoices"]
    assert "not found by their own words" in str(rep) and "s.invoices" in str(rep)


def test_save_and_load_round_trip(tmp_path):
    items = golden.synthesize(_catalog())
    p = tmp_path / "g.jsonl"
    assert golden.save(items, str(p)) == len(items)
    back = golden.load(str(p))
    assert [(g.question, g.tables, g.kind) for g in back] == [(g.question, g.tables, g.kind) for g in items]


def test_load_refuses_a_malformed_line(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"question": "x", "tables": []}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="bad.jsonl:1"):
        golden.load(str(p))
    p.write_text("not json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not JSON"):
        golden.load(str(p))


class _Provider:
    name = "fake"

    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def complete(self, system, prompt, max_tokens=1024):
        self.prompts.append(prompt)
        return self.reply


def test_paraphrase_replaces_questions_and_keeps_answers():
    items = golden.synthesize(_catalog())
    prov = _Provider(json.dumps([f"rewritten {i}" for i in range(len(items))]))
    out = golden.paraphrase(items, prov)
    assert [g.question for g in out] == [f"rewritten {i}" for i in range(len(items))]
    assert [g.tables for g in out] == [g.tables for g in items]
    assert "s.customers" in prov.prompts[0]           # the model is told which tables each must need


def test_a_bad_model_reply_keeps_the_originals():
    items = golden.synthesize(_catalog())
    for reply in ("not json at all", json.dumps(["too", "few"]), json.dumps([""] * len(items))):
        out = golden.paraphrase(items, _Provider(reply))
        assert [g.question for g in out] == [g.question for g in items]


def test_main_exit_code_follows_unreachable_tables(tmp_path, capsys):
    cat = _catalog()
    assert golden.main(cat, top_k=3) == 0
    assert "written from the schema's own words" in capsys.readouterr().out
    p = tmp_path / "q.jsonl"
    p.write_text(json.dumps({"question": "customers account number market segment",
                             "tables": ["s.invoices"], "kind": "table"}) + "\n", encoding="utf-8")
    cat.hint("invoices", "zzqx")
    code = golden.main(cat, questions_path=str(p), top_k=1)
    out = capsys.readouterr().out
    assert code == 1 and "not found by their own words" in out and "s.invoices" in out


def test_an_empty_schema_is_an_error_not_a_pass(capsys):
    cat = Catalog(name="empty")
    assert golden.main(cat) == 2
    out = capsys.readouterr().out
    assert "nothing to test" in out and "--schema" in out


def test_a_caller_who_sees_nothing_is_told_so(capsys):
    cat = Catalog(name="hidden")
    cat.add(ObjectDoc(name="payroll", schema="s", roles=["hr"], columns=[Column("id", "INT", pk=True)]))
    cat.index()
    assert golden.main(cat, principal=Principal("db:A", roles=frozenset({"analyst"}))) == 2
    assert "visible for db:A" in capsys.readouterr().out


def _sqlite(tmp_path):
    db = tmp_path / "own.db"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE customers (id INTEGER PRIMARY KEY, account_number TEXT, segment TEXT);
        CREATE TABLE invoices (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), total_gross REAL);
        CREATE VIEW v_big AS SELECT id FROM invoices WHERE total_gross > 100;
    """)
    con.commit()
    con.close()
    return f"sqlite:///{db.as_posix()}"


def test_the_cli_runs_the_golden_set_on_the_users_schema_and_creates_nothing(tmp_path):
    url = _sqlite(tmp_path)
    save = tmp_path / "q.jsonl"
    out = subprocess.run([sys.executable, "-m", "schemagate", "certify", url, "--golden", "--save", str(save),
                          "--top-k", "3"], capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stdout[-600:] + out.stderr[-600:]
    assert "4 question(s) written" in out.stdout and "4 of 4" in out.stdout
    assert "CERTIFIED" not in out.stdout                      # the fixture run did not happen
    lines = [json.loads(ln) for ln in save.read_text(encoding="utf-8").splitlines()]
    assert {tuple(x["tables"]) for x in lines} >= {("main.customers",), ("main.invoices", "main.customers")}
    from sqlalchemy import create_engine, inspect
    assert not [t for t in inspect(create_engine(url)).get_table_names() if t.startswith("schemagate_cert_")]
    # and the saved file runs back in
    again = subprocess.run([sys.executable, "-m", "schemagate", "certify", url, "--golden", str(save)],
                           capture_output=True, text=True, timeout=300)
    assert again.returncode == 0 and "4 question(s) from" in again.stdout


def test_without_the_flag_certify_is_unchanged(tmp_path):
    out = subprocess.run([sys.executable, "-m", "schemagate", "certify", f"sqlite:///{tmp_path/'c.db'}"],
                         capture_output=True, text=True, timeout=300)
    assert "CERTIFIED" in out.stdout and "golden:" not in out.stdout.split("PASS")[0]
