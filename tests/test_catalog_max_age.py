# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""SCHEMAGATE_CATALOG_MAX_AGE: a bounded window for stale permissions, failing closed.

The server reads permissions when it builds its catalogue: restrictions from the config file and,
with SCHEMAGATE_RESTRICT_FROM_GRANTS, the database's own GRANTs. Without a bound, a revoke in the
database only lands when someone calls refresh_catalog, and a refresh that fails keeps the old
catalogue serving forever. With the bound, an older catalogue is re-read before it is used, and if
that fails every scoping tool refuses until a re-read succeeds.

Every case runs on a controlled clock, so the boundary is exact: just inside the age, just past it,
past it with the re-read failing, the retry pacing, and recovery.
"""
import json
import threading

import pytest

from schemagate import mcp_server

SCOPING = ("select_schema", "list_objects", "describe_object", "run_query")


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


@pytest.fixture
def server(monkeypatch, tmp_path):
    """A server on the demo database with a config file the test can rewrite, a fake clock, and a
    counter on every re-read."""
    clock = Clock()
    cfg = tmp_path / "roles.json"
    cfg.write_text(json.dumps({"restrict": {}}), encoding="utf-8")
    monkeypatch.setattr(mcp_server, "_clock", clock)
    monkeypatch.setenv("SCHEMAGATE_DATABASE_URL", "demo")
    monkeypatch.setenv("SCHEMAGATE_CATALOG_CONFIG", str(cfg))
    monkeypatch.setenv("SCHEMAGATE_AUTO_DESCRIBE", "0")
    monkeypatch.setenv("SCHEMAGATE_CATALOG_MAX_AGE", "60")
    real = mcp_server._reflect
    calls = []

    def counting(url, config_path):
        calls.append(clock())
        return real(url, config_path)

    monkeypatch.setattr(mcp_server, "_reflect", counting)
    mcp_server.build_catalog()
    calls.clear()                                   # the startup read is not a re-read
    yield clock, cfg, calls, monkeypatch
    monkeypatch.setitem(mcp_server._STATE, "max_age", None)


def _call(tool, **kw):
    fn = getattr(mcp_server, tool)
    args = {"select_schema": {"question": "which customers owe us money"},
            "list_objects": {}, "describe_object": {"name": "crm_customer"},
            "run_query": {"sql": "SELECT count(*) FROM crm_customer"}}[tool]
    return fn(**{**args, **kw})


def _fail_reflect(monkeypatch, calls, clock):
    def broken(url, config_path):
        calls.append(clock())
        raise RuntimeError("could not connect to secret-host.internal as user admin")
    monkeypatch.setattr(mcp_server, "_reflect", broken)


# --- configuration -----------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["abc", "0", "-5", "inf", "nan", "1e400"])
def test_an_invalid_max_age_stops_the_server_before_any_database_work(monkeypatch, bad):
    monkeypatch.setenv("SCHEMAGATE_DATABASE_URL", "demo")
    monkeypatch.setenv("SCHEMAGATE_CATALOG_MAX_AGE", bad)
    touched = []
    monkeypatch.setattr(mcp_server, "_reflect", lambda *a: touched.append(1))
    with pytest.raises(SystemExit, match="SCHEMAGATE_CATALOG_MAX_AGE"):
        mcp_server.build_catalog()
    assert touched == []


def test_unset_means_no_bound_and_no_rereads(server):
    clock, cfg, calls, mp = server
    mp.setitem(mcp_server._STATE, "max_age", None)
    clock.advance(10 ** 6)
    for tool in SCOPING:
        assert "error" not in _call(tool), tool
    assert calls == []


def test_a_catalogue_handed_in_directly_has_nothing_to_reread(server, cat):
    clock, cfg, calls, mp = server
    mcp_server.build_catalog(catalog=cat)
    mp.setitem(mcp_server._STATE, "max_age", 60.0)
    clock.advance(10 ** 6)
    assert "error" not in mcp_server.list_objects()
    assert calls == []


# --- the boundary ------------------------------------------------------------------------------------

def test_inside_the_age_nothing_is_reread(server):
    clock, cfg, calls, mp = server
    clock.advance(60.0)                              # exactly at the limit is still fresh
    for tool in SCOPING:
        assert "error" not in _call(tool), tool
    assert calls == []


def test_just_past_the_age_one_reread_then_fresh_again(server):
    clock, cfg, calls, mp = server
    clock.advance(60.001)
    assert "error" not in _call("list_objects")
    assert len(calls) == 1
    for tool in SCOPING:                             # the clock restarted at the re-read
        assert "error" not in _call(tool), tool
    assert len(calls) == 1
    assert mcp_server.health()["catalog_stale"] is False


# --- failing closed ----------------------------------------------------------------------------------

def test_past_the_age_with_a_failing_reread_every_scoping_tool_refuses(server):
    clock, cfg, calls, mp = server
    _fail_reflect(mp, calls, clock)
    clock.advance(61)
    for tool in SCOPING:
        out = _call(tool)
        assert "rows" not in out and "objects" not in out and "ddl" not in out, (tool, out)
        assert "permissions are stale" in out["error"], (tool, out)
    answered = mcp_server.answer(question="which customers owe us money")
    assert "permissions are stale" in answered.get("error", ""), answered


def test_the_refusal_never_carries_the_database_error_text(server):
    clock, cfg, calls, mp = server
    _fail_reflect(mp, calls, clock)
    clock.advance(61)
    for tool in SCOPING:
        text = json.dumps(_call(tool))
        assert "secret-host" not in text and "admin" not in text, (tool, text)
    h = mcp_server.health()                          # the operator gets the reason
    assert h["catalog_stale"] is True and "secret-host" in (h["last_error"] or "")
    assert h["catalog_max_age_seconds"] == 60.0 and h["catalog_age_seconds"] > 60


def test_a_failed_reread_is_retried_at_most_every_few_seconds(server):
    clock, cfg, calls, mp = server
    _fail_reflect(mp, calls, clock)
    clock.advance(61)
    _call("list_objects")
    assert len(calls) == 1
    for _ in range(20):                              # a burst inside the retry window
        assert "stale" in _call("list_objects")["error"]
    assert len(calls) == 1, "no reflection storm while the database is down"
    clock.advance(mcp_server.STALE_RETRY_SECONDS)
    _call("list_objects")
    assert len(calls) == 2


def test_recovery_once_the_database_answers_again(server):
    clock, cfg, calls, mp = server
    _fail_reflect(mp, calls, clock)
    clock.advance(61)
    assert "stale" in _call("list_objects")["error"]
    mp.undo()                                        # put _reflect, env and clock back ...
    mp.setattr(mcp_server, "_clock", clock)          # ... then re-apply what this test needs
    mp.setenv("SCHEMAGATE_DATABASE_URL", "demo")
    mp.setenv("SCHEMAGATE_CATALOG_CONFIG", str(cfg))
    mp.setenv("SCHEMAGATE_AUTO_DESCRIBE", "0")
    mp.setitem(mcp_server._STATE, "max_age", 60.0)
    clock.advance(mcp_server.STALE_RETRY_SECONDS)
    for tool in SCOPING:
        assert "error" not in _call(tool), (tool, _call(tool))
    assert mcp_server.health()["catalog_stale"] is False


# --- what the bound is for ---------------------------------------------------------------------------

def test_a_revocation_takes_effect_within_the_age(server):
    clock, cfg, calls, mp = server
    assert "crm_customer" in json.dumps(mcp_server.list_objects())
    cfg.write_text(json.dumps({"restrict": {"crm_customer": ["finance"]}}), encoding="utf-8")
    clock.advance(30)                                # inside the window: the old answer, as documented
    assert "crm_customer" in json.dumps(mcp_server.list_objects())
    clock.advance(31)                                # past it: re-read, revoked
    assert "crm_customer" not in json.dumps(mcp_server.list_objects())
    out = mcp_server.run_query(sql="SELECT count(*) FROM crm_customer")
    assert "error" in out and "rows" not in out
    fin = mcp_server.list_objects(principal="okta:fin", roles=["finance"])
    assert "crm_customer" in json.dumps(fin)


def test_a_manual_refresh_restarts_the_clock(server):
    clock, cfg, calls, mp = server
    clock.advance(59)
    assert mcp_server.refresh_catalog()["ok"] is True
    clock.advance(59)                                # 118 s since startup, 59 since the refresh
    assert "error" not in _call("list_objects")
    assert len(calls) == 1                           # only the manual one


def test_simultaneous_calls_past_the_age_cause_one_reread(server):
    clock, cfg, calls, mp = server
    clock.advance(61)
    results, start = [], threading.Barrier(10)

    def worker():
        start.wait()
        results.append(_call("list_objects"))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert len(results) == 10 and all("error" not in r for r in results)
    assert len(calls) == 1, f"{len(calls)} re-reads for one expiry"


def test_a_stale_refusal_is_recorded_as_a_refusal(server):
    clock, cfg, calls, mp = server
    _fail_reflect(mp, calls, clock)
    clock.advance(61)
    _call("list_objects")
    rec = mcp_server._audit().recent()[-1]
    assert rec["tool"] == "list_objects" and rec["ok"] is False, rec
    assert "permissions are stale" in rec["error"] and "secret-host" not in rec["error"], rec
