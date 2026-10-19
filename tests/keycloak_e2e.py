# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""schemagate + a real Keycloak: the whole MCP OAuth flow, driven by the MCP SDK's own OAuth client.

Run by .github/workflows/mcp-e2e.yml (keycloak job). Not a pytest module: it needs Keycloak on
localhost:8180 (KC_BOOTSTRAP_ADMIN_PASSWORD from the environment, throwaway, one job long).

The client starts from nothing but the server URL: 401 -> Protected Resource Metadata -> Keycloak's
metadata -> Dynamic Client Registration -> authorization code with PKCE (a person's login is played
by posting Keycloak's own login form) -> token -> tools. Then: a `sales` user cannot read the payroll
table whatever the tool arguments claim, a `payroll` user can, real Keycloak tokens for another
application or from another realm are refused, an edited token is refused, and removing the role
in Keycloak takes effect on the next token.

    python tests/keycloak_e2e.py [python-to-run-the-server-with]
"""
import asyncio
import base64
import html
import http.cookiejar as cookiejar
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

KC = "http://localhost:8180"
ISSUER = f"{KC}/realms/sg"
PORT = 8766
BASE = f"http://127.0.0.1:{PORT}"
REDIRECT = "http://127.0.0.1:53682/callback"
R = []


def rec(name, ok, detail=""):
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"   ({str(detail)[:600]})"), flush=True)


def http(method, url, data=None, headers=None, form=False, opener=None):
    h = dict(headers or {})
    if data is not None and not isinstance(data, bytes):
        if form:
            data = urllib.parse.urlencode(data).encode()
            h.setdefault("Content-Type", "application/x-www-form-urlencoded")
        else:
            data = json.dumps(data).encode()
            h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with (opener or urllib.request.build_opener()).open(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")


# --- Keycloak: realm, roles, users, audience, a client without the audience, anonymous DCR ----------

def admin_token():
    s, _, b = http("POST", f"{KC}/realms/master/protocol/openid-connect/token",
                   {"grant_type": "password", "client_id": "admin-cli", "username": "admin",
                    "password": os.environ.get("KC_BOOTSTRAP_ADMIN_PASSWORD", "kc-throwaway-2026")}, form=True)
    assert s == 200, b
    return json.loads(b)["access_token"]


def setup():
    tok = admin_token()
    A = {"Authorization": f"Bearer {tok}"}
    adm = f"{KC}/admin/realms"

    def ok(call, *a, **k):
        s, h, b = http(*a, headers=A, **k)
        assert s in (200, 201, 204), (call, s, b)
        return h, b

    http("DELETE", f"{adm}/sg", headers=A)
    ok("realm", "POST", adm, {"realm": "sg", "enabled": True, "accessTokenLifespan": 300})
    for role in ("sales", "payroll"):
        ok("role", "POST", f"{adm}/sg/roles", {"name": role})
    # created before the audience scope exists, so its tokens are for some other application
    ok("other-app", "POST", f"{adm}/sg/clients", {"clientId": "other-app", "publicClient": False, "secret": "other-secret",
                                                  "serviceAccountsEnabled": True, "standardFlowEnabled": False})
    h, _ = ok("scope", "POST", f"{adm}/sg/client-scopes", {
        "name": "schemagate", "protocol": "openid-connect",
        "attributes": {"include.in.token.scope": "true"},
        "protocolMappers": [{"name": "audience", "protocol": "openid-connect", "protocolMapper": "oidc-audience-mapper",
                             "config": {"included.custom.audience": "schemagate", "access.token.claim": "true",
                                        "id.token.claim": "false"}},
                            # a client that asks only for `schemagate` gets only this scope: carry what schemagate reads
                            {"name": "username", "protocol": "openid-connect",
                             "protocolMapper": "oidc-usermodel-attribute-mapper",
                             "config": {"user.attribute": "username", "claim.name": "preferred_username",
                                        "jsonType.label": "String", "access.token.claim": "true"}},
                            {"name": "realm roles", "protocol": "openid-connect",
                             "protocolMapper": "oidc-usermodel-realm-role-mapper",
                             "config": {"claim.name": "realm_access.roles", "multivalued": "true",
                                        "jsonType.label": "String", "access.token.claim": "true"}}]})
    scope_id = h.get("Location", h.get("location")).rsplit("/", 1)[1]
    ok("default scope", "PUT", f"{adm}/sg/default-default-client-scopes/{scope_id}")
    # self-registered clients do not get every realm role: the scope says which ones it may carry
    roles = [json.loads(ok("r", "GET", f"{adm}/sg/roles/{r}")[1]) for r in ("sales", "payroll")]
    ok("scope roles", "POST", f"{adm}/sg/client-scopes/{scope_id}/scope-mappings/realm", roles)
    ok("sg-cli", "POST", f"{adm}/sg/clients", {"clientId": "sg-cli", "publicClient": True,
                                              "directAccessGrantsEnabled": True, "standardFlowEnabled": False})
    for user, role in (("sam", "sales"), ("pat", "payroll")):
        ok("user", "POST", f"{adm}/sg/users", {
            "username": user, "enabled": True, "email": f"{user}@example.test", "emailVerified": True,
            "firstName": user.title(), "lastName": "Test",
            "credentials": [{"type": "password", "value": f"{user}-pass-2026", "temporary": False}]})
        _, b = ok("find", "GET", f"{adm}/sg/users?username={user}&exact=true")
        uid = json.loads(b)[0]["id"]
        _, rb = ok("role", "GET", f"{adm}/sg/roles/{role}")
        ok("map", "POST", f"{adm}/sg/users/{uid}/role-mappings/realm", [json.loads(rb)])
    # anonymous Dynamic Client Registration, which MCP clients use: allow it from this machine
    _, b = ok("policies", "GET", f"{adm}/sg/components?type=org.keycloak.services.clientregistration.policy.ClientRegistrationPolicy")
    for c in json.loads(b):
        if c.get("subType") != "anonymous":
            continue
        if c["providerId"] == "trusted-hosts":
            # registrations may come from anywhere, but redirect URIs must stay on this machine
            c["config"].update({"host-sending-registration-request-must-match": ["false"],
                                "client-uris-must-match": ["true"],
                                "trusted-hosts": ["127.0.0.1", "localhost"]})
            ok("trusted hosts", "PUT", f"{adm}/sg/components/{c['id']}", c)
        if c["providerId"] == "allowed-client-templates":
            # the MCP client asks for the scopes the provider advertises; allow this realm's own
            _, sb = ok("scopes", "GET", f"{adm}/sg/client-scopes")
            c["config"].update({"allow-default-scopes": ["true"],
                                "allowed-client-scopes": [x["name"] for x in json.loads(sb)]})
            ok("allowed scopes", "PUT", f"{adm}/sg/components/{c['id']}", c)
        if c["providerId"] == "consent-required":
            ok("no consent screen", "DELETE", f"{adm}/sg/components/{c['id']}")
    return A


def password_token(user, client="sg-cli"):
    s, _, b = http("POST", f"{ISSUER}/protocol/openid-connect/token",
                   {"grant_type": "password", "client_id": client, "username": user,
                    "password": f"{user}-pass-2026", "scope": "openid schemagate"}, form=True)
    assert s == 200, b
    return json.loads(b)["access_token"]


# --- schemagate from PyPI ----------------------------------------------------------------------

def start_server(python):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SCHEMAGATE_") and k != "PYTHONPATH"}
    env.update(SCHEMAGATE_MCP_TRANSPORT="streamable-http", SCHEMAGATE_MCP_PORT=str(PORT),
               SCHEMAGATE_MCP_OAUTH_ISSUER=ISSUER, SCHEMAGATE_MCP_OAUTH_AUDIENCE="schemagate",
               SCHEMAGATE_MCP_OAUTH_RESOURCE=f"{BASE}/mcp",
               SCHEMAGATE_MCP_OAUTH_ROLES_CLAIM="realm_access.roles",
               SCHEMAGATE_MCP_OAUTH_SUBJECT_CLAIM="preferred_username",
               SCHEMAGATE_MCP_OAUTH_NAMESPACE="keycloak", SCHEMAGATE_MCP_OAUTH_SCOPES="schemagate",
               SCHEMAGATE_AUTO_DESCRIBE="0", PYTHONIOENCODING="utf-8")
    import tempfile
    global LOG
    LOG = os.path.join(tempfile.mkdtemp(), "server.log")
    log = open(LOG, "w", encoding="utf-8")
    proc = subprocess.Popen([python, "-m", "schemagate.mcp_server", "--url", "demo"], env=env, stdout=log,
                            stderr=subprocess.STDOUT, cwd=tempfile.gettempdir())
    for _ in range(240):
        try:
            if http("GET", f"{BASE}/.well-known/oauth-protected-resource/mcp")[0] == 200:
                return proc
        except OSError:
            pass
        if proc.poll() is not None:
            raise SystemExit("server exited:\n" + open(LOG, encoding="utf-8").read()[-3000:])
        time.sleep(0.5)
    raise SystemExit("server did not start")


class Raw:
    """MCP over streamable HTTP by hand, for the negative cases."""

    def __init__(self, token):
        self.h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        if token:
            self.h["Authorization"] = f"Bearer {token}"
        self.n = 0

    def post(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}
        if not notify:
            self.n += 1
            msg["id"] = self.n
        return http("POST", f"{BASE}/mcp", json.dumps(msg).encode(), self.h)

    @staticmethod
    def body(resp):
        s, h, b = resp
        if h.get("Content-Type", h.get("content-type", "")).startswith("application/json"):
            return json.loads(b)
        return json.loads(next(line[5:] for line in b.splitlines() if line.startswith("data:")))

    def start(self):
        r = self.post("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "raw", "version": "0"}})
        assert r[0] == 200, r
        self.h["mcp-session-id"] = r[1].get("mcp-session-id", r[1].get("Mcp-Session-Id", ""))
        self.h["mcp-protocol-version"] = self.body(r)["result"]["protocolVersion"]
        self.post("notifications/initialized", notify=True)
        return self

    def call(self, tool, **a):
        res = self.body(self.post("tools/call", {"name": tool, "arguments": a}))["result"]
        sc = res.get("structuredContent")
        if sc:
            return sc["result"] if set(sc) == {"result"} else sc
        return json.loads("".join(c.get("text", "") for c in res["content"]))


# --- a person signing in at Keycloak's login page ---------------------------------------------

def browser_login(auth_url, user):
    """What the user does in the browser: open the URL, type a password, get sent back with a code."""
    class LocalhostIsSecure(cookiejar.DefaultCookiePolicy):
        """Browsers send Secure cookies to http://localhost (a secure context); urllib does not."""

        def return_ok_secure(self, cookie, request):
            return True

    jar = cookiejar.CookieJar(policy=LocalhostIsSecure())
    caught = {}

    class Stop(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if newurl.startswith(REDIRECT):
                caught["url"] = newurl
                return None
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), Stop())
    s, _, page = http("GET", auth_url, opener=opener)
    m = re.search(r'<form[^>]+id="kc-form-login"[^>]+action="([^"]+)"', page)
    assert s == 200 and m, (s, page[:800])
    s2, _, after = http("POST", html.unescape(m.group(1)), {"username": user, "password": f"{user}-pass-2026",
                                                             "credentialId": ""}, form=True, opener=opener)
    if "url" not in caught:
        text = re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<(script|style).*?</\1>", "", after))
        raise AssertionError(f"no redirect back with a code: {s2} " + " ".join(text.split())[:700])
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(caught["url"]).query)
    return {k: v[0] for k, v in q.items()}


async def official_client(user):
    """The MCP SDK's own OAuth client: 401 -> metadata -> registration -> PKCE login -> token -> tools."""
    from mcp import ClientSession
    from mcp.client.auth import OAuthClientProvider
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
    from mcp.shared.auth import AuthorizationCodeResult, OAuthClientMetadata

    class Mem:
        tokens = client = None

        async def get_tokens(self):
            return self.tokens

        async def set_tokens(self, t):
            self.tokens = t

        async def get_client_info(self):
            return self.client

        async def set_client_info(self, c):
            self.client = c

    seen = {}

    async def redirect(url):
        seen["auth_url"] = url
        seen.update(await asyncio.to_thread(browser_login, url, user))

    async def callback():
        return AuthorizationCodeResult(code=seen["code"], state=seen.get("state"), iss=seen.get("iss"))

    store = Mem()
    provider = OAuthClientProvider(
        server_url=f"{BASE}/mcp", storage=store, redirect_handler=redirect, callback_handler=callback,
        client_metadata=OAuthClientMetadata(client_name="schemagate e2e", redirect_uris=[REDIRECT],
                                            grant_types=["authorization_code", "refresh_token"],
                                            response_types=["code"], token_endpoint_auth_method="none"))
    out = {}
    async with create_mcp_http_client(auth=provider) as hc:
        async with streamable_http_client(f"{BASE}/mcp", http_client=hc) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as s:
                await s.initialize()

                async def call(tool, **a):
                    res = await s.call_tool(tool, a)
                    sc = getattr(res, "structured_content", None) or getattr(res, "structuredContent", None)
                    if sc:
                        return sc["result"] if set(sc) == {"result"} else sc
                    return json.loads("".join(getattr(c, "text", "") for c in res.content))

                out["hr_spoof"] = await call("run_query", sql="SELECT * FROM hr_compensation",
                                             principal="okta:admin", roles=["payroll"])
                out["hr_count"] = await call("run_query", sql="SELECT COUNT(*) FROM hr_compensation")
                out["objects"] = json.dumps(await call("list_objects", roles=["payroll"]))
                out["select"] = await call("select_schema", question="salary and bonus per employee",
                                           roles=["payroll"])
                out["health"] = await call("health")
    out["auth_url"] = seen.get("auth_url", "")
    out["client_id"] = store.client.client_id if store.client else None
    return out


def main(python):
    setup()
    print("keycloak realm ready", flush=True)
    proc = start_server(python)
    try:
        run()
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
    if not all(R):
        print("\n--- server log ---\n" + open(LOG, encoding="utf-8").read()[-4000:])
    print(f"\n[keycloak] RESULT {sum(R)}/{len(R)}")
    sys.exit(0 if R and all(R) else 1)


def run():
    # discovery, as a client that knows nothing but the URL does it
    s, h, b = Raw(None).post("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                            "clientInfo": {"name": "x", "version": "0"}})
    wa = h.get("WWW-Authenticate", h.get("www-authenticate", ""))
    m = re.search(r'resource_metadata="([^"]+)"', wa)
    rec("no token: 401 with resource_metadata", s == 401 and bool(m), (s, wa))
    meta = json.loads(http("GET", m.group(1))[2])
    rec("metadata names Keycloak as the authorization server",
        meta["authorization_servers"] == [ISSUER] and meta["resource"] == f"{BASE}/mcp", meta)
    oidc = json.loads(http("GET", f"{ISSUER}/.well-known/openid-configuration")[2])
    rec("Keycloak offers registration and PKCE S256",
        bool(oidc.get("registration_endpoint")) and "S256" in oidc.get("code_challenge_methods_supported", []))

    # the SDK's own OAuth client, end to end, as two different people
    sam = asyncio.run(official_client("sam"))
    rec("official client: registered itself with Keycloak (DCR)", bool(sam["client_id"]), sam["client_id"])
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(sam["auth_url"]).query)
    rec("official client: authorization request used PKCE S256",
        q.get("code_challenge_method") == ["S256"] and bool(q.get("code_challenge")), sam["auth_url"][:300])
    rec("sam (sales): hr_compensation refused despite roles=['payroll'] and principal='okta:admin'",
        "error" in sam["hr_spoof"] and "rows" not in sam["hr_spoof"], sam["hr_spoof"])
    rec("sam (sales): COUNT on hr_compensation refused too", "rows" not in sam["hr_count"], sam["hr_count"])
    rec("sam (sales): list_objects hides hr_compensation", "hr_compensation" not in sam["objects"], sam["objects"][:300])
    rec("sam (sales): select_schema never shows hr_compensation",
        "hr_compensation" not in json.dumps(sam["select"]), json.dumps(sam["select"])[:300])
    rec("health says auth=oauth", sam["health"].get("auth") == "oauth", sam["health"])

    pat = asyncio.run(official_client("pat"))
    rec("pat (payroll): hr_compensation rows come back", bool(pat["hr_count"].get("rows")), pat["hr_count"])
    rec("pat: principal is keycloak:pat from the token, not okta:admin from the arguments",
        pat["hr_spoof"].get("principal") == "keycloak:pat", pat["hr_spoof"])
    rec("pat (payroll): list_objects includes hr_compensation", "hr_compensation" in pat["objects"])

    # tokens Keycloak really issued, that must still be refused
    s, _, b = http("POST", f"{ISSUER}/protocol/openid-connect/token",
                   {"grant_type": "client_credentials", "client_id": "other-app", "client_secret": "other-secret"},
                   form=True)
    other = json.loads(b)["access_token"]
    r = Raw(other).post("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                       "clientInfo": {"name": "x", "version": "0"}})
    rec("a real Keycloak token for another application (no schemagate audience): 401", r[0] == 401, r[:2])
    r = Raw(admin_token()).post("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                               "clientInfo": {"name": "x", "version": "0"}})
    rec("a real token from another realm (another issuer): 401", r[0] == 401, r[:2])
    good = password_token("pat")
    head, body, sig = good.split(".")
    claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    claims["realm_access"] = {"roles": ["payroll", "admin"]}
    forged = head + "." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=") + "." + sig
    r = Raw(forged).post("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                        "clientInfo": {"name": "x", "version": "0"}})
    rec("pat's real token with edited roles (signature no longer matches): 401", r[0] == 401, r[:2])

    # the token decides every time: take payroll away from pat, sign in again
    A = {"Authorization": f"Bearer {admin_token()}"}
    uid = json.loads(http("GET", f"{KC}/admin/realms/sg/users?username=pat&exact=true", headers=A)[2])[0]["id"]
    role = json.loads(http("GET", f"{KC}/admin/realms/sg/roles/payroll", headers=A)[2])
    s = http("DELETE", f"{KC}/admin/realms/sg/users/{uid}/role-mappings/realm", json.dumps([role]).encode(),
             {**A, "Content-Type": "application/json"})[0]
    c = Raw(password_token("pat"))
    r = c.post("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "x", "version": "0"}})
    if r[0] == 200:      # still admitted: then the tool must refuse
        c.n = 0
        out = c.start().call("run_query", sql="SELECT COUNT(*) FROM hr_compensation")
        refused = "rows" not in out
    else:                # Keycloak dropped the scope with the role, so the token no longer has our audience
        out, refused = r[:1], r[0] == 401
    rec("payroll removed from pat in Keycloak: pat's next token cannot read hr_compensation",
        s == 204 and refused, (s, out))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else sys.executable)
