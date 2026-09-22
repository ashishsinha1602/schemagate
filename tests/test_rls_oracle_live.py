"""Oracle VPD, probed, against a real database: the measurement in
docs/row-level-security.md, as a test.

    SCHEMAGATE_ORACLE_URL=oracle+oracledb://ADMIN:pw@alias_high \\
    SCHEMAGATE_CONNECT_ARGS='{"config_dir": "./wallet", "wallet_location": "./wallet", "wallet_password": "..."}' \\
    pytest tests/test_rls_oracle_live.py

The connecting user must be able to create users, grant, and proxy: ADMIN on
an Autonomous Database is. Everything is named SGVPDT_* and dropped after.
"""
from __future__ import annotations

import os
import secrets

import pytest
from sqlalchemy import text

from schemagate import Catalog, Principal
from schemagate.grants import restrict_from_grants
from schemagate.models import POLICY_NOTE
from schemagate.rls import restrict_from_policies

URL = os.environ.get("SCHEMAGATE_ORACLE_URL")
pytestmark = [pytest.mark.live,
              pytest.mark.skipif(not URL, reason="set SCHEMAGATE_ORACLE_URL to run")]

S, R1, R2 = "SGVPDT", "SGVPDT_R1", "SGVPDT_R2"


def _pw():
    return "Sg_" + secrets.token_urlsafe(18).replace("-", "x").replace("_", "y") + "1#"


def _run(conn, statements, ok=()):
    for s in statements:
        try:
            conn.execute(text(s))
        except Exception as e:                        # noqa: BLE001
            code = getattr(e.orig.args[0], "code", None) if getattr(e, "orig", None) and e.orig.args else None
            if code not in ok:
                raise


@pytest.fixture(scope="module")
def engine():
    from schemagate.introspect import engine_from_url
    eng = engine_from_url(URL)
    app = (eng.url.username or "").upper()
    with eng.begin() as c:
        _run(c, [f"DROP USER {u} CASCADE" for u in (S, R1, R2)], ok=(1918,))
        _run(c, [f'CREATE USER {u} IDENTIFIED BY "{_pw()}"' for u in (S, R1, R2)])
        _run(c, [f"GRANT CREATE SESSION TO {u}" for u in (S, R1, R2)])
        _run(c, [f"ALTER USER {S} QUOTA UNLIMITED ON DATA",
                 f"GRANT CREATE TABLE, CREATE PROCEDURE TO {S}",
                 f"CREATE TABLE {S}.EMPLOYEE_SALARY (id NUMBER PRIMARY KEY, employee VARCHAR2(40), dept VARCHAR2(20), salary NUMBER)",
                 f"INSERT INTO {S}.EMPLOYEE_SALARY VALUES (1,'A','SALES',61000)",
                 f"INSERT INTO {S}.EMPLOYEE_SALARY VALUES (2,'B','SALES',58000)",
                 f"INSERT INTO {S}.EMPLOYEE_SALARY VALUES (3,'C','HR',74000)",
                 f"INSERT INTO {S}.EMPLOYEE_SALARY VALUES (4,'D','HR',69000)",
                 f"GRANT SELECT ON {S}.EMPLOYEE_SALARY TO {R1}",
                 f"GRANT SELECT ON {S}.EMPLOYEE_SALARY TO {R2}",
                 f"""CREATE OR REPLACE FUNCTION {S}.SALARY_PREDICATE (p_schema IN VARCHAR2, p_object IN VARCHAR2)
                     RETURN VARCHAR2 AS v VARCHAR2(128) := SYS_CONTEXT('USERENV','SESSION_USER');
                     BEGIN
                       IF v = '{R1}' THEN RETURN 'dept = ''SALES''';
                       ELSIF v = '{R2}' THEN RETURN '1 = 0';
                       ELSE RETURN NULL; END IF;
                     END;""",
                 f"""BEGIN DBMS_RLS.ADD_POLICY(object_schema => '{S}', object_name => 'EMPLOYEE_SALARY',
                     policy_name => 'SALARY_ROWS', function_schema => '{S}', policy_function => 'SALARY_PREDICATE',
                     statement_types => 'SELECT'); END;""",
                 # what makes probing possible: the app user may act as each reader
                 f"ALTER USER {R1} GRANT CONNECT THROUGH {app}",
                 f"ALTER USER {R2} GRANT CONNECT THROUGH {app}"])
    try:
        yield eng
    finally:
        with eng.begin() as c:
            _run(c, [f"DROP USER {u} CASCADE" for u in (S, R1, R2)], ok=(1918,))
        eng.dispose()


def _catalog(engine):
    cat = Catalog().bootstrap(engine, schemas=[S])
    restrict_from_grants(cat, engine)
    return cat


def _sees(cat, user):
    who = Principal(f"db:{user}", roles=frozenset({user}))
    return any(getattr(o, "name", o).upper().endswith("EMPLOYEE_SALARY")
               for o in cat.select("salary by employee", top_k=10, principal=who).objects)


def test_ora_vpd_table_is_flagged_and_noted(engine):
    cat = _catalog(engine)
    rep = restrict_from_policies(cat, engine, probe=False, report=True)
    assert any(q.upper().endswith("EMPLOYEE_SALARY") for q in rep.policied), rep
    doc = next(d for d in cat._docs.values() if d.name.upper() == "EMPLOYEE_SALARY")
    assert f"-- {POLICY_NOTE}" in doc.render_ddl()


def test_ora_vpd_the_user_whose_policy_admits_nothing_loses_the_table(engine):
    cat = _catalog(engine)
    assert _sees(cat, R1) and _sees(cat, R2), "the grants alone show it to both"
    rep = restrict_from_policies(cat, engine, report=True)
    # the owner is a grantee too (Oracle records no self-grant, so the reader
    # adds it) and nobody granted CONNECT THROUGH for it: kept and reported,
    # which is the rule. The two readers must have been probed for real.
    assert R1 not in rep.unprobed_roles and R2 not in rep.unprobed_roles, rep
    assert any(w.endswith(f"<- {R2}") for w in rep.withheld), rep
    assert _sees(cat, R1) and not _sees(cat, R2)


def test_ora_vpd_a_user_the_connection_cannot_proxy_for_is_kept_and_named(engine):
    app = (engine.url.username or "").upper()
    with engine.begin() as c:
        c.execute(text(f"ALTER USER {R2} REVOKE CONNECT THROUGH {app}"))
    try:
        cat = _catalog(engine)
        rep = restrict_from_policies(cat, engine, report=True)
        assert R2 in rep.unprobed_roles, rep
        assert _sees(cat, R2), "could not check must never read as checked and denied"
        assert any(f"ALTER USER {R2} GRANT CONNECT THROUGH {app}" in w for w in rep.warnings), rep.warnings
    finally:
        with engine.begin() as c:
            c.execute(text(f"ALTER USER {R2} GRANT CONNECT THROUGH {app}"))
