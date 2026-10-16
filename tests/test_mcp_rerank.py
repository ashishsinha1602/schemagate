# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""SCHEMAGATE_MCP_RERANK: the MCP server's select_schema reranks with its configured model.

Off unless set; set without a model, the server refuses to start. On, the model only reorders the
shortlist of what the caller may already see, and a model that errors leaves the maths order.
A fake model stands in for a real one, so nothing here costs a call.
"""
import re

import pytest

from schemagate import mcp_server

QUESTION = "which customers owe us money"


class FakeModel:
    """Picks the LAST candidate it is shown, so a rerank is visible in the order."""

    def __init__(self, fail=False):
        self.prompts, self.fail = [], fail

    def complete(self, system, prompt, max_tokens=120):
        self.prompts.append(prompt)
        if self.fail:
            raise RuntimeError("model unavailable")
        n = len(re.findall(r"^\d+\. ", prompt, flags=re.M))
        return str(n)

    def last_candidate(self):
        return re.findall(r"^\d+\. (\S+)", self.prompts[-1], flags=re.M)[-1]


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("SCHEMAGATE_DATABASE_URL", "demo")
    monkeypatch.setenv("SCHEMAGATE_AUTO_DESCRIBE", "0")
    monkeypatch.delenv("SCHEMAGATE_CATALOG_MAX_AGE", raising=False)
    monkeypatch.delenv("SCHEMAGATE_CATALOG_CONFIG", raising=False)

    def start(model=None, rerank=True):
        if rerank:
            monkeypatch.setenv("SCHEMAGATE_MCP_RERANK", "1")
        else:
            monkeypatch.delenv("SCHEMAGATE_MCP_RERANK", raising=False)
        monkeypatch.setattr(mcp_server, "_server_provider", lambda: model)
        mcp_server.build_catalog()
    yield start
    mcp_server._STATE["rerank"] = False


def test_off_by_default_and_the_model_is_never_asked(server, monkeypatch):
    server(rerank=False)

    def boom():
        raise AssertionError("the model was consulted with reranking off")
    monkeypatch.setattr(mcp_server, "_server_provider", boom)
    out = mcp_server.select_schema(QUESTION)
    assert out["objects"] and mcp_server.health()["rerank"] is False


def test_on_the_models_choice_leads_the_selection(server):
    model = FakeModel()
    server(model)
    out = mcp_server.select_schema(QUESTION)
    assert model.prompts, "the model was not asked"
    assert out["objects"][0] == model.last_candidate()
    assert mcp_server.health()["rerank"] is True


def test_the_model_never_sees_or_returns_a_withheld_object(server):
    model = FakeModel()
    server(model)
    every = {d.qname for d in mcp_server._catalog().objects()}
    sales = mcp_server.select_schema("salary by employee", principal="okta:sales", roles=["sales"])
    allowed = set(mcp_server.select_schema("salary by employee", principal="okta:pay",
                                           roles=["payroll"])["objects"]) | set(sales["objects"])
    hidden = {q for q in every if "compensation" in q}
    assert hidden, "the demo schema should have a restricted compensation table"
    shown_to_model = model.prompts[0]
    assert not any(h in shown_to_model for h in hidden)
    assert not hidden & set(sales["objects"])
    assert allowed


def test_a_failing_model_leaves_the_maths_order_and_no_error(server, monkeypatch):
    server(FakeModel(fail=True))
    reranked = mcp_server.select_schema(QUESTION)
    monkeypatch.setitem(mcp_server._STATE, "rerank", False)
    plain = mcp_server.select_schema(QUESTION)
    assert "error" not in reranked and reranked["objects"] == plain["objects"]


@pytest.mark.parametrize("env", [
    {},                                                                    # no model at all
    {"SCHEMAGATE_MCP_PROVIDER": "anthropic"},                              # model name missing
    {"SCHEMAGATE_MCP_PROVIDER": "nonsense", "SCHEMAGATE_MCP_MODEL": "x"},  # unknown provider
])
def test_rerank_without_a_usable_model_stops_the_server(monkeypatch, env):
    monkeypatch.setenv("SCHEMAGATE_DATABASE_URL", "demo")
    monkeypatch.setenv("SCHEMAGATE_MCP_RERANK", "1")
    monkeypatch.delenv("SCHEMAGATE_MCP_PROVIDER", raising=False)
    monkeypatch.delenv("SCHEMAGATE_MCP_MODEL", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(SystemExit, match="SCHEMAGATE_MCP_RERANK=1 needs a model"):
        mcp_server.build_catalog()
