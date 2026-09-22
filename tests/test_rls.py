"""Row-level policies, without a server: the marking, the probing logic, the
views that bypass the policy, and the one line the prompt gains.

The measurement that motivated this is in docs/row-level-security.md: a
reader whose policy admits no rows holds every permission the dictionary
records. These tests pin what the library does about it once a reader has
told it which objects are policied.
"""
from __future__ import annotations

from sqlalchemy import create_engine

import pytest

from schemagate import Principal
from schemagate.models import POLICY_NOTE
from schemagate.rls import (CannotSetRole, PolicyReport, apply_policies,
                            restrict_from_policies)


def _two(cat):
    docs = sorted(cat._docs.values(), key=lambda d: d.name)
    assert len(docs) >= 2
    return docs[0], docs[1]


def _key(doc):
    return (doc.schema, doc.name)


def test_the_note_appears_only_when_the_object_is_flagged(cat):
    a, _ = _two(cat)
    before = a.render_ddl()
    assert POLICY_NOTE not in before
    a.extra["row_policy"] = True
    after = a.render_ddl()
    assert f"-- {POLICY_NOTE}" in after
    # one line added, nothing else touched
    assert [l for l in after.splitlines() if POLICY_NOTE not in l] == before.splitlines()
    a.extra.clear()


def test_a_dialect_without_a_reader_is_a_warning_not_a_change(cat, db_url):
    rep = restrict_from_policies(cat, create_engine(db_url), report=True)
    assert rep.dialect == "sqlite"
    assert any("no row-level policy reader" in w for w in rep.warnings)
    assert not rep.policied and not rep.withheld
    assert not any(d.extra for d in cat._docs.values())


def test_flagged_and_withheld_from_the_role_that_gets_nothing(cat):
    a, b = _two(cat)
    a.roles = ["r1", "r2"]
    asked = []

    def probe(role, schema, name):
        asked.append((role, name))
        return role == "r1"

    rep = apply_policies(cat, {_key(a)}, set(), probe=probe)
    assert a.extra["row_policy"] is True and "row_policy" not in b.extra
    assert a.roles == ["r1"]
    assert rep.withheld == [f"{a.qname} <- r2"]
    assert rep.probed == 2 and asked == [("r1", a.name), ("r2", a.name)]
    assert rep.policied == [a.qname]
    a.roles = None; a.extra.clear()


def test_a_role_the_connection_cannot_become_is_kept_and_named(cat):
    a, _ = _two(cat)
    a.roles = ["r1", "r2"]

    def probe(role, schema, name):
        if role == "r2":
            raise CannotSetRole("permission denied to set role")
        return True

    rep = apply_policies(cat, {_key(a)}, set(), probe=probe)
    # "could not check" never reads as "checked and denied"
    assert a.roles == ["r1", "r2"]
    assert rep.unprobed_roles == ["r2"] and not rep.withheld
    assert any("could not act as r2" in w for w in rep.warnings)
    a.roles = None; a.extra.clear()


def test_a_public_policied_object_is_flagged_and_the_gap_is_said(cat):
    a, _ = _two(cat)
    a.roles = None
    rep = apply_policies(cat, {_key(a)}, set(), probe=lambda *x: True)
    assert a.extra["row_policy"] is True and a.roles is None
    assert rep.probed == 0
    assert any("readable by PUBLIC" in w for w in rep.warnings)
    a.extra.clear()


def test_a_bypassing_view_is_flagged_and_can_be_hidden(cat):
    a, b = _two(cat)
    rep = apply_policies(cat, set(), {_key(b)})
    assert b.extra["policy_bypass"] is True and rep.bypassing_views == [b.qname]
    assert b.roles is None                    # flagged, still visible
    apply_policies(cat, set(), {_key(b)}, hide_bypassing_views=True)
    # an empty role list would mean "everyone" under the one visibility rule,
    # so hiding removes the object, exactly as exclude= at bootstrap does
    assert all(d is not b for d in cat._docs.values())
    who = Principal("okta:anyone", roles=frozenset({"r1", "payroll", "admin"}))
    names = {getattr(o, "name", o) for o in cat.select(b.name, top_k=20, principal=who).objects}
    assert b.name not in names
    b.extra.clear()


def test_matching_ignores_case_and_qualification(cat):
    a, _ = _two(cat)
    rep = apply_policies(cat, {("PUBLIC" if a.schema is None else a.schema.upper(),
                                a.name.upper())}, set())
    assert a.extra.get("row_policy") is True, "an upper-cased dictionary spelling must still match"
    assert rep.policied == [a.qname]
    a.extra.clear()


def test_the_report_reads_as_a_sentence():
    rep = PolicyReport(dialect="postgresql", policied=["public.t"],
                       bypassing_views=["public.v"], probed=3,
                       withheld=["public.t <- r2"], unprobed_roles=["r9"],
                       warnings=["x"])
    s = str(rep)
    for bit in ("postgresql", "1 policied", "1 policy-bypassing", "3 probe",
                "withheld: public.t <- r2", "bypasses the policy: public.v",
                "cannot act as them): r9", "warning: x"):
        assert bit in s, bit


# --- Oracle: identifier then proxy, without a database -----------------------

class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConn:
    """Answers the three statements the Oracle prober sends. `rows` is a
    function of (identifier, session_user) -> bool: does one row come back."""

    def __init__(self, engine, session_user):
        self.engine = engine
        self.session_user = session_user

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def exec_driver_sql(self, sql, params=None):
        e = self.engine
        e.log.append((self.session_user, sql.split("(")[0].strip(), params))
        if "SET_IDENTIFIER" in sql:
            e.identifier = params[0]
            return _FakeResult(None)
        if "CLEAR_IDENTIFIER" in sql:
            e.identifier = None
            return _FakeResult(None)
        if "FROM dual" in sql:
            return _FakeResult((1,))
        got = e.rows(e.identifier, self.session_user)
        return _FakeResult((1,) if got else None)


class _FakeURL:
    def __init__(self, username):
        self.username = username

    def set(self, username):
        return _FakeURL(username)


class _FakeEngine:
    def __init__(self, rows, session_user="APP", proxy_ok=True, url=None, shared=None):
        from sqlalchemy.dialects import oracle
        self.dialect = oracle.dialect()
        self.rows = rows
        self.session_user = session_user
        self.proxy_ok = proxy_ok
        self.url = url or _FakeURL("APP")
        self.log = shared.log if shared else []
        self.identifier = None
        self.disposed = False

    def connect(self):
        return _FakeConn(self, self.session_user)

    def dispose(self):
        self.disposed = True


def _oracle_prober(monkeypatch, rows, proxy_ok=True):
    """An _OracleProber whose proxied engines are fakes sharing one log."""
    from schemagate import rls
    app = _FakeEngine(rows)
    made = []

    def fake_engine_from_url(url, **kw):
        if not proxy_ok:
            raise RuntimeError("ORA-28150: proxy not authorized to connect as client")
        role = url.username.split("[", 1)[1].rstrip("]")
        eng = _FakeEngine(rows, session_user=role, url=url, shared=app)
        made.append(eng)
        return eng

    import schemagate.introspect as intro
    monkeypatch.setattr(intro, "engine_from_url", fake_engine_from_url)
    return rls._OracleProber(app), app, made


def test_ora_identifier_withholds_only_when_the_policy_reacted(monkeypatch):
    """A policy keyed on CLIENT_IDENTIFIER: rows with none set, none with the
    role's identifier. That is a policy demonstrably reacting, and the answer
    is final without a proxy session."""
    rows = lambda ident, user: ident is None or ident != "R2"          # noqa: E731
    prober, app, made = _oracle_prober(monkeypatch, rows)
    assert prober("R2", "HR", "employee_salary") is False
    assert made == [], "no proxy session was needed"
    assert app.identifier is None, "the identifier was cleared on the app connection"
    stmts = [s for _, s, _ in app.log]
    assert any("SET_IDENTIFIER" in s for s in stmts) and any("CLEAR_IDENTIFIER" in s for s in stmts)


def test_ora_identifier_rows_defer_to_the_proxy_whose_answer_is_final(monkeypatch):
    """A policy keyed on SESSION_USER ignores the identifier: rows both ways
    prove nothing. The proxy session *is* the user, and it gets nothing."""
    rows = lambda ident, user: user != "R2"                             # noqa: E731
    prober, app, made = _oracle_prober(monkeypatch, rows)
    assert prober("R2", "HR", "employee_salary") is False
    assert prober("R1", "HR", "employee_salary") is True
    assert [e.session_user for e in made] == ["R2", "R1"], "one proxied engine per role"
    # the same role on a second object reuses its engine
    assert prober("R2", "HR", "employee_bonus") is False
    assert len(made) == 2
    prober.close()
    assert all(e.disposed for e in made)


def test_ora_targets_are_denormalised_and_quoted(monkeypatch):
    rows = lambda ident, user: True                                     # noqa: E731
    prober, app, _ = _oracle_prober(monkeypatch, rows)
    assert prober._target("hr", "employee_salary") == '"HR"."EMPLOYEE_SALARY"'
    assert prober._target(None, "Mixed") == '"Mixed"'


def test_ora_a_user_the_connection_cannot_proxy_for_is_kept_and_the_fix_is_named(monkeypatch):
    from schemagate.rls import CannotSetRole
    rows = lambda ident, user: True                                     # noqa: E731
    prober, app, _ = _oracle_prober(monkeypatch, rows, proxy_ok=False)
    with pytest.raises(CannotSetRole) as ei:
        prober("R2", "HR", "employee_salary")
    msg = str(ei.value)
    assert "ALTER USER R2 GRANT CONNECT THROUGH APP" in msg and "ORA-28150" in msg


def test_ora_baseline_without_rows_skips_the_identifier_and_asks_the_proxy(monkeypatch):
    """The app user itself gets no rows: the identifier probe cannot tell
    anything, so it is not even attempted; the proxy answers."""
    rows = lambda ident, user: user == "R1"                             # noqa: E731
    prober, app, made = _oracle_prober(monkeypatch, rows)
    assert prober("R1", "HR", "employee_salary") is True
    assert not any("SET_IDENTIFIER" in s for _, s, _ in app.log)
    assert [e.session_user for e in made] == ["R1"]


def test_apply_policies_reports_why_a_role_was_not_probed(cat):
    from schemagate.rls import CannotSetRole, apply_policies
    a, _ = _two(cat)
    a.roles = ["R2"]

    def probe(role, schema, name):
        raise CannotSetRole("cannot proxy for R2 (ORA-28150); a DBA can allow it with "
                            "ALTER USER R2 GRANT CONNECT THROUGH APP")

    rep = apply_policies(cat, {_key(a)}, set(), probe=probe)
    assert a.roles == ["R2"]
    assert any("ALTER USER R2 GRANT CONNECT THROUGH APP" in w for w in rep.warnings), rep.warnings
    a.roles = None; a.extra.clear()
