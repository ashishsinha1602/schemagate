"""Row-level policies against a real PostgreSQL: the measurement in
docs/row-level-security.md, turned into what the library now does about it.

    SCHEMAGATE_PG_URL=postgresql://postgres:pw@127.0.0.1:5432/app  pytest tests/test_rls_live.py

The connection must be a superuser (or a member of the fixture roles) for
the probe half; the flagging half needs only the grant.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from schemagate import Catalog, Principal
from schemagate.grants import restrict_from_grants
from schemagate.models import POLICY_NOTE
from schemagate.rls import restrict_from_policies

PG_URL = os.environ.get("SCHEMAGATE_PG_URL") or os.environ.get("SGBENCH_PG_URL")
pytestmark = [pytest.mark.live,
              pytest.mark.skipif(not PG_URL, reason="set SCHEMAGATE_PG_URL to run")]

T, V, VSI = "sgrls_t_salary", "sgrls_t_v_sales", "sgrls_t_v_sales_si"
R1, R2 = "sgrls_t_r1", "sgrls_t_r2"

SETUP = [
    f"DROP VIEW IF EXISTS {V}", f"DROP VIEW IF EXISTS {VSI}", f"DROP TABLE IF EXISTS {T}",
    f"DROP ROLE IF EXISTS {R1}", f"DROP ROLE IF EXISTS {R2}",
    f"CREATE ROLE {R1} NOLOGIN", f"CREATE ROLE {R2} NOLOGIN",
    f"CREATE TABLE {T} (id int primary key, name text, dept text, salary numeric)",
    f"INSERT INTO {T} VALUES (1,'Ann','SALES',91000),(2,'Bob','SALES',87000),"
    f"(3,'Cy','ENG',120000),(4,'Di','HR',70000)",
    f"ALTER TABLE {T} ENABLE ROW LEVEL SECURITY",
    f"CREATE POLICY p_r1 ON {T} FOR SELECT TO {R1} USING (dept = 'SALES')",
    f"CREATE POLICY p_r2 ON {T} FOR SELECT TO {R2} USING (false)",
    f"CREATE VIEW {V} AS SELECT * FROM {T} WHERE dept = 'SALES'",
    f"CREATE VIEW {VSI} WITH (security_invoker = true) AS SELECT * FROM {T} WHERE dept = 'SALES'",
    f"GRANT USAGE ON SCHEMA public TO {R1}, {R2}",
    f"GRANT SELECT ON {T}, {V}, {VSI} TO {R1}, {R2}",
]
TEARDOWN = [
    f"DROP VIEW IF EXISTS {V}", f"DROP VIEW IF EXISTS {VSI}", f"DROP TABLE IF EXISTS {T}",
    f"REVOKE ALL ON SCHEMA public FROM {R1}, {R2}",
    f"DROP ROLE IF EXISTS {R1}", f"DROP ROLE IF EXISTS {R2}",
]


def _run(engine, statements):
    with engine.begin() as c:
        for s in statements:
            c.execute(text(s))


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(PG_URL)
    _run(eng, SETUP)
    try:
        yield eng
    finally:
        _run(eng, TEARDOWN)


@pytest.fixture(scope="module")
def superuser(engine) -> bool:
    with engine.connect() as c:
        return bool(c.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar())


def _sees(cat, role, name):
    who = Principal(f"db:{role}", roles=frozenset({role}))
    got = {getattr(o, "name", o).split(".")[-1]
           for o in cat.select("sales salary by employee", top_k=20, principal=who).objects}
    return name in got


def test_pg_policied_table_is_flagged_and_the_note_reaches_the_prompt(engine):
    cat = Catalog().bootstrap(engine)
    restrict_from_grants(cat, engine)
    rep = restrict_from_policies(cat, engine, probe=False, report=True)
    assert any(q.endswith(T) for q in rep.policied), rep
    doc = next(d for d in cat._docs.values() if d.name == T)
    assert doc.extra["row_policy"] is True
    assert f"-- {POLICY_NOTE}" in doc.render_ddl()
    # the plain predicate view bypasses the policy; the security_invoker one does not
    flagged = {q.split(".")[-1] for q in rep.bypassing_views}
    assert V in flagged and VSI not in flagged, rep


def test_pg_the_role_that_gets_no_rows_loses_the_table(engine, superuser):
    if not superuser:
        pytest.skip("probing needs SET ROLE; the connection is not a superuser")
    cat = Catalog().bootstrap(engine)
    restrict_from_grants(cat, engine)
    assert _sees(cat, R2, T), "before probing the grant reader still shows it"
    rep = restrict_from_policies(cat, engine, report=True)
    assert f"public.{T} <- {R2}" in rep.withheld or f"{T} <- {R2}" in rep.withheld, rep
    assert not rep.unprobed_roles, rep
    doc = next(d for d in cat._docs.values() if d.name == T)
    assert R1 in doc.roles and R2 not in doc.roles
    assert _sees(cat, R1, T) and not _sees(cat, R2, T)


def test_pg_hiding_bypassing_views_withholds_them_from_everyone(engine):
    cat = Catalog().bootstrap(engine)
    restrict_from_grants(cat, engine)
    assert _sees(cat, R1, V)
    restrict_from_policies(cat, engine, probe=False, hide_bypassing_views=True)
    assert not _sees(cat, R1, V) and not _sees(cat, R2, V)
    assert _sees(cat, R1, VSI), "the security_invoker view is not a bypass and stays"
