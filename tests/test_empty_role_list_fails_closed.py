# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""No automatic path may leave an object or column with an empty role list.

`models.allowed` reads an empty role list as "no restriction", so writing one
turns a restricted object public, anonymous callers included. Three places
could write one:

- the row-policy probe, when every granted role reads zero rows (an empty
  policied table, RLS enabled with no policy yet, a policy that admits only an
  ungranted principal);
- the grant reader, given an object whose grantee set is empty;
- `restrict` / `restrict_column` called with no roles, from code or a config.

And `run_query`'s column check compared names across all referenced tables,
so a column withheld on one table passed when another referenced table had a
visible column of the same name.
"""
from types import SimpleNamespace as NS

import pytest

from schemagate import Catalog, Principal
from schemagate import config as sg_config
from schemagate import grants as sg_grants
from schemagate.mcp_server import _check_scope
from schemagate.models import allowed
from schemagate.rls import apply_policies

ANON = None
HOLDER = Principal("okta:r", roles=frozenset({"r1", "r2"}))
OTHER = Principal("okta:o", roles=frozenset({"sales"}))


@pytest.fixture
def fresh(db_url):
    return Catalog().bootstrap(db_url)


def _first(cat):
    return sorted(cat._docs.items(), key=lambda kv: kv[1].name)[0]


def _seen(cat, doc, who):
    return any(o is doc for o in cat.objects() if cat._visible(o, who))


# --- the probe ------------------------------------------------------------------------------------

def test_every_granted_role_withheld_removes_the_object_rather_than_making_it_public(fresh):
    key, doc = _first(fresh)
    doc.roles = ["r1", "r2"]
    rep = apply_policies(fresh, {(doc.schema, doc.name)}, set(), probe=lambda role, s, n: False)
    assert key not in fresh._docs
    assert doc.qname in rep.removed
    assert any("withheld from everyone" in w for w in rep.warnings)
    for who in (ANON, HOLDER, OTHER):
        assert not _seen(fresh, doc, who)
        names = {getattr(o, "name", o) for o in fresh.select(doc.name, top_k=50, principal=who).objects}
        assert doc.name not in names


def test_one_role_still_reading_rows_keeps_the_object_for_that_role_only(fresh):
    key, doc = _first(fresh)
    doc.roles = ["r1", "r2"]
    rep = apply_policies(fresh, {(doc.schema, doc.name)}, set(), probe=lambda role, s, n: role == "r2")
    assert fresh._docs[key].roles == ["r2"] and not rep.removed
    assert not _seen(fresh, doc, ANON) and not _seen(fresh, doc, OTHER)
    assert _seen(fresh, doc, Principal("okta:x", roles=frozenset({"r2"})))


def test_no_probe_leaves_roles_alone(fresh):
    key, doc = _first(fresh)
    doc.roles = ["r1"]
    apply_policies(fresh, {(doc.schema, doc.name)}, set())
    assert fresh._docs[key].roles == ["r1"]


def test_nothing_reachable_ends_with_an_empty_role_list(fresh):
    for _, d in list(fresh._docs.items())[:3]:
        d.roles = ["r1"]
    apply_policies(fresh, {(d.schema, d.name) for d in fresh._docs.values()}, set(),
                   probe=lambda *a: False)
    assert all(d.roles != [] for d in fresh._docs.values())


# --- the grant reader ----------------------------------------------------------------------------

def test_an_empty_grantee_set_withholds_the_object(fresh, monkeypatch):
    key, doc = _first(fresh)
    monkeypatch.setattr(sg_grants, "grantees_by_object", lambda engine: {(doc.schema, doc.name): set()})
    eng = NS(dialect=NS(name="postgresql"))
    rep = sg_grants.restrict_from_grants(fresh, eng, expand_roles=False, report=True)
    assert key not in fresh._docs
    assert any("withheld from everyone" in w for w in rep.warnings)
    assert not _seen(fresh, doc, ANON)


# --- restrict / restrict_column / config ---------------------------------------------------------

def test_restrict_with_no_roles_is_refused(fresh):
    _, doc = _first(fresh)
    with pytest.raises(ValueError, match="at least one role"):
        fresh.restrict(doc.name, [])
    assert doc.roles is None


def test_restrict_column_with_no_roles_is_refused(fresh):
    _, doc = _first(fresh)
    with pytest.raises(ValueError, match="at least one role"):
        fresh.restrict_column(doc.name, doc.columns[0].name, [])


def test_a_config_with_an_empty_role_list_fails_to_load(fresh):
    _, doc = _first(fresh)
    with pytest.raises(ValueError):
        sg_config.apply(fresh, {"restrict": {doc.name: []}})
    with pytest.raises(ValueError):
        sg_config.apply(fresh, {"restrict_column": {doc.name: {doc.columns[0].name: []}}})


# --- run_query: a withheld column shadowed by a visible one of the same name ---------------------

def _doc(name, cols):
    cs = [NS(name=c, roles=r) for c, r in cols]
    return NS(schema="public", name=name, qname=f"public.{name}", roles=None, columns=cs,
              visible_columns=lambda who, cs=cs: [c for c in cs if allowed(c.roles, who)])


class _Cat:
    def __init__(self, docs):
        self._d = docs

    def objects(self):
        return self._d

    def _visible(self, doc, who):
        return allowed(doc.roles, who)


SHADOW = _Cat([_doc("staff", [("id", None), ("salary", ["payroll"])]),
               _doc("offers", [("id", None), ("salary", None)])])


@pytest.mark.parametrize("sql", [
    "SELECT staff.salary FROM staff CROSS JOIN offers",
    "SELECT s.salary FROM staff s JOIN offers o ON o.id = s.id",
    "SELECT salary FROM staff, offers",
    "SELECT * FROM staff CROSS JOIN offers",
    "SELECT s.* FROM staff s, offers o",
])
def test_a_withheld_column_is_refused_even_when_another_table_shows_that_name(sql):
    assert _check_scope(SHADOW, sql, OTHER) is not None


@pytest.mark.parametrize("sql", [
    "SELECT salary FROM offers",
    "SELECT id FROM staff",
    "SELECT staff.id, offers.salary FROM staff JOIN offers ON offers.id = staff.id",
])
def test_what_is_visible_still_runs(sql):
    # the last one names `salary` while `staff` withholds it: refused, fail closed
    got = _check_scope(SHADOW, sql, OTHER)
    if "staff" in sql and "salary" in sql:
        assert got is not None
    else:
        assert got is None


def test_the_payroll_holder_can_read_it():
    who = Principal("okta:p", roles=frozenset({"payroll"}))
    assert _check_scope(SHADOW, "SELECT staff.salary FROM staff CROSS JOIN offers", who) is None
