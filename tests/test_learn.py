"""Learning from SQL that ran, without learning anything it must not.

Two properties carry this file. A remembered query can only ever *add* to
what a caller gets: with nothing remembered the prompt is byte-identical to
before memory existed, and a pin from memory goes through the same
visibility gate a hand-written pin does. And a remembered query naming a
table the caller may not see is never shown to that caller as an example --
the SQL names the table, and the name is the disclosure.
"""
from __future__ import annotations

import json
import threading

import pytest

from schemagate import Catalog, Column, ObjectDoc, Principal
from schemagate.answer import _prompt_body, sql_prompt
from schemagate.catalog import default_embedder
from schemagate.learn import (Memory, format_examples, learn_from_audit,
                              referenced_tables)

EMB = default_embedder()


@pytest.fixture
def mem():
    return Memory(EMB)


# --- storing ---------------------------------------------------------------------

def test_remember_keeps_question_sql_and_the_tables_it_reads(mem):
    e = mem.remember("customers who owe money",
                     "SELECT c.id FROM crm_customer c JOIN billing_invoice i ON i.id_customer = c.id WHERE i.balance > 0")
    assert e["tables"] == ["billing_invoice", "crm_customer"]
    assert len(mem) == 1 and mem.stats["remembered"] == 1


def test_a_write_is_refused_on_the_way_in(mem):
    assert mem.remember("clean up", "DELETE FROM crm_customer") is None
    assert mem.remember("two", "SELECT 1; DROP TABLE x") is None
    assert len(mem) == 0 and mem.stats["rejected"] == 2


def test_the_same_question_again_replaces_its_earlier_answer(mem):
    mem.remember("how many customers", "SELECT COUNT(*) FROM crm_customer")
    mem.remember("How many customers ", "SELECT COUNT(id) FROM crm_customer")
    assert len(mem) == 1
    assert mem.similar("how many customers")[0][1]["sql"] == "SELECT COUNT(id) FROM crm_customer"


def test_forget_one_and_forget_all(mem):
    mem.remember("a", "SELECT 1 FROM t")
    mem.remember("b", "SELECT 2 FROM t")
    assert mem.forget("a") == 1 and len(mem) == 1
    assert mem.forget() == 1 and len(mem) == 0


def test_rows_are_never_part_of_an_entry(mem):
    e = mem.remember("q", "SELECT id FROM crm_customer")
    assert set(e) == {"ts", "question", "sql", "tables", "source"}


# --- similarity ------------------------------------------------------------------

def test_similar_finds_a_paraphrase_and_ignores_the_unrelated(mem):
    mem.remember("customers who owe money", "SELECT id FROM crm_customer WHERE balance > 0")
    mem.remember("warehouse stock below reorder point", "SELECT sku FROM inv_stock WHERE qty < reorder")
    hits = mem.similar("which customers owe us money")
    assert hits and hits[0][1]["question"] == "customers who owe money"
    assert all("stock" not in h[1]["question"] for h in hits)


def test_nothing_similar_means_nothing_not_the_nearest_junk(mem):
    mem.remember("warehouse stock below reorder point", "SELECT sku FROM inv_stock WHERE qty < reorder")
    assert mem.similar("employee salary by department") == []
    assert mem.pins_for("employee salary by department") == []


def test_pins_for_is_the_union_of_tables_from_similar_queries(mem):
    mem.remember("customers who owe money",
                 "SELECT c.id FROM crm_customer c JOIN billing_invoice i ON i.id_customer = c.id")
    assert mem.pins_for("customers that owe money") == ["billing_invoice", "crm_customer"]


# --- what the caller may be shown -------------------------------------------------

def test_examples_are_filtered_by_what_the_caller_can_see(mem):
    mem.remember("what do we pay people", "SELECT amount FROM hr_compensation")
    mem.remember("what do we pay people, by team", "SELECT e.team FROM hr_employee e")
    everyone = mem.examples_for("what do we pay people", visible=["main.hr_employee", "hr_compensation"])
    assert {q for q, _ in everyone} == {"what do we pay people", "what do we pay people, by team"}
    no_payroll = mem.examples_for("what do we pay people", visible=["main.hr_employee"])
    assert [q for q, _ in no_payroll] == ["what do we pay people, by team"]
    assert all("hr_compensation" not in s for _, s in no_payroll)


def test_a_tampered_stored_sql_is_refused_on_the_way_out(mem):
    mem.remember("q", "SELECT id FROM t")
    mem._entries[0]["sql"] = "SELECT id FROM t; DROP TABLE t"     # edited behind our back
    assert mem.examples_for("q", visible=["t"]) == []


def test_format_examples_is_empty_for_nothing_and_a_block_for_something():
    assert format_examples([]) == ""
    out = format_examples([("a question", "SELECT 1")])
    assert out.startswith("Queries that answered similar questions")
    assert "Question: a question\nSQL: SELECT 1" in out


def test_the_prompt_is_byte_identical_with_no_examples():
    assert _prompt_body("q", "DDL") == "Tables you may use:\n\nDDL\nQuestion: q\n"
    assert sql_prompt("q", "DDL", "sqlite") == sql_prompt("q", "DDL", "sqlite", examples=())


# --- pins go through the same gate as everything else -------------------------------

def test_a_pin_from_memory_never_admits_a_restricted_table(mem):
    cat = Catalog()
    cat.add(ObjectDoc(name="hr_compensation", columns=[Column("amount", "INT")], roles=["payroll"]))
    cat.add(ObjectDoc(name="hr_employee", columns=[Column("id", "INT")]))
    cat.index()
    mem.remember("what do we pay people", "SELECT amount FROM hr_compensation")
    pins = mem.pins_for("what do we pay people")
    assert pins == ["hr_compensation"]
    sel = cat.select("what do we pay people", top_k=5, principal=Principal("okta:x"), pin=pins)
    assert "hr_compensation" not in " ".join(sel.table_names)
    sel = cat.select("what do we pay people", top_k=5,
                     principal=Principal("okta:hr", roles={"payroll"}), pin=pins)
    assert any(h.reason == "pinned" and h.doc.name == "hr_compensation" for h in sel.hits)


# --- the file -------------------------------------------------------------------------

def test_off_disk_unless_asked(monkeypatch):
    monkeypatch.delenv("SCHEMAGATE_MEMORY", raising=False)
    assert Memory.from_env(EMB).enabled is False


def test_file_round_trip_and_tampered_lines_dropped(tmp_path):
    path = tmp_path / "m.jsonl"
    m1 = Memory(EMB, path=path)
    m1.remember("customers who owe money", "SELECT id FROM crm_customer WHERE balance > 0")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": "t", "question": "evil", "sql": "DELETE FROM crm_customer",
                             "tables": ["crm_customer"], "source": "api"}) + "\n")
        fh.write("not json\n")
    m2 = Memory(EMB, path=path)
    assert len(m2) == 1 and m2.stats["rejected"] == 2
    assert m2.similar("which customers owe money")[0][1]["question"] == "customers who owe money"


def test_default_path_is_per_catalog_under_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHEMAGATE_HOME", str(tmp_path))
    m = Memory.from_env(EMB, "prod-db", {"SCHEMAGATE_MEMORY": "1"})
    assert m.path == tmp_path / "memory" / "prod-db.jsonl"


def test_concurrent_remember_loses_nothing(tmp_path):
    m = Memory(EMB, path=tmp_path / "m.jsonl")

    def worker(n):
        for i in range(25):
            m.remember(f"question {n}-{i}", f"SELECT {i} FROM t{n}")
    ts = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(m) == 200 and m.stats["remembered"] == 200
    assert len((tmp_path / "m.jsonl").read_text("utf-8").splitlines()) == 200


# --- fed from the audit log ----------------------------------------------------------

def test_learn_from_audit_takes_only_successful_queries_with_a_question(mem):
    recs = [
        {"tool": "answer", "ok": True, "question": "customers who owe money",
         "sql": "SELECT id FROM crm_customer WHERE balance > 0", "tables": ["crm_customer"]},
        {"tool": "run_query", "ok": False, "question": "x", "sql": "SELECT * FROM nope"},
        {"tool": "run_query", "ok": True, "sql": "SELECT 1"},                  # no question
        {"tool": "select_schema", "ok": True, "question": "q"},               # not a query
        {"tool": "answer", "ok": True, "question": "wipe", "sql": "DELETE FROM t"},
    ]
    assert learn_from_audit(mem, recs) == 1
    assert mem.similar("which customers owe money")[0][1]["source"] == "audit"


def test_referenced_tables_ignores_ctes_strings_and_comments():
    sql = ("WITH recent AS (SELECT * FROM billing_invoice) -- from nowhere\n"
           "SELECT r.id FROM recent r JOIN crm_customer c ON c.id = r.id_customer "
           "WHERE c.note = 'from the join table'")
    assert referenced_tables(sql) == ["billing_invoice", "crm_customer"]
