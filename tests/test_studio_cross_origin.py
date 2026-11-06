# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""GHSA-5fcm-hgr8-hff5: a web page must not be able to drive a local Studio.

A loopback bind keeps other machines out, not other pages in the user's
browser. Before the fix, a file:// page, another local port or a LAN site
could send a no-preflight POST to /api/connect and make the Studio connect to
a database of its choosing, sampling its values. Every refused request below
must leave no trace: no connect call, no settings change.
"""
import http.client
import json

import pytest

from schemagate import Catalog
from schemagate.demo_schema import create_demo_db
from schemagate import studio as st
from schemagate.studio import StudioState, serve


def _host_ok(host):
    return st._host_ok(host)


@pytest.fixture
def studio():
    state = StudioState(Catalog(name="t").bootstrap(create_demo_db()), "t", "b", [])
    state.allow_connect = True          # the loopback default the report is about
    calls = []
    state.connect = lambda body: calls.append(body) or {"ok": True}
    srv = serve(state, "127.0.0.1", 0, False)            # serves on its own thread
    port = srv.server_address[1]

    def send(method, path, body=None, **headers):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        headers.setdefault("Host", f"127.0.0.1:{port}")
        data = json.dumps(body).encode() if body is not None else None
        conn.request(method, path, body=data, headers=headers)
        r = conn.getresponse()
        return r.status, r.read().decode("utf-8", "replace")

    yield send, state, calls, port
    srv.shutdown()
    srv.server_close()


ATTACK = {"url": "sqlite:////tmp/ssrf_target.db", "sample_values": True}


def test_the_reported_request_is_refused_and_does_nothing(studio):
    send, state, calls, port = studio
    before = send("GET", "/api/settings")[1]
    # Exactly the PoC: text/plain, foreign Origin, no token.
    code, body = send("POST", "/api/connect", ATTACK,
                      **{"Content-Type": "text/plain", "Origin": "http://evil.example"})
    assert code == 403, body
    assert calls == [], "connect() ran for a refused request"
    assert send("GET", "/api/settings")[1] == before


def test_a_file_page_is_refused(studio):
    send, state, calls, port = studio
    code, _ = send("POST", "/api/connect", ATTACK, **{"Content-Type": "text/plain", "Origin": "null"})
    assert code == 403 and calls == []


def test_no_token_is_refused_even_without_an_origin(studio):
    send, state, calls, port = studio
    code, body = send("POST", "/api/connect", ATTACK, **{"Content-Type": "application/json"})
    assert code == 403 and "token" in body and calls == []


def test_a_wrong_token_is_refused(studio):
    send, state, calls, port = studio
    code, _ = send("POST", "/api/connect", ATTACK, **{"X-Schemagate-Token": "guess"})
    assert code == 403 and calls == []


def test_the_right_token_from_a_foreign_origin_is_still_refused(studio):
    send, state, calls, port = studio
    code, _ = send("POST", "/api/connect", ATTACK,
                   **{"X-Schemagate-Token": state.token, "Origin": "http://192.168.1.20:8000"})
    assert code == 403 and calls == []


def test_every_post_endpoint_needs_the_token(studio):
    send, state, calls, port = studio
    for path in ("/api/select", "/api/settings", "/api/answer", "/api/describe",
                 "/api/apply-descriptions", "/api/resync", "/api/connections",
                 "/api/models", "/api/hints", "/api/glossary", "/api/rules"):
        code, _ = send("POST", path, {"question": "x"}, **{"Content-Type": "text/plain"})
        assert code == 403, path


def test_dns_rebinding_cannot_read_the_token(studio):
    # A rebinding page reaches the server under its own name; the page HTML
    # carries the token, so it must not be served to that Host.
    send, state, calls, port = studio
    code, body = send("GET", "/", Host=f"evil.example:{port}")
    assert code == 403 and state.token not in body
    code, _ = send("POST", "/api/connect", ATTACK,
                   Host=f"evil.example:{port}", **{"X-Schemagate-Token": state.token})
    assert code == 403 and calls == []


def test_the_studio_page_works_with_its_own_token(studio):
    send, state, calls, port = studio
    code, html = send("GET", "/")
    assert code == 200 and json.dumps(state.token) in html and '"X-Schemagate-Token"' in html
    code, _ = send("POST", "/api/connect", {"url": "sqlite://"},
                   **{"Content-Type": "application/json", "X-Schemagate-Token": state.token,
                      "Origin": f"http://127.0.0.1:{port}"})
    assert code == 200 and calls == [{"url": "sqlite://"}]


def test_a_preflight_is_refused_without_cors_headers(studio):
    send, state, calls, port = studio
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("OPTIONS", "/api/connect", headers={
        "Host": f"127.0.0.1:{port}", "Origin": "http://evil.example",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-schemagate-token"})
    r = conn.getresponse()
    r.read()
    assert r.status == 403
    assert not [h for h in r.getheaders() if h[0].lower().startswith("access-control-")]


@pytest.fixture
def real_studio(tmp_path):
    """No stubs: the real connect(), the real engine, a real target database."""
    import sqlite3
    target = tmp_path / "target.db"
    db = sqlite3.connect(target)
    db.execute("CREATE TABLE status_codes (id INTEGER PRIMARY KEY, status TEXT)")
    db.executemany("INSERT INTO status_codes (status) VALUES (?)", [("OPEN",), ("CLOSED",), ("REFUND",)])
    db.commit()
    db.close()
    state = StudioState(Catalog(name="t").bootstrap(create_demo_db()), "t", "b", [])
    state.allow_connect = True
    real_connect, calls = state.connect, []
    state.connect = lambda body: calls.append(body) or real_connect(body)
    srv = serve(state, "127.0.0.1", 0, False)
    port = srv.server_address[1]
    yield state, calls, port, f"sqlite:///{target.as_posix()}"
    srv.shutdown()
    srv.server_close()


def _post(port, path, body, **headers):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    conn.request("POST", path, body=json.dumps(body).encode(),
                 headers={"Host": f"127.0.0.1:{port}", **headers})
    r = conn.getresponse()
    return r.status, json.loads(r.read() or b"{}")


def test_a_refused_connect_creates_no_engine_and_reads_nothing(real_studio):
    state, calls, port, url = real_studio
    engine, docs = state.engine, set(state.catalog._docs)
    code, _ = _post(port, "/api/connect", {"url": url, "sample_values": True},
                    **{"Content-Type": "text/plain", "Origin": "http://evil.example"})
    assert code == 403
    assert calls == [], "connect() was reached"
    assert state.engine is engine and set(state.catalog._docs) == docs
    assert not any("status_codes" in d for d in state.catalog._docs)
    assert state.connected is False and not state.connection_label


def test_the_studio_page_connects_end_to_end_with_its_token(real_studio):
    state, calls, port, url = real_studio
    code, out = _post(port, "/api/connect", {"url": url},
                      **{"Content-Type": "application/json", "X-Schemagate-Token": state.token,
                         "Origin": f"http://127.0.0.1:{port}"})
    assert code == 200, out
    assert len(calls) == 1 and state.connected is True
    assert any(d.endswith("status_codes") for d in state.catalog._docs)


def test_each_studio_gets_its_own_token():
    a = StudioState(Catalog(name="a"), "a", "b", [])
    b = StudioState(Catalog(name="b"), "a", "b", [])
    assert a.token != b.token and len(a.token) >= 32


@pytest.mark.parametrize("host,ok", [
    ("127.0.0.1:8770", True), ("localhost:8770", True), ("[::1]:8770", True),
    ("10.0.0.5:8770", True), ("LOCALHOST", True),
    ("evil.example:8770", False), ("127.0.0.1.nip.io:8770", False), ("", False), (None, False),
])
def test_host_check(host, ok):
    assert _host_ok(host) is ok


def test_named_hosts_can_be_allowed(monkeypatch):
    monkeypatch.setenv("SCHEMAGATE_STUDIO_ALLOWED_HOSTS", "studio.corp, other.corp")
    assert _host_ok("studio.corp:8770") and _host_ok("other.corp")
    assert not _host_ok("evil.example")
