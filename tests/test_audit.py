"""The audit log: every identity decision recorded, nothing it must not hold.

Three properties carry the file. Every audited tool writes a record on
success *and* on refusal. The record never contains row data, withheld
column names, or a database URL. And the server-side hints a tool attaches
for the log (`_denied_reason`, `_tables`, ...) never reach the caller --
`describe_object` answers "missing" and "restricted" identically on purpose,
and the log knowing which must not undo that.
"""
from __future__ import annotations

import json
import threading

import pytest

from schemagate import mcp_server
from schemagate.audit import AuditLog, summarize


@pytest.fixture
def served(cat, db_url, monkeypatch):
    """The commerce fixture with one restriction, a database to query, and a
    fresh in-memory audit log."""
    cat.restrict("hr_compensation", ["payroll"])
    monkeypatch.delenv("SCHEMAGATE_AUDIT_LOG", raising=False)
    mcp_server.build_catalog(catalog=cat)
    monkeypatch.setattr(mcp_server, "_URL", db_url, raising=False)
    monkeypatch.setattr(mcp_server, "_ENGINE", None, raising=False)
    return mcp_server._audit()


def last(log: AuditLog):
    return log.recent(1)[0]


# --- every tool is recorded ------------------------------------------------

def test_select_schema_is_recorded_with_what_was_shown_and_withheld(served):
    mcp_server.select_schema("salary by employee", top_k=10, principal="okta:x", roles=["finance"])
    rec = last(served)
    assert rec["tool"] == "select_schema" and rec["ok"] is True
    assert rec["principal"] == "okta:x" and rec["roles"] == ["finance"]
    assert rec["question"] == "salary by employee"
    assert rec["selected"] == len(rec["objects"]) > 0
    assert rec["objects_withheld"] == 1           # hr_compensation, for this caller
    assert "hr_compensation" not in " ".join(rec["objects"])


def test_the_withheld_count_is_zero_for_the_caller_who_may_see_it(served):
    mcp_server.select_schema("salary by employee", top_k=10, principal="okta:hr", roles=["payroll"])
    assert last(served)["objects_withheld"] == 0


def test_list_objects_is_recorded(served):
    mcp_server.list_objects(principal="okta:x")
    rec = last(served)
    assert rec["tool"] == "list_objects" and rec["objects_withheld"] == 1


def test_describe_object_records_restricted_vs_missing_but_the_caller_cannot_tell(served):
    denied = mcp_server.describe_object("hr_compensation", principal="okta:x", roles=["finance"])
    rec_r = last(served)
    missing = mcp_server.describe_object("no_such_table", principal="okta:x")
    rec_m = last(served)
    # the caller: identical shape and wording
    assert set(denied) == set(missing) == {"error"}
    assert denied["error"].replace("hr_compensation", "?") == missing["error"].replace("no_such_table", "?")
    # the log: knows which was which
    assert rec_r["denied"] == "restricted" and rec_m["denied"] == "missing"
    assert served.stats["refused"] >= 2


def test_run_query_records_sql_tables_and_row_count_but_never_rows(served, db_url):
    import sqlite3
    # The fixture ships no data, so put one unmistakable value in and check
    # that it comes back to the caller and never appears in the record.
    marker = "ACCT-LEAK-CANARY-7f3a"
    c = sqlite3.connect(db_url[len("sqlite:///"):])
    c.execute("INSERT INTO crm_customer (id, account_number, segment) VALUES (9001, ?, 'smb')", (marker,))
    c.commit(); c.close()
    out = mcp_server.run_query("SELECT id, account_number FROM crm_customer WHERE id = 9001",
                               principal="okta:x", max_rows=3)
    assert out["row_count"] == 1 and out["rows"][0][1] == marker
    rec = last(served)
    assert rec["tool"] == "run_query" and rec["ok"] is True
    assert rec["sql"].startswith("SELECT") and "crm_customer" in rec["tables"]
    assert rec["row_count"] == 1 and rec["truncated"] is False
    assert "rows" not in rec and "columns" not in rec
    assert marker not in json.dumps(rec)


def test_run_query_refusals_are_recorded_with_the_reason(served):
    mcp_server.run_query("SELECT * FROM hr_compensation", principal="okta:x", roles=["finance"])
    rec = last(served)
    assert rec["ok"] is False and rec["refused"] == "out-of-scope"
    assert "hr_compensation" in rec["tables"]
    mcp_server.run_query("DELETE FROM hr_employee", principal="okta:x")
    assert last(served)["refused"] == "not-read-only"


def test_identity_errors_are_recorded_too(served):
    mcp_server.select_schema("anything", principal="no-namespace")
    rec = last(served)
    assert rec["ok"] is False and "namespaced" in rec["error"]


def test_health_and_refresh_are_not_identity_events(served):
    before = served.stats["records"]
    mcp_server.health()
    assert served.stats["records"] == before


# --- the hints never reach the caller ----------------------------------------

@pytest.mark.parametrize("call", [
    lambda: mcp_server.select_schema("salary", top_k=5, principal="okta:x"),
    lambda: mcp_server.list_objects(principal="okta:x"),
    lambda: mcp_server.describe_object("hr_compensation", principal="okta:x"),
    lambda: mcp_server.run_query("SELECT 1 AS n", principal="okta:x"),
    lambda: mcp_server.run_query("SELECT * FROM hr_compensation", principal="okta:x"),
])
def test_no_underscore_key_ever_leaves_the_server(served, call):
    out = call()
    assert not [k for k in out if k.startswith("_")], out.keys()


# --- health says what the log holds, not what is in it ------------------------

def test_health_reports_counts_only(served):
    mcp_server.select_schema("customers who owe money", top_k=5, principal="okta:jdoe")
    h = mcp_server.health()["audit"]
    assert h["file"] is None and h["records"] >= 1
    assert "jdoe" not in json.dumps(h) and "owe" not in json.dumps(h)


# --- the file ------------------------------------------------------------------

def test_file_is_off_unless_asked(monkeypatch):
    monkeypatch.delenv("SCHEMAGATE_AUDIT_LOG", raising=False)
    assert AuditLog.from_env().enabled is False
    assert AuditLog.from_env({"SCHEMAGATE_AUDIT_LOG": "0"}).enabled is False


def test_file_is_append_only_jsonl(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl")
    log.record({"ts": "t1", "tool": "select_schema", "ok": True})
    log.record({"ts": "t2", "tool": "run_query", "ok": False, "refused": "out-of-scope"})
    lines = (tmp_path / "a.jsonl").read_text("utf-8").splitlines()
    assert [json.loads(l)["ts"] for l in lines] == ["t1", "t2"]
    assert log.stats == {"records": 2, "refused": 1, "errors": 1, "write_failures": 0}


def test_default_path_and_explicit_path_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHEMAGATE_HOME", str(tmp_path))
    assert AuditLog.from_env({"SCHEMAGATE_AUDIT_LOG": "1"}).path == tmp_path / "audit.jsonl"
    assert AuditLog.from_env({"SCHEMAGATE_AUDIT_LOG": str(tmp_path / "x.jsonl")}).path == tmp_path / "x.jsonl"


def test_server_writes_the_file_when_configured(cat, tmp_path, monkeypatch):
    path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("SCHEMAGATE_AUDIT_LOG", str(path))
    cat.restrict("hr_compensation", ["payroll"])
    mcp_server.build_catalog(catalog=cat)
    mcp_server.select_schema("salary by employee", top_k=10, principal="okta:x")
    mcp_server.describe_object("hr_compensation", principal="okta:x")
    recs = list(AuditLog.read(path))
    assert [r["tool"] for r in recs] == ["select_schema", "describe_object"]
    assert recs[1]["denied"] == "restricted"
    assert mcp_server.health()["audit"]["file"] == str(path)
    # the reader filters
    assert list(AuditLog.read(path, principal="okta:nobody")) == []
    monkeypatch.delenv("SCHEMAGATE_AUDIT_LOG")
    mcp_server.build_catalog(catalog=cat)          # back to memory-only


def test_rotation_keeps_one_predecessor(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl", max_bytes=200)
    for i in range(40):
        log.record({"ts": f"t{i:03}", "tool": "run_query", "ok": True, "pad": "x" * 20})
    assert (tmp_path / "a.jsonl").exists() and (tmp_path / "a.jsonl.1").exists()
    assert log.stats["records"] == 40


def test_a_failed_write_never_reaches_the_caller(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl")
    log.path = tmp_path / "no_such_dir" / "deeper" / "a.jsonl"    # parent missing
    rec = log.record({"ts": "t", "tool": "run_query", "ok": True})
    assert rec["ok"] is True                                    # returned normally
    assert log.stats["write_failures"] == 1
    assert len(log.recent()) == 1                               # and still in memory


def test_concurrent_records_are_all_kept(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl")

    def worker(n):
        for i in range(50):
            log.record({"ts": f"{n}-{i}", "tool": "select_schema", "ok": True})
    ts = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert log.stats["records"] == 400
    assert len((tmp_path / "a.jsonl").read_text("utf-8").splitlines()) == 400


# --- summarize on its own ---------------------------------------------------------

def test_summarize_truncates_long_inputs_and_drops_rows():
    rec = summarize("run_query", {"principal": "okta:x", "sql": "S" * 9000},
                    {"sql": "S" * 9000, "rows": [[1, 2]], "columns": ["a", "b"],
                     "row_count": 1, "truncated": False})
    assert len(rec["sql"]) == 4000 and "rows" not in rec and "columns" not in rec
    rec = summarize("select_schema", {"question": "q" * 900, "principal": None}, {"selected": 0})
    assert len(rec["question"]) == 500 and rec["principal"] is None and rec["roles"] == []


# --- answer(): the fragment must actually reach the model --------------------

class _Recording:
    """A provider that records what it was asked and answers a fixed SELECT."""
    calls: list = []

    def __init__(self, model=None):
        self.model = model

    def complete(self, system, prompt, max_tokens=None):
        _Recording.calls.append((system, prompt))
        return "SELECT id FROM crm_customer"


def test_answer_hands_the_model_the_ddl_and_the_dialect(served, monkeypatch):
    from schemagate.ai import providers as _p
    monkeypatch.setattr(_p, "LocalProvider", _Recording)
    monkeypatch.setenv("SCHEMAGATE_MCP_PROVIDER", "local")
    monkeypatch.setenv("SCHEMAGATE_MCP_MODEL", "fake")
    _Recording.calls.clear()
    out = mcp_server.answer("which customers do we have", principal="okta:x", top_k=5)
    assert "error" not in out, out
    assert out["sql"] == "SELECT id FROM crm_customer" and "rows" in out
    system, prompt = _Recording.calls[-1]
    # the DDL: this was empty before the fix
    assert "TABLE " in prompt and "crm_customer" in prompt, prompt[:200]
    # the dialect, derived from the URL without opening a connection
    assert "dialect: sqlite" in system.lower()
    rec = last(served)
    assert rec["tool"] == "answer" and rec["sql"] == out["sql"] and rec["question"].startswith("which")
