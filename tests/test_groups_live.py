"""NativeRoles against real servers: the database's own role graph resolves
a ``db:<user>`` subject, transitively, and the grants-restricted catalog lets
exactly that user through.

Skipped unless the URL for a server is set, because the direction of a
role graph and the spelling of a grantee are things only a live server can
answer -- and both have been wrong before (see grants.py).

    SGBENCH_PG_URL=postgresql://postgres:pw@127.0.0.1:5434/sgbench   pytest tests/test_groups_live.py
    SCHEMAGATE_MYSQL_URL=mysql+pymysql://root:pw@127.0.0.1:3307/app    pytest tests/test_groups_live.py

Each test creates roles and a table under a ``sg_grp_`` prefix and drops
them all afterwards. Superuser / root is needed to create roles.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from schemagate import Catalog
from schemagate.grants import restrict_from_grants
from schemagate.groups import Groups, NativeRoles, from_config

PG_URL = os.environ.get("SCHEMAGATE_PG_URL") or os.environ.get("SGBENCH_PG_URL")
MY_URL = os.environ.get("SCHEMAGATE_MYSQL_URL")


def _run(engine, statements):
    with engine.connect() as c:
        for s in statements:
            c.execute(text(s))
        c.commit()


def _sees(cat, principal, table):
    picked = cat.select("salary", principal=principal, top_k=5).table_names
    return any(n.lower().endswith(table) for n in picked)


# --- PostgreSQL --------------------------------------------------------------

PG_SETUP = [
    "DROP TABLE IF EXISTS public.sg_grp_payroll",
    "DROP ROLE IF EXISTS sg_grp_jdoe", "DROP ROLE IF EXISTS sg_grp_other",
    "DROP ROLE IF EXISTS sg_grp_analysts", "DROP ROLE IF EXISTS sg_grp_reporting",
    "CREATE ROLE sg_grp_reporting", "CREATE ROLE sg_grp_analysts",
    "CREATE ROLE sg_grp_jdoe LOGIN", "CREATE ROLE sg_grp_other LOGIN",
    "GRANT sg_grp_reporting TO sg_grp_analysts",       # analysts inherit reporting
    "GRANT sg_grp_analysts TO sg_grp_jdoe",            # jdoe inherits analysts
    "CREATE TABLE public.sg_grp_payroll (id int primary key, salary numeric)",
    "REVOKE ALL ON public.sg_grp_payroll FROM PUBLIC",
    "GRANT SELECT ON public.sg_grp_payroll TO sg_grp_reporting",
]
PG_TEARDOWN = [
    "DROP TABLE IF EXISTS public.sg_grp_payroll",
    "DROP ROLE IF EXISTS sg_grp_jdoe", "DROP ROLE IF EXISTS sg_grp_other",
    "DROP ROLE IF EXISTS sg_grp_analysts", "DROP ROLE IF EXISTS sg_grp_reporting",
]


@pytest.fixture(scope="module")
def pg():
    if not PG_URL:
        pytest.skip("set SCHEMAGATE_PG_URL (or SGBENCH_PG_URL)")
    url = PG_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    eng = create_engine(url, isolation_level="AUTOCOMMIT")
    _run(eng, PG_SETUP)
    yield eng
    _run(eng, PG_TEARDOWN)
    eng.dispose()


def test_pg_native_roles_are_transitive_and_case_folded(pg):
    s = NativeRoles(pg)
    assert s.groups("db:sg_grp_jdoe") == {"sg_grp_analysts", "sg_grp_reporting"}
    assert s.groups("db:SG_GRP_JDOE") == {"sg_grp_analysts", "sg_grp_reporting"}
    assert s.groups("db:sg_grp_other") == set()
    assert s.groups("db:sg_grp_nobody") == set()


def test_pg_grants_and_native_roles_agree_with_the_server(pg):
    cat = Catalog().bootstrap(pg, include=["sg_grp_payroll"], schemas=["public"])
    restrict_from_grants(cat, pg)
    g = Groups([NativeRoles(pg)])
    assert _sees(cat, g.principal("db:sg_grp_jdoe"), "sg_grp_payroll")
    assert not _sees(cat, g.principal("db:sg_grp_other"), "sg_grp_payroll")
    assert not _sees(cat, None, "sg_grp_payroll")
    with pg.connect() as c:
        truth = {r: c.execute(text(
            f"SELECT has_table_privilege('{r}', 'public.sg_grp_payroll', 'SELECT')")).scalar()
            for r in ("sg_grp_jdoe", "sg_grp_other")}
    assert truth == {"sg_grp_jdoe": True, "sg_grp_other": False}


def test_pg_from_config_native_uses_the_catalog_url(pg):
    g = from_config({"sources": [{"type": "native"}]}, env={}, default_url=PG_URL)
    assert g.roles_for("db:sg_grp_jdoe") == {"sg_grp_analysts", "sg_grp_reporting"}


# --- MySQL ---------------------------------------------------------------------

MY_SETUP = [
    "CREATE DATABASE IF NOT EXISTS sg_grp",
    "DROP TABLE IF EXISTS sg_grp.payroll",
    "DROP USER IF EXISTS 'sg_grp_jdoe'@'%'", "DROP USER IF EXISTS 'sg_grp_other'@'%'",
    "DROP ROLE IF EXISTS sg_grp_analysts", "DROP ROLE IF EXISTS sg_grp_reporting",
    "CREATE ROLE sg_grp_reporting", "CREATE ROLE sg_grp_analysts",
    "CREATE USER 'sg_grp_jdoe'@'%' IDENTIFIED BY 'Sg_Grp_2026x'",
    "CREATE USER 'sg_grp_other'@'%' IDENTIFIED BY 'Sg_Grp_2026x'",
    "GRANT sg_grp_reporting TO sg_grp_analysts",
    "GRANT sg_grp_analysts TO 'sg_grp_jdoe'@'%'",
    "CREATE TABLE sg_grp.payroll (id INT PRIMARY KEY, salary DECIMAL(10,2))",
    "GRANT SELECT ON sg_grp.payroll TO sg_grp_reporting",
    "FLUSH PRIVILEGES",
]
MY_TEARDOWN = [
    "DROP TABLE IF EXISTS sg_grp.payroll",
    "DROP USER IF EXISTS 'sg_grp_jdoe'@'%'", "DROP USER IF EXISTS 'sg_grp_other'@'%'",
    "DROP ROLE IF EXISTS sg_grp_analysts", "DROP ROLE IF EXISTS sg_grp_reporting",
    "DROP DATABASE IF EXISTS sg_grp",
]


@pytest.fixture(scope="module")
def my():
    if not MY_URL:
        pytest.skip("set SCHEMAGATE_MYSQL_URL")
    eng = create_engine(MY_URL, isolation_level="AUTOCOMMIT")
    _run(eng, MY_SETUP)
    yield eng
    _run(eng, MY_TEARDOWN)
    eng.dispose()


def test_mysql_native_roles_are_transitive_in_every_spelling(my):
    s = NativeRoles(my)
    got = s.groups("db:sg_grp_jdoe")
    # role_edges spells a grantee three ways; the bare role name is among them
    assert {"sg_grp_analysts", "sg_grp_reporting"} <= got, got
    assert s.groups("db:sg_grp_other") == set()
    # role_edges is read by user name, host dropped; a subject spelt with the
    # host is a name the graph does not hold, and strictness never over-grants
    assert s.groups("db:sg_grp_jdoe@%") == set()


def test_mysql_grants_and_native_roles_agree_with_the_server(my):
    cat = Catalog().bootstrap(my, include=["payroll"], schemas=["sg_grp"])
    restrict_from_grants(cat, my)
    g = Groups([NativeRoles(my)])
    assert _sees(cat, g.principal("db:sg_grp_jdoe"), "payroll")
    assert not _sees(cat, g.principal("db:sg_grp_other"), "payroll")
    assert not _sees(cat, None, "payroll")
