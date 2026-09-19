"""Where a caller's roles come from.

Before this, the MCP server used whatever roles the client sent. These tests
are about the three properties that make a resolver safe to put in front of
that: it fails closed, it ignores what the client claims, and every source
answers only for the namespaces it serves.
"""
from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import urllib.request

import pytest
from sqlalchemy import create_engine

from schemagate import Principal
from schemagate.grants import ROLE_GRAPH_READERS
from schemagate.groups import (DatabaseGroups, EntraGroups, GroupError, Groups,
                               HttpGroups, NativeRoles, StaticGroups,
                               from_config, local_part)


# --- fakes -----------------------------------------------------------------

class FakeEngine:
    def __init__(self, name="fakedb"):
        class D:
            pass
        self.dialect = D()
        self.dialect.name = name


class Answers:
    """Scripted urlopen. Each entry: (substring of URL, status, JSON body)."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.calls.append((url, req.get_method(), dict(req.header_items()),
                           req.data.decode() if req.data else None))
        for needle, status, body in self.script:
            if needle in url:
                if status != 200:
                    raise urllib.error.HTTPError(url, status, "err", {}, io.BytesIO(json.dumps(body).encode()))
                return _Resp(json.dumps(body).encode())
        raise AssertionError(f"unscripted URL {url}")


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def urlopen(monkeypatch):
    def install(*script):
        a = Answers(*script)
        monkeypatch.setattr(urllib.request, "urlopen", a)
        return a
    return install


@pytest.fixture
def fake_graph():
    """A role graph reader registered for a fake dialect, cleaned up after."""
    ROLE_GRAPH_READERS["fakedb"] = lambda e: {
        # GRANT reporting TO analysts; GRANT analysts TO jdoe; GRANT ops TO mbrown
        "reporting": {"analysts"}, "analysts": {"jdoe"}, "ops": {"mbrown"},
        # a cycle, because GRANT a TO b; GRANT b TO a is legal
        "loop_a": {"loop_b"}, "loop_b": {"loop_a", "cyclic_user"},
    }
    yield FakeEngine("fakedb")
    ROLE_GRAPH_READERS.pop("fakedb", None)


# --- static ------------------------------------------------------------------

def test_static_groups_by_subject():
    s = StaticGroups({"okta:jdoe": ["finance", "  "], "OKTA:mbrown": ["ops"]})
    assert s.groups("okta:jdoe") == {"finance"}
    assert s.groups("Okta:mbrown") == {"ops"}          # namespace case-insensitive
    assert s.groups("okta:JDOE") == set()               # local part is not
    assert s.groups("db:jdoe") == set()                 # different person


def test_local_part_and_namespace_routing():
    assert local_part("okta:jdoe") == "jdoe"
    assert local_part("entra:jdoe@contoso.com") == "jdoe@contoso.com"
    s = StaticGroups({"okta:jdoe": ["x"]}, serves=["okta"])
    assert s.applies("okta:jdoe") and not s.applies("entra:jdoe")


# --- the resolver ------------------------------------------------------------

def test_map_translates_and_passthrough_keeps_the_rest():
    g = Groups([StaticGroups({"okta:jdoe": ["Finance Analysts", "5f1c-guid"]})],
               map={"5f1c-guid": "finance"})
    assert g.roles_for("okta:jdoe") == {"finance", "Finance Analysts"}


def test_passthrough_off_is_a_strict_allow_list():
    g = Groups([StaticGroups({"okta:jdoe": ["Finance Analysts", "5f1c-guid"]})],
               map={"5f1c-guid": "finance"}, passthrough=False)
    assert g.roles_for("okta:jdoe") == {"finance"}


def test_sources_are_a_union_and_only_matching_namespaces_answer():
    a = StaticGroups({"okta:jdoe": ["a"]}, serves=["okta"])
    b = StaticGroups({"okta:jdoe": ["b"], "entra:jdoe": ["c"]}, serves=["entra"])
    g = Groups([a, b])
    assert g.roles_for("okta:jdoe") == {"a"}            # b serves entra only
    assert g.roles_for("entra:jdoe") == {"c"}
    assert g.roles_for("db:jdoe") == set()              # nobody serves db:


def test_principal_carries_the_directory_roles_not_the_callers():
    g = Groups([StaticGroups({"okta:jdoe": ["finance"]})])
    claimed = Principal("okta:jdoe", roles={"payroll"})
    who = g.resolve(claimed)
    assert who.roles == {"finance"}
    assert who.subject == "okta:jdoe"
    assert g.principal("okta:jdoe").roles == {"finance"}


def test_principal_still_validates_the_namespace():
    g = Groups([StaticGroups({})])
    with pytest.raises(Exception, match="namespaced"):
        g.principal("no-namespace")


class Failing(StaticGroups):
    name = "failing"

    def groups(self, subject):
        raise ConnectionError("idp down: https://idp/x?token=SECRET")


def test_a_failing_source_raises_and_never_becomes_no_roles():
    g = Groups([StaticGroups({"okta:jdoe": ["finance"]}), Failing({})])
    with pytest.raises(GroupError) as e:
        g.roles_for("okta:jdoe")
    assert "failing source failed" in str(e.value)
    assert g.stats["errors"] == 1
    # and nothing was cached, so the next call asks again
    assert g.describe()["cached"] == 0


def test_cache_honours_ttl_and_forget():
    calls = []

    class Counting(StaticGroups):
        def groups(self, subject):
            calls.append(subject)
            return super().groups(subject)

    now = [1000.0]
    g = Groups([Counting({"okta:jdoe": ["finance"]})], ttl=300, clock=lambda: now[0])
    assert g.roles_for("okta:jdoe") == {"finance"}
    assert g.roles_for("okta:jdoe") == {"finance"}
    assert len(calls) == 1                              # served from cache
    now[0] += 301
    g.roles_for("okta:jdoe")
    assert len(calls) == 2                              # ttl elapsed, re-asked
    g.forget("okta:jdoe")
    g.roles_for("okta:jdoe")
    assert len(calls) == 3                              # revocation honoured now
    assert g.stats == {"hits": 1, "misses": 3, "errors": 0}


def test_cache_is_bounded():
    g = Groups([StaticGroups({})], maxsize=2)
    for i in range(5):
        g.roles_for(f"okta:u{i}")
    assert g.describe()["cached"] == 2


def test_describe_has_counts_and_no_names():
    g = Groups([StaticGroups({"okta:jdoe": ["Finance Analysts"]})], map={"x": "y"})
    g.roles_for("okta:jdoe")
    d = g.describe()
    assert d["sources"] == ["static"] and d["mapped"] == 1 and d["cached"] == 1
    assert "jdoe" not in json.dumps(d) and "Finance" not in json.dumps(d)


# --- sql --------------------------------------------------------------------

@pytest.fixture
def membership_engine():
    p = tempfile.mktemp(suffix=".db")
    c = sqlite3.connect(p)
    c.executescript("""
        CREATE TABLE app_membership (subject TEXT, role TEXT);
        INSERT INTO app_membership VALUES ('jdoe', 'finance'), ('jdoe', 'reporting'),
                                          ('okta:mbrown', 'ops'), ('x', NULL);
    """)
    c.commit(); c.close()
    return create_engine(f"sqlite:///{p}")


def test_sql_source_binds_the_local_part_by_default(membership_engine):
    s = DatabaseGroups(membership_engine,
                       "SELECT role FROM app_membership WHERE subject = :subject")
    assert s.groups("okta:jdoe") == {"finance", "reporting"}
    assert s.groups("okta:nobody") == set()
    assert s.groups("okta:x") == set()                  # NULL row dropped


def test_sql_source_can_bind_the_whole_subject(membership_engine):
    s = DatabaseGroups(membership_engine,
                       "SELECT role FROM app_membership WHERE subject = :subject",
                       bind="subject")
    assert s.groups("okta:mbrown") == {"ops"}
    assert s.groups("okta:jdoe") == set()


def test_sql_source_is_bound_not_formatted(membership_engine):
    s = DatabaseGroups(membership_engine,
                       "SELECT role FROM app_membership WHERE subject = :subject")
    assert s.groups("okta:jdoe' OR '1'='1") == set()


# --- native -------------------------------------------------------------------

def test_native_roles_walk_the_graph_upward_transitively(fake_graph):
    s = NativeRoles(fake_graph)
    assert s.groups("db:jdoe") == {"analysts", "reporting"}
    assert s.groups("db:JDOE") == {"analysts", "reporting"}     # Oracle spelling
    assert s.groups("db:mbrown") == {"ops"}
    assert s.groups("db:nobody") == set()


def test_native_roles_survive_a_cycle(fake_graph):
    assert NativeRoles(fake_graph).groups("db:cyclic_user") == {"loop_a", "loop_b"}


def test_native_roles_serve_db_subjects_only(fake_graph):
    s = NativeRoles(fake_graph)
    assert s.applies("db:jdoe") and not s.applies("okta:jdoe")


def test_native_roles_fail_closed_on_an_unsupported_dialect():
    with pytest.raises(GroupError, match="not readable"):
        NativeRoles(FakeEngine("nosuchdb")).groups("db:jdoe")


# --- http ---------------------------------------------------------------------

def test_http_source_list_of_strings(urlopen):
    a = urlopen(("/users/jdoe/groups", 200, ["finance", "ops"]))
    s = HttpGroups("https://idp.example.com/users/{id}/groups",
                   headers={"Authorization": "Bearer t"})
    assert s.groups("okta:jdoe") == {"finance", "ops"}
    _url, method, headers, _ = a.calls[0]
    assert method == "GET" and headers["Authorization"] == "Bearer t"


def test_http_source_object_forms_and_url_quoting(urlopen):
    urlopen(("/users/jdoe%40contoso.com", 200,
             {"value": [{"id": "g1", "displayName": "Finance"}, {"name": "ops"}]}))
    s = HttpGroups("https://idp/users/{id}")
    assert s.groups("okta:jdoe@contoso.com") == {"g1", "Finance", "ops"}


def test_http_source_custom_path_and_bad_shapes(urlopen):
    urlopen(("/a/", 200, {"memberships": ["x"]}), ("/b/", 200, {"nope": 1}),
            ("/c/", 200, "a string"))
    assert HttpGroups("https://idp/a/{id}", path="memberships").groups("o:u") == {"x"}
    with pytest.raises(GroupError, match="none of"):
        HttpGroups("https://idp/b/{id}").groups("o:u")
    with pytest.raises(GroupError, match="not a list"):
        HttpGroups("https://idp/c/{id}").groups("o:u")


def test_http_errors_fail_closed_with_status_not_secret(urlopen):
    urlopen(("/users/", 403, {"error": "forbidden"}))
    s = HttpGroups("https://idp/users/{id}", headers={"Authorization": "Bearer SECRET"})
    with pytest.raises(GroupError) as e:
        s.groups("okta:jdoe")
    assert "HTTP 403" in str(e.value) and "SECRET" not in str(e.value)


def test_http_unreachable_fails_closed(monkeypatch):
    def down(req, timeout=None):
        raise urllib.error.URLError("connection refused")
    monkeypatch.setattr(urllib.request, "urlopen", down)
    with pytest.raises(GroupError, match="could not reach"):
        HttpGroups("https://idp/users/{id}").groups("okta:jdoe")


# --- entra --------------------------------------------------------------------

TOKEN = ("/oauth2/v2.0/token", 200, {"access_token": "tok", "expires_in": 3600})
MEMBER = ("/getMemberGroups", 200, {"value": ["g-fin", "g-all"]})
NAMES = ("/directoryObjects/getByIds", 200,
         {"value": [{"id": "g-fin", "displayName": "Finance Analysts"},
                    {"id": "g-all", "displayName": "All Staff"}]})


def test_entra_resolves_transitive_ids_and_names(urlopen):
    a = urlopen(TOKEN, MEMBER, NAMES)
    s = EntraGroups("contoso.onmicrosoft.com", "cid", "csecret")
    got = s.groups("entra:jdoe@contoso.com")
    assert got == {"g-fin", "g-all", "Finance Analysts", "All Staff"}
    token_url, _, _, form = a.calls[0]
    assert "login.microsoftonline.com/contoso.onmicrosoft.com" in token_url
    assert "client_secret=csecret" in form and "client_credentials" in form
    member_url, method, headers, body = a.calls[1]
    assert member_url.endswith("/users/jdoe@contoso.com/getMemberGroups")
    assert method == "POST" and headers["Authorization"] == "Bearer tok"
    assert json.loads(body) == {"securityEnabledOnly": False}
    assert json.loads(a.calls[2][3])["ids"] == ["g-all", "g-fin"]


def test_entra_token_is_reused_and_security_only_is_sent(urlopen):
    a = urlopen(TOKEN, MEMBER, NAMES)
    s = EntraGroups("t", "cid", "csecret", security_only=True, names=False)
    s.groups("entra:a"); s.groups("entra:b")
    token_calls = [c for c in a.calls if "/token" in c[0]]
    assert len(token_calls) == 1
    assert json.loads(a.calls[1][3]) == {"securityEnabledOnly": True}
    assert not any("getByIds" in c[0] for c in a.calls)


def test_entra_secret_never_appears_in_repr_or_errors(urlopen):
    urlopen(TOKEN, ("/getMemberGroups", 403,
                    {"error": {"code": "Authorization_RequestDenied",
                               "message": "Insufficient privileges"}}))
    s = EntraGroups("t", "cid", "csecret")
    assert "csecret" not in repr(s)
    with pytest.raises(GroupError) as e:
        s.groups("entra:jdoe")
    msg = str(e.value)
    assert "HTTP 403" in msg and "Insufficient privileges" in msg
    assert "csecret" not in msg and "tok" not in msg


def test_entra_needs_all_three_settings():
    with pytest.raises(GroupError, match="needs tenant"):
        EntraGroups("t", "", "s")


# --- config -------------------------------------------------------------------

def test_from_config_builds_every_source_and_expands_env(membership_engine):
    env = {"ENTRA_CLIENT_SECRET": "s3", "API_TOKEN": "t9"}
    g = from_config({
        "ttl": 60, "map": {"g-fin": "finance"}, "passthrough": False,
        "sources": [
            {"type": "static", "members": {"okta:jdoe": ["g-fin", "other"]}},
            {"type": "sql", "url": "sqlite://", "sql": "SELECT 1", "for": ["okta"]},
            {"type": "native", "url": "sqlite://"},
            {"type": "http", "url": "https://idp/{id}",
             "headers": {"Authorization": "Bearer ${API_TOKEN}"}, "for": ["okta"]},
            {"type": "entra", "tenant": "t", "client_id": "c",
             "client_secret": "${ENTRA_CLIENT_SECRET}"},
        ]}, env=env, engine_factory=lambda url: membership_engine)
    assert [s.name for s in g.sources] == ["static", "sql", "native", "http", "entra"]
    assert g.ttl == 60 and g.passthrough is False and g.map == {"g-fin": "finance"}
    assert g.sources[3]._headers["Authorization"] == "Bearer t9"
    assert g.sources[4]._secret == "s3"
    assert g.sources[2].serves == {"db"}                # native default
    assert g.sources[4].serves == {"entra", "aad", "azuread"}


def test_from_config_unset_env_ref_is_an_error_not_empty():
    with pytest.raises(GroupError, match=r"\$\{ENTRA_CLIENT_SECRET\} but it is not set"):
        from_config({"sources": [{"type": "entra", "tenant": "t", "client_id": "c",
                                  "client_secret": "${ENTRA_CLIENT_SECRET}"}]}, env={})


def test_from_config_single_source_unwrapped_and_defaults():
    g = from_config({"type": "static", "members": {"okta:jdoe": ["x"]}}, env={})
    assert g.roles_for("okta:jdoe") == {"x"} and g.ttl == 300.0


def test_from_config_absent_or_empty_means_trust_the_caller():
    assert from_config(None) is None
    assert from_config({}) is None
    assert from_config({"map": {"a": "b"}}, env={}) is None


def test_from_config_rejects_unknown_types_and_missing_fields():
    with pytest.raises(GroupError, match="unknown groups source type"):
        from_config({"sources": [{"type": "ldap"}]}, env={})
    with pytest.raises(GroupError, match="needs a url"):
        from_config({"sources": [{"type": "http"}]}, env={})
    with pytest.raises(GroupError, match="sql"):
        from_config({"sources": [{"type": "sql", "url": "sqlite://"}]}, env={})
    with pytest.raises(GroupError, match="needs a url"):
        from_config({"sources": [{"type": "native"}]}, env={})   # no default_url


def test_from_config_uses_the_catalog_url_as_default(membership_engine):
    seen = []

    def factory(url):
        seen.append(url)
        return membership_engine
    from_config({"sources": [{"type": "native"}]}, env={},
                default_url="postgresql://x", engine_factory=factory)
    assert seen == ["postgresql://x"]


# --- the MCP server uses it and ignores what the client claims ---------------

def test_mcp_server_ignores_client_roles_when_groups_are_configured(cat):
    from schemagate import mcp_server
    cat.restrict("hr_compensation", ["payroll"])
    groups = Groups([StaticGroups({"okta:hr": ["payroll"], "okta:x": ["finance"]})])
    mcp_server.build_catalog(catalog=cat, groups=groups)
    try:
        # the directory says yes -- no roles needed from the client
        out = mcp_server.select_schema("salary by employee", top_k=10, principal="okta:hr")
        assert "hr_compensation" in " ".join(out["objects"])
        # the client claims payroll; the directory says finance. Claim ignored.
        out = mcp_server.select_schema("salary by employee", top_k=10,
                                       principal="okta:x", roles=["payroll"])
        assert "hr_compensation" not in " ".join(out["objects"])
        # unknown to the directory: no roles, not an error
        out = mcp_server.select_schema("salary by employee", top_k=10, principal="okta:new")
        assert "hr_compensation" not in " ".join(out["objects"])
        assert mcp_server.health()["groups"]["sources"] == ["static"]
    finally:
        mcp_server.build_catalog(catalog=cat)          # groups=None again
    assert mcp_server.health()["groups"] is None


def test_mcp_server_fails_closed_when_the_directory_is_down(cat):
    from schemagate import mcp_server
    cat.restrict("hr_compensation", ["payroll"])
    mcp_server.build_catalog(catalog=cat, groups=Groups([Failing({})]))
    try:
        out = mcp_server.select_schema("salary by employee", top_k=10, principal="okta:hr")
        assert "error" in out and "failing source failed" in out["error"]
        assert "objects" not in out
        out = mcp_server.run_query("SELECT 1", principal="okta:hr")
        assert "error" in out and "rows" not in out
    finally:
        mcp_server.build_catalog(catalog=cat)


def test_mcp_anonymous_caller_is_unchanged_by_groups(cat):
    from schemagate import mcp_server
    cat.restrict("hr_compensation", ["payroll"])
    mcp_server.build_catalog(catalog=cat, groups=Groups([StaticGroups({"okta:hr": ["payroll"]})]))
    try:
        out = mcp_server.select_schema("salary by employee", top_k=10)
        assert "hr_compensation" not in " ".join(out["objects"])
    finally:
        mcp_server.build_catalog(catalog=cat)


# --- the CLI ------------------------------------------------------------------

def test_cli_select_resolves_principal_from_config(db_url, tmp_path, capsys):
    from schemagate.cli import main
    cfg = tmp_path / "catalog.json"
    cfg.write_text(json.dumps({
        "restrict": {"hr_compensation": ["payroll"]},
        "groups": {"sources": [{"type": "static", "members": {"okta:hr": ["payroll"]}}]},
    }), "utf-8")
    main(["select", "salary by employee", "--url", db_url, "--config", str(cfg),
          "--principal", "okta:hr", "--top-k", "10"])
    assert "hr_compensation" in capsys.readouterr().out
    main(["select", "salary by employee", "--url", db_url, "--config", str(cfg),
          "--principal", "okta:other", "--top-k", "10"])
    assert "hr_compensation" not in capsys.readouterr().out


def test_cli_explicit_role_wins_over_config(db_url, tmp_path, capsys):
    from schemagate.cli import main
    cfg = tmp_path / "catalog.json"
    cfg.write_text(json.dumps({
        "restrict": {"hr_compensation": ["payroll"]},
        "groups": {"sources": [{"type": "static", "members": {}}]},
    }), "utf-8")
    main(["select", "salary by employee", "--url", db_url, "--config", str(cfg),
          "--principal", "okta:hr", "--role", "payroll", "--top-k", "10"])
    assert "hr_compensation" in capsys.readouterr().out
