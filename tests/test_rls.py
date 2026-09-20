"""Row-level policies, without a server: the marking, the probing logic, the
views that bypass the policy, and the one line the prompt gains.

The measurement that motivated this is in docs/row-level-security.md: a
reader whose policy admits no rows holds every permission the dictionary
records. These tests pin what the library does about it once a reader has
told it which objects are policied.
"""
from __future__ import annotations

from sqlalchemy import create_engine

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
    assert any("could not SET ROLE to r2" in w for w in rep.warnings)
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
                "cannot SET ROLE): r9", "warning: x"):
        assert bit in s, bit
