# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""OAuth on the HTTP transport: identity comes from a verified token, never from the client.

The unit tests check the verifier and the request rewrite. The end-to-end test starts the real
server (`python -m schemagate.mcp_server`, streamable HTTP, the demo database) against a local
identity provider -- OpenID metadata and a JWKS on loopback, keys made here -- and talks MCP to it
over HTTP: tokens that are missing, expired, for another audience, from another issuer, signed with
another key or unsigned are refused, and a caller whose token says `sales` cannot read the payroll
table by sending roles=["payroll"] in the tool arguments.
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import serialization          # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa         # noqa: E402

from schemagate import oauth                                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)
AUD = "https://sg.example.test/mcp"


def _token(iss, key=KEY, kid="k1", alg="RS256", **claims):
    body = {"iss": iss, "aud": AUD, "sub": "okta|sam", "exp": int(time.time()) + 600, **claims}
    body = {k: v for k, v in body.items() if v is not None}
    return jwt.encode(body, key, algorithm=alg, headers={"kid": kid})


class _Keys:
    """Stands in for PyJWKClient: one known key id."""

    class _K:
        key = KEY.public_key()

    def get_signing_key_from_jwt(self, token):
        if jwt.get_unverified_header(token).get("kid") != "k1":
            raise jwt.PyJWKClientError("unknown kid")
        return self._K()


ISS = "https://idp.example.test"


def _verifier(**kw):
    cfg = oauth.OAuthConfig(issuer=ISS, audience=AUD, resource=AUD, **kw)
    return oauth.Verifier(cfg, jwk_client=_Keys())


# --- the verifier --------------------------------------------------------------------------------

def test_a_good_token_gives_its_subject_and_roles():
    assert _verifier().verify(_token(ISS, roles=["sales"])) == ("oauth:okta|sam", ["sales"])


def test_groups_and_dotted_claims_and_a_single_string_role():
    assert _verifier().verify(_token(ISS, groups=["finance"]))[1] == ["finance"]
    v = _verifier(roles_claims=["realm_access.roles"])
    assert v.verify(_token(ISS, realm_access={"roles": ["payroll"]}))[1] == ["payroll"]
    assert _verifier().verify(_token(ISS, roles="hr"))[1] == ["hr"]
    auth0 = _verifier(roles_claims=["https://example.com/roles"])                 # a claim name with dots
    assert auth0.verify(_token(ISS, **{"https://example.com/roles": ["sales"]}))[1] == ["sales"]
    assert _verifier().verify(_token(ISS))[1] == []                      # no claim: no roles


@pytest.mark.parametrize("label, token", [
    ("expired", lambda: _token(ISS, exp=int(time.time()) - 3600)),
    ("another audience", lambda: _token(ISS, aud="https://other.example.test")),
    ("another issuer", lambda: _token("https://evil.example.test")),
    ("another key", lambda: _token(ISS, key=OTHER)),
    ("unknown key id", lambda: _token(ISS, kid="k9")),
    ("no exp", lambda: _token(ISS, exp=None)),
    ("no subject", lambda: _token(ISS, sub=None)),
    ("unsigned", lambda: jwt.encode({"iss": ISS, "aud": AUD, "sub": "x", "exp": int(time.time()) + 600},
                                    None, algorithm="none")),
    ("HMAC with the public key as secret", lambda: jwt.encode(
        {"iss": ISS, "aud": AUD, "sub": "x", "exp": int(time.time()) + 600},
        KEY.public_key().public_bytes(serialization.Encoding.PEM,
                                      serialization.PublicFormat.SubjectPublicKeyInfo).decode()[:64],
        algorithm="HS256", headers={"kid": "k1"})),
    ("garbage", lambda: "not.a.token"),
])
def test_bad_tokens_are_refused(label, token):
    with pytest.raises(oauth.TokenError):
        _verifier().verify(token())


def test_a_missing_scope_is_403_insufficient_scope():
    v = _verifier(scopes=["schemagate.read"])
    assert v.verify(_token(ISS, scope="openid schemagate.read"))[0] == "oauth:okta|sam"
    assert v.verify(_token(ISS, scp=["schemagate.read"]))[0] == "oauth:okta|sam"
    with pytest.raises(oauth.TokenError) as e:
        v.verify(_token(ISS, scope="openid"))
    assert e.value.status == 403 and e.value.error == "insufficient_scope"


def test_config_needs_an_audience_and_https():
    assert oauth.OAuthConfig.from_env({}) is None
    with pytest.raises(ValueError, match="AUDIENCE is required"):
        oauth.OAuthConfig.from_env({"SCHEMAGATE_MCP_OAUTH_ISSUER": ISS})
    with pytest.raises(ValueError, match="https"):
        oauth.OAuthConfig.from_env({"SCHEMAGATE_MCP_OAUTH_ISSUER": "http://idp.example.test",
                                    "SCHEMAGATE_MCP_OAUTH_AUDIENCE": AUD})
    cfg = oauth.OAuthConfig.from_env({"SCHEMAGATE_MCP_OAUTH_ISSUER": ISS, "SCHEMAGATE_MCP_OAUTH_AUDIENCE": AUD,
                                      "SCHEMAGATE_MCP_OAUTH_ROLES_CLAIM": "realm_access.roles",
                                      "SCHEMAGATE_MCP_OAUTH_SCOPES": "a, b"})
    assert cfg.roles_claims == ["realm_access.roles"] and cfg.scopes == ["a", "b"]
    assert cfg.metadata_url() == "https://sg.example.test/.well-known/oauth-protected-resource/mcp"
    assert cfg.metadata()["authorization_servers"] == [ISS]


# --- the rewrite ---------------------------------------------------------------------------------

def test_tool_calls_get_the_token_identity_whatever_the_client_sent():
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "run_query", "arguments": {"sql": "SELECT 1", "principal": "admin",
                                                          "roles": ["payroll"]}}}
    out = json.loads(oauth._rewrite(json.dumps(call).encode(), "okta|sam", ["sales"], ["run_query"]))
    assert out["params"]["arguments"] == {"sql": "SELECT 1", "principal": "okta|sam", "roles": ["sales"]}
    batch = [dict(call, id=2), {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                "params": {"name": "list_objects"}}]
    out = json.loads(oauth._rewrite(json.dumps(batch).encode(), "u", [], ["run_query", "list_objects"]))
    assert [m["params"]["arguments"]["roles"] for m in out] == [[], []]
    other = {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "health", "arguments": {}}}
    raw = json.dumps(other).encode()
    assert oauth._rewrite(raw, "u", [], ["run_query"]) == raw                # no identity to set
    assert oauth._rewrite(b"{not json", "u", [], ["run_query"]) == b"{not json"


# --- the real server, over HTTP, against a local identity provider -------------------------------

def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def idp():
    from jwt.algorithms import RSAAlgorithm
    jwk = dict(RSAAlgorithm.to_jwk(KEY.public_key(), as_dict=True), kid="k1", use="sig", alg="RS256")
    port = _free_port()
    issuer = f"http://127.0.0.1:{port}"

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            docs = {"/.well-known/openid-configuration": {"issuer": issuer, "jwks_uri": issuer + "/jwks"},
                    "/jwks": {"keys": [jwk]}}
            if self.path not in docs:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(docs[self.path]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield issuer
    srv.shutdown()


class _Resp:
    def __init__(self, status, headers, body):
        self.status_code, self.headers, self.text = status, {k.lower(): v for k, v in headers.items()}, body

    def json(self):
        return json.loads(self.text)


def _http(method, url, headers=None, data=None):
    """urllib: the MCP SDK 2.x no longer installs an HTTP client library."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return _Resp(r.status, dict(r.headers), r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return _Resp(e.code, dict(e.headers), e.read().decode("utf-8", "replace"))


@pytest.fixture(scope="module")
def server(idp):
    pytest.importorskip("mcp")
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith("SCHEMAGATE_")}
    env.update(SCHEMAGATE_MCP_TRANSPORT="streamable-http", SCHEMAGATE_MCP_PORT=str(port),
               SCHEMAGATE_MCP_OAUTH_ISSUER=idp, SCHEMAGATE_MCP_OAUTH_AUDIENCE=AUD,
               SCHEMAGATE_MCP_OAUTH_RESOURCE=f"http://127.0.0.1:{port}/mcp",
               SCHEMAGATE_AUTO_DESCRIBE="0", PYTHONIOENCODING="utf-8",
               PYTHONPATH=os.pathsep.join([os.path.join(ROOT, "src"), env.get("PYTHONPATH", "")]))
    proc = subprocess.Popen([sys.executable, "-m", "schemagate.mcp_server", "--url", "demo"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(240):
        try:
            if _http("GET", base + "/.well-known/oauth-protected-resource/mcp").status_code == 200:
                break
        except OSError:
            pass
        if proc.poll() is not None:
            pytest.fail("server exited: " + proc.stdout.read().decode(errors="replace")[-2000:])
        time.sleep(0.5)
    else:
        proc.kill()
        pytest.fail("server did not start")
    yield base
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()


class _Client:
    """Just enough MCP over streamable HTTP: initialize, then tools/call."""

    def __init__(self, base, token):
        self.url = base + "/mcp"
        self.headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self.n = 0

    def post(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}
        if not notify:
            self.n += 1
            msg["id"] = self.n
        return _http("POST", self.url, self.headers, json.dumps(msg).encode())

    @staticmethod
    def body(resp):
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:])
        raise AssertionError(resp.text)

    def start(self):
        r = self.post("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "test", "version": "0"}})
        assert r.status_code == 200, (r.status_code, r.text)
        self.headers["mcp-session-id"] = r.headers.get("mcp-session-id", "")
        self.headers["mcp-protocol-version"] = self.body(r)["result"]["protocolVersion"]
        self.post("notifications/initialized", notify=True)
        return self

    def call(self, tool, **args):
        res = self.body(self.post("tools/call", {"name": tool, "arguments": args}))["result"]
        sc = res.get("structuredContent")
        if sc:
            return sc["result"] if set(sc) == {"result"} else sc        # 2.x wraps a dict return
        return json.loads("".join(c.get("text", "") for c in res["content"]))


def test_metadata_points_clients_at_the_identity_provider(server, idp):
    meta = _http("GET", server + "/.well-known/oauth-protected-resource/mcp").json()
    assert meta["authorization_servers"] == [idp] and meta["resource"] == server + "/mcp"


@pytest.mark.parametrize("label, token", [
    ("no token", lambda iss: None),
    ("expired", lambda iss: _token(iss, exp=int(time.time()) - 3600, roles=["payroll"])),
    ("another audience", lambda iss: _token(iss, aud="https://other.example.test", roles=["payroll"])),
    ("another issuer", lambda iss: _token("https://evil.example.test", roles=["payroll"])),
    ("another key", lambda iss: _token(iss, key=OTHER, roles=["payroll"])),
])
def test_requests_without_a_valid_token_get_401_and_the_metadata_url(server, idp, label, token):
    r = _Client(server, token(idp)).post("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                        "clientInfo": {"name": "t", "version": "0"}})
    assert r.status_code == 401, (label, r.status_code, r.text)
    assert "resource_metadata=" in r.headers["www-authenticate"]
    assert server + "/.well-known/oauth-protected-resource/mcp" in r.headers["www-authenticate"]


def test_the_token_decides_the_roles_not_the_tool_arguments(server, idp):
    sales = _Client(server, _token(idp, roles=["sales"])).start()
    out = sales.call("run_query", sql="SELECT * FROM hr_compensation", principal="admin", roles=["payroll"])
    assert "error" in out and "rows" not in out, out
    listed = json.dumps(sales.call("list_objects", principal="admin", roles=["payroll"]))
    assert "hr_compensation" not in listed
    assert sales.call("health")["auth"] == "oauth"

    payroll = _Client(server, _token(idp, sub="okta|pat", roles=["payroll"])).start()
    out = payroll.call("run_query", sql="SELECT COUNT(*) FROM hr_compensation")
    assert out.get("rows") and out["principal"] == "oauth:okta|pat", out
    # the client cannot take on another identity either
    out = payroll.call("run_query", sql="SELECT 1", principal="okta|someone-else")
    assert out["principal"] == "oauth:okta|pat", out


def test_no_role_claim_means_no_roles(server, idp):
    anon = _Client(server, _token(idp)).start()
    out = anon.call("run_query", sql="SELECT * FROM hr_compensation", principal="okta:pat", roles=["payroll"])
    assert "error" in out and "rows" not in out, out
