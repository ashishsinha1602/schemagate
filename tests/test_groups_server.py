"""The groups resolver in front of the MCP server: every tool, a real client.

`test_groups.py` proves the resolver. This file proves the server uses it
everywhere -- one tool that still trusted the client's roles would be the
whole hole again -- and that the path a desktop client takes (a subprocess,
stdio, `SCHEMAGATE_CATALOG_CONFIG` with a ``groups`` block) behaves the same.
"""
from __future__ import annotations

import json
import os
import sys
import threading

import pytest

from schemagate import mcp_server
from schemagate.groups import Groups, StaticGroups


class Down(StaticGroups):
    name = "down"

    def groups(self, subject):
        raise ConnectionError("directory unreachable")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def served_with(cat, db_url, monkeypatch):
    """Install the commerce catalog with one restriction and a resolver;
    put the server back to 'trust the client' afterwards. ``_URL`` and
    ``_ENGINE`` are set so run_query has a database, as the run_query tests
    in test_mcp_server.py do."""
    cat.restrict("hr_compensation", ["payroll"])
    monkeypatch.setattr(mcp_server, "_URL", db_url, raising=False)
    monkeypatch.setattr(mcp_server, "_ENGINE", None, raising=False)

    def install(groups):
        mcp_server.build_catalog(catalog=cat, groups=groups)
        return cat
    yield install
    mcp_server.build_catalog(catalog=cat)
    assert mcp_server.health()["groups"] is None


DIRECTORY = Groups([StaticGroups({"okta:hr": ["payroll"], "okta:fin": ["finance"]})])


# --- every tool consults the directory, not the client ------------------------

def test_list_objects_uses_directory_roles(served_with):
    served_with(DIRECTORY)
    def names(out):
        return {o["name"].split(".")[-1] for o in out["objects"]}
    assert "hr_compensation" in names(mcp_server.list_objects(principal="okta:hr"))
    assert "hr_compensation" not in names(
        mcp_server.list_objects(principal="okta:fin", roles=["payroll"]))
    assert "hr_compensation" not in names(mcp_server.list_objects())


def test_describe_object_uses_directory_roles(served_with):
    served_with(DIRECTORY)
    ok = mcp_server.describe_object("hr_compensation", principal="okta:hr")
    assert "error" not in ok and "hr_compensation" in ok["ddl"].lower()
    denied = mcp_server.describe_object("hr_compensation", principal="okta:fin",
                                        roles=["payroll"])
    missing = mcp_server.describe_object("no_such_table", principal="okta:fin")
    # restricted and absent still read the same, so existence does not leak
    assert "error" in denied
    assert (denied["error"].replace("hr_compensation", "?")
            == missing["error"].replace("no_such_table", "?"))


def test_run_query_uses_directory_roles(served_with):
    served_with(DIRECTORY)
    ok = mcp_server.run_query("SELECT COUNT(*) AS n FROM hr_compensation", principal="okta:hr")
    assert "rows" in ok, ok
    denied = mcp_server.run_query("SELECT COUNT(*) AS n FROM hr_compensation",
                                  principal="okta:fin", roles=["payroll"])
    assert "error" in denied and "rows" not in denied


@pytest.mark.parametrize("tool,args", [
    ("select_schema", {"question": "salary by employee", "top_k": 10}),
    ("list_objects", {}),
    ("describe_object", {"name": "hr_compensation"}),
    ("run_query", {"sql": "SELECT 1 AS x"}),
])
def test_every_identity_tool_fails_closed_when_the_directory_is_down(served_with, tool, args):
    served_with(Groups([Down({})]))
    out = getattr(mcp_server, tool)(principal="okta:hr", **args)
    assert "error" in out and "down source failed" in out["error"], out
    for key in ("objects", "ddl", "rows", "columns"):
        assert key not in out
    # and the server is still serving: the anonymous path never asks the directory
    assert "error" not in mcp_server.list_objects()
    assert mcp_server.health()["status"] == "ok"


def test_directory_error_is_counted_but_does_not_poison_the_cache(served_with):
    flaky = {"fail": True}

    class Flaky(StaticGroups):
        name = "flaky"

        def groups(self, subject):
            if flaky["fail"]:
                raise ConnectionError("blip")
            return super().groups(subject)

    g = Groups([Flaky({"okta:hr": ["payroll"]})])
    served_with(g)
    out = mcp_server.select_schema("salary by employee", top_k=10, principal="okta:hr")
    assert "error" in out
    flaky["fail"] = False
    out = mcp_server.select_schema("salary by employee", top_k=10, principal="okta:hr")
    assert "hr_compensation" in " ".join(out["objects"])
    assert g.stats["errors"] == 1 and g.stats["misses"] == 1


def test_refresh_forgets_cached_memberships(served_with, monkeypatch):
    members = {"okta:hr": ["payroll"]}

    class Live(StaticGroups):
        def groups(self, subject):
            return set(members.get(subject, ()))

    served_with(Groups([Live({})]))
    out = mcp_server.select_schema("salary by employee", top_k=10, principal="okta:hr")
    assert "hr_compensation" in " ".join(out["objects"])
    members.clear()                                     # revoked in the directory
    out = mcp_server.select_schema("salary by employee", top_k=10, principal="okta:hr")
    assert "hr_compensation" in " ".join(out["objects"])   # still cached, within ttl
    mcp_server._GROUPS.forget()                            # what refresh_catalog does
    out = mcp_server.select_schema("salary by employee", top_k=10, principal="okta:hr")
    assert "hr_compensation" not in " ".join(out["objects"])


# --- concurrency ------------------------------------------------------------------

def test_resolver_is_safe_under_concurrent_callers():
    calls = []
    lock = threading.Lock()

    class Slow(StaticGroups):
        def groups(self, subject):
            with lock:
                calls.append(subject)
            return super().groups(subject)

    g = Groups([Slow({f"okta:u{i}": [f"g{i}"] for i in range(8)})])
    errors = []

    def worker(n):
        try:
            for i in range(50):
                subj = f"okta:u{(n + i) % 8}"
                got = g.roles_for(subj)
                if got != {f"g{(n + i) % 8}"}:
                    errors.append((subj, got))
        except Exception as e:                                  # noqa: BLE001
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert g.stats["hits"] + g.stats["misses"] == 16 * 50
    assert g.describe()["cached"] == 8


# --- the path a desktop client takes: subprocess, stdio, config file -------------

def _stdio_params(config_path):
    from mcp import StdioServerParameters
    env = dict(os.environ)
    env["SCHEMAGATE_DATABASE_URL"] = "demo"
    env["SCHEMAGATE_CATALOG_CONFIG"] = str(config_path)
    return StdioServerParameters(command=sys.executable,
                                 args=["-m", "schemagate.mcp_server"], env=env)


async def _call(session, tool, args):
    result = await session.call_tool(tool, args)
    return "".join(getattr(c, "text", "") for c in result.content)


@pytest.mark.anyio
async def test_groups_block_in_config_governs_a_real_client(tmp_path):
    pytest.importorskip("mcp")
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    cfg = tmp_path / "catalog.json"
    cfg.write_text(json.dumps({
        "groups": {"sources": [{"type": "static",
                                "members": {"okta:hr": ["Payroll Team"]}}],
                   "map": {"Payroll Team": "payroll"}, "passthrough": False},
    }), "utf-8")
    async with stdio_client(_stdio_params(cfg)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # the demo catalog restricts hr_compensation to `payroll`
            claimed = await _call(session, "select_schema",
                                  {"question": "salary by employee", "top_k": 10,
                                   "principal": "okta:x", "roles": ["payroll"]})
            assert "hr_compensation" not in claimed.lower(), "client's claim was honoured"
            member = await _call(session, "select_schema",
                                 {"question": "salary by employee", "top_k": 10,
                                  "principal": "okta:hr"})
            assert "hr_compensation" in member
            health = json.loads(await _call(session, "health", {}))
            assert health["groups"]["sources"] == ["static"]
            assert health["groups"]["mapped"] == 1
            assert "okta:hr" not in json.dumps(health["groups"])


@pytest.mark.anyio
async def test_a_bad_groups_block_stops_the_server_before_it_answers(tmp_path):
    """An unset ${SECRET} must not degrade to 'trust the client'."""
    pytest.importorskip("mcp")
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    cfg = tmp_path / "catalog.json"
    cfg.write_text(json.dumps({
        "groups": {"sources": [{"type": "entra", "tenant": "t", "client_id": "c",
                                "client_secret": "${SG_TEST_UNSET_SECRET}"}]},
    }), "utf-8")
    os.environ.pop("SG_TEST_UNSET_SECRET", None)
    with pytest.raises(Exception):                      # noqa: B017 -- SDK-specific
        async with stdio_client(_stdio_params(cfg)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _call(session, "select_schema",
                            {"question": "salary", "principal": "okta:x", "roles": ["payroll"]})
