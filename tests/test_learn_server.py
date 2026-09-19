"""Memory in front of the server, the CLI and the Studio.

`test_learn.py` proves the memory. This proves the three call sites use it,
and -- the half that matters -- that memory can only add to what a caller
gets, never widen it: a remembered query that reads a restricted table is
pinned only for a caller who may see it, and shown as an example only to
that caller.
"""
from __future__ import annotations

import json

import pytest

from schemagate import Catalog, mcp_server
from schemagate.ai import providers as P
from schemagate.demo_schema import create_demo_db
from schemagate.learn import Memory

REMEMBERED = "SELECT annual_amount FROM hr_compensation"


class Recording:
    """A provider that records every prompt and answers one fixed SELECT."""
    prompts: list = []

    def __init__(self, model=None):
        self.model = model

    def complete(self, system, prompt, max_tokens=None):
        Recording.prompts.append(prompt)
        return REMEMBERED


@pytest.fixture
def served(monkeypatch):
    """A restricted demo catalog behind the server, a fake model, empty memory."""
    url = create_demo_db()
    cat = Catalog().bootstrap(url)
    cat.restrict("hr_compensation", ["payroll"])
    monkeypatch.delenv("SCHEMAGATE_MEMORY", raising=False)
    monkeypatch.delenv("SCHEMAGATE_AUDIT_LOG", raising=False)
    mcp_server.build_catalog(catalog=cat)
    monkeypatch.setattr(mcp_server, "_URL", url, raising=False)
    monkeypatch.setattr(mcp_server, "_ENGINE", None, raising=False)
    monkeypatch.setattr(P, "LocalProvider", Recording)
    monkeypatch.setenv("SCHEMAGATE_MCP_PROVIDER", "local")
    monkeypatch.setenv("SCHEMAGATE_MCP_MODEL", "fake")
    Recording.prompts.clear()
    return mcp_server._memory()


def ask(principal, roles=None):
    return mcp_server.answer("what do we pay people", principal=principal,
                             roles=roles or [], top_k=5)


# --- the loop: run, remember, reuse ------------------------------------------------

def test_a_query_that_ran_is_remembered_and_shown_next_time(served):
    first = ask("okta:hr", ["payroll"])
    assert "error" not in first and first["sql"] == REMEMBERED
    assert "Queries that answered" not in Recording.prompts[-1]      # nothing to show yet
    assert served.describe()["entries"] == 1

    second = ask("okta:hr", ["payroll"])
    assert "error" not in second
    assert REMEMBERED in Recording.prompts[-1]                        # now it is shown
    assert "Queries that answered similar questions" in Recording.prompts[-1]


def test_a_query_that_failed_is_not_remembered(served, monkeypatch):
    monkeypatch.setattr(Recording, "complete",
                        lambda self, s, p, max_tokens=None: "SELECT no_such_column FROM hr_compensation")
    out = ask("okta:hr", ["payroll"])
    assert "error" in out
    assert served.describe()["entries"] == 0


# --- memory never widens what a caller may see --------------------------------------

def test_the_example_is_never_shown_to_a_caller_who_cannot_see_its_table(served):
    ask("okta:hr", ["payroll"])                                       # remembered by payroll
    ask("okta:x", ["finance"])                                        # asked by someone else
    prompt = Recording.prompts[-1]
    assert "hr_compensation" not in prompt
    assert "Queries that answered" not in prompt


def test_a_remembered_table_is_pinned_only_for_a_caller_who_may_see_it(served):
    ask("okta:hr", ["payroll"])
    with_role = mcp_server.select_schema("what do we pay people", top_k=3,
                                         principal="okta:hr", roles=["payroll"])
    assert any(e["reason"] == "pinned" and e["object"].endswith("hr_compensation")
               for e in with_role["explain"])
    without = mcp_server.select_schema("what do we pay people", top_k=3, principal="okta:x")
    assert not any(o.endswith("hr_compensation") for o in without["objects"])
    assert not any(e["reason"] == "pinned" for e in without["explain"])


def test_an_unrelated_question_is_neither_pinned_nor_shown(served):
    ask("okta:hr", ["payroll"])
    out = mcp_server.select_schema("warehouse stock below reorder point", top_k=3,
                                   principal="okta:hr", roles=["payroll"])
    assert not any(e["reason"] == "pinned" for e in out["explain"])


# --- health, the file, and what is never in either -----------------------------------

def test_health_reports_counts_and_no_questions(served):
    ask("okta:hr", ["payroll"])
    h = mcp_server.health()["memory"]
    assert h["entries"] == 1 and h["remembered"] == 1 and h["file"] is None
    assert "pay" not in json.dumps(h) and "hr_compensation" not in json.dumps(h)


def test_file_from_env_survives_a_restart(monkeypatch, tmp_path):
    url = create_demo_db()
    cat = Catalog().bootstrap(url)
    cat.restrict("hr_compensation", ["payroll"])
    path = tmp_path / "memory.jsonl"
    monkeypatch.setenv("SCHEMAGATE_MEMORY", str(path))
    monkeypatch.setattr(P, "LocalProvider", Recording)
    monkeypatch.setenv("SCHEMAGATE_MCP_PROVIDER", "local")
    monkeypatch.setenv("SCHEMAGATE_MCP_MODEL", "fake")
    mcp_server.build_catalog(catalog=cat)
    monkeypatch.setattr(mcp_server, "_URL", url, raising=False)
    monkeypatch.setattr(mcp_server, "_ENGINE", None, raising=False)
    ask("okta:hr", ["payroll"])
    lines = [json.loads(l) for l in path.read_text("utf-8").splitlines()]
    assert len(lines) == 1 and lines[0]["sql"] == REMEMBERED
    assert "rows" not in lines[0] and "annual_amount" not in json.dumps(lines[0]["tables"])

    # a new server process: the memory is back, from the file
    mcp_server.build_catalog(catalog=cat)
    assert mcp_server.health()["memory"]["entries"] == 1
    Recording.prompts.clear()
    ask("okta:hr", ["payroll"])
    assert REMEMBERED in Recording.prompts[-1]
    monkeypatch.delenv("SCHEMAGATE_MEMORY")
    mcp_server.build_catalog(catalog=cat)


# --- the CLI ----------------------------------------------------------------------------

def test_cli_memory_flag_feeds_the_paste_prompt_next_time(tmp_path, capsys):
    from schemagate.cli import main
    url = create_demo_db()
    path = tmp_path / "m.jsonl"
    # seed the file the way a previous --answer run would have
    Memory(Catalog().embedder, path=path).remember("what do we pay people", REMEMBERED)
    main(["select", "what do we pay people", "--url", url, "--memory", str(path),
          "--answer", "--provider", "none", "--top-k", "5"])
    out = capsys.readouterr().out
    assert "Queries that answered similar questions" in out and REMEMBERED in out
    assert "pinned" not in out or "hr_compensation" in out


def test_cli_without_memory_flag_prints_the_old_prompt(tmp_path, capsys, monkeypatch):
    from schemagate.cli import main
    monkeypatch.delenv("SCHEMAGATE_MEMORY", raising=False)
    url = create_demo_db()
    main(["select", "what do we pay people", "--url", url, "--answer", "--provider", "none", "--top-k", "5"])
    out = capsys.readouterr().out
    assert "Queries that answered" not in out and "Question: what do we pay people" in out


# --- the Studio -------------------------------------------------------------------------

def test_studio_example_filter_reads_object_dicts_and_respects_visibility():
    from schemagate.studio import StudioState
    st = StudioState.__new__(StudioState)                                 # no server, no connect
    st.memory = Memory(Catalog().embedder)
    st.memory.remember("what do we pay people", REMEMBERED)
    shown = st._examples("what do we pay people",
                         {"objects": [{"name": "main.hr_compensation", "kind": "TABLE"}]})
    assert shown and shown[0][1] == REMEMBERED
    hidden = st._examples("what do we pay people",
                          {"objects": [{"name": "main.hr_employee", "kind": "TABLE"}]})
    assert hidden == []
    st.memory = None
    assert st._examples("anything", {"objects": []}) == ()
