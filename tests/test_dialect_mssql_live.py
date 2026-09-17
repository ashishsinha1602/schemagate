"""The SQL Server dialect hooks, against a real server.

Skipped unless SCHEMAGATE_MSSQL_URL points at one. The unit tests in
`test_dialects.py` pin the classification -- that `dbo` is the user's schema
and the nine fixed-role schemas are not -- because getting that backwards
empties a catalog. What they cannot tell you is whether the two catalog
queries are shaped the way `sys.schemas`, `sys.columns` and `sys.types`
actually are on a running instance, and that is the only thing this module is
here for.

    docker run -d --name sgmssql -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD=... \
        -p 1433:1433 mcr.microsoft.com/mssql/server:2022-latest
    SCHEMAGATE_MSSQL_URL='mssql+pyodbc://sa:...@127.0.0.1:1433/master?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes' \
        pytest tests/test_dialect_mssql_live.py

CI runs exactly that against a service container, so the claim in the README
has a run behind it rather than a reading of the documentation.
"""
from __future__ import annotations

import os

import pytest

URL = os.environ.get("SCHEMAGATE_MSSQL_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set SCHEMAGATE_MSSQL_URL")

sa = pytest.importorskip("sqlalchemy")

SCHEMA = "sg_live"

#: An alias type is the case that cannot be detected from the reflected value
#: alone: `AccountNumber` arrives as NVARCHAR(20), which is not wrong, just
#: less than the schema says. `hierarchyid` and `sql_variant` are the other
#: half -- types SQLAlchemy has no class for, which reflect as NULL.
DDL = [
    f"IF SCHEMA_ID('{SCHEMA}') IS NULL EXEC('CREATE SCHEMA {SCHEMA}')",
    "IF TYPE_ID('dbo.AccountNumber') IS NULL "
    "CREATE TYPE dbo.AccountNumber FROM nvarchar(20)",
    f"""IF OBJECT_ID('{SCHEMA}.accounts') IS NULL
        CREATE TABLE {SCHEMA}.accounts (
            id INT PRIMARY KEY,
            account_no dbo.AccountNumber,
            label NVARCHAR(40),
            wide VARCHAR(MAX),
            amount DECIMAL(12,3),
            node hierarchyid,
            anything sql_variant
        )""",
    f"""IF OBJECT_ID('{SCHEMA}.customers') IS NULL
        CREATE TABLE {SCHEMA}.customers (
            id INT PRIMARY KEY,
            name NVARCHAR(80),
            account_id INT REFERENCES {SCHEMA}.accounts(id)
        )""",
    f"""IF OBJECT_ID('{SCHEMA}.v_accounts') IS NULL
        EXEC('CREATE VIEW {SCHEMA}.v_accounts AS
              SELECT id, account_no FROM {SCHEMA}.accounts')""",
]

TEARDOWN = [
    f"IF OBJECT_ID('{SCHEMA}.v_accounts') IS NOT NULL DROP VIEW {SCHEMA}.v_accounts",
    f"IF OBJECT_ID('{SCHEMA}.customers') IS NOT NULL DROP TABLE {SCHEMA}.customers",
    f"IF OBJECT_ID('{SCHEMA}.accounts') IS NOT NULL DROP TABLE {SCHEMA}.accounts",
    "IF TYPE_ID('dbo.AccountNumber') IS NOT NULL DROP TYPE dbo.AccountNumber",
    f"IF SCHEMA_ID('{SCHEMA}') IS NOT NULL DROP SCHEMA {SCHEMA}",
]


@pytest.fixture(scope="module")
def engine():
    eng = sa.create_engine(URL)
    with eng.begin() as conn:
        for stmt in DDL:
            conn.exec_driver_sql(stmt)
    yield eng
    with eng.begin() as conn:
        for stmt in TEARDOWN:
            try:
                conn.exec_driver_sql(stmt)
            except Exception:                                    # noqa: BLE001
                pass
    eng.dispose()


@pytest.fixture(scope="module")
def types(engine):
    from schemagate.dialects.mssql import _catalog_types
    return _catalog_types(engine)


def test_the_connection_is_actually_sql_server(engine):
    """Guards the rest of the module: every assertion below is only evidence
    if it ran against SQL Server and not, say, a SQLite URL left in the
    environment."""
    assert engine.dialect.name == "mssql"
    with engine.connect() as conn:
        banner = conn.exec_driver_sql("SELECT @@VERSION").scalar()
    assert "SQL Server" in banner


# --------------------------------------------------------------- schemas

def test_maintained_schemas_are_what_the_server_owns(engine):
    """The principal_id range 16384..16393 is how the nine fixed-role schemas
    are found without matching nine English names. If that range is wrong the
    query returns them anyway on an English server and silently stops working
    on a localised one, so this checks the range did the work."""
    from schemagate.dialects.mssql import maintained_schemas
    found = {s.lower() for s in maintained_schemas(engine)}
    assert "sys" in found
    assert "information_schema" in found
    for role_schema in ("db_owner", "db_datareader", "db_denydatawriter"):
        assert role_schema in found, f"{role_schema} not reported as maintained"


def test_dbo_is_never_maintained(engine):
    """The one that empties the catalog if it goes wrong. Most SQL Server
    databases keep everything in `dbo`."""
    from schemagate.dialects.mssql import maintained_schemas
    assert "dbo" not in {s.lower() for s in maintained_schemas(engine)}


def test_the_users_schema_survives(engine):
    from schemagate.dialects.mssql import maintained_schemas
    assert SCHEMA not in {s.lower() for s in maintained_schemas(engine)}


# ----------------------------------------------------------------- types

def test_the_catalog_query_runs_and_finds_our_columns(types):
    """`_TYPES_SQL` joining sys.columns to sys.objects, sys.schemas and twice
    to sys.types is the part that was written from documentation. Either the
    joins are right and our seven columns come back, or they are not."""
    assert (SCHEMA, "accounts", "account_no") in types
    assert (SCHEMA, "accounts", "node") in types


def test_views_are_included_not_just_tables(types):
    """`o.type IN ('U', 'V')` -- a view's columns are as worth describing as
    a table's, and schemagate indexes both."""
    assert (SCHEMA, "v_accounts", "account_no") in types


def test_an_alias_type_keeps_its_name_and_says_what_it_is(types):
    """The case reflection cannot report: SQLAlchemy resolves
    `dbo.AccountNumber` to its base and hands back NVARCHAR(20), which is true
    and is not what the schema calls it."""
    rendered = types[(SCHEMA, "accounts", "account_no")]
    assert "AccountNumber" in rendered
    assert "nvarchar(20)" in rendered.lower(), rendered


def test_max_length_is_halved_for_the_n_prefixed_types(types):
    """`sys.columns.max_length` is bytes. NVARCHAR(40) stores two bytes per
    character and reports 80, so a renderer that trusts the column reports a
    column twice the width the user declared."""
    assert types[(SCHEMA, "accounts", "label")].lower() == "nvarchar(40)"


def test_minus_one_is_MAX_not_a_negative_width(types):
    assert types[(SCHEMA, "accounts", "wide")].lower() == "varchar(max)"


def test_decimal_keeps_precision_and_scale(types):
    assert types[(SCHEMA, "accounts", "amount")].lower() == "decimal(12,3)"


def test_the_types_sqlalchemy_has_no_class_for_get_a_name(types):
    """`hierarchyid` and `sql_variant` reflect as NULL. A column whose type
    reads NULL in the prompt tells the model nothing."""
    assert types[(SCHEMA, "accounts", "node")].lower() == "hierarchyid"
    assert types[(SCHEMA, "accounts", "anything")].lower() == "sql_variant"


# ------------------------------------------------- the hook, end to end

def test_reflection_leaves_no_column_typed_NULL(engine):
    """What all of the above is for. Run the hook the way reflection runs it
    and check the two unknown types were filled in place."""
    from schemagate.dialects.mssql import unknown_types
    insp = sa.inspect(engine)
    cols = insp.get_columns("accounts", schema=SCHEMA)
    unknown_types(engine, SCHEMA, "accounts", cols)
    rendered = {c["name"]: str(c["type"]) for c in cols}
    for name, text in rendered.items():
        assert text.upper() not in ("NULL", "NULLTYPE"), \
            f"{name} still has no type after the hook ran"
    assert "hierarchyid" in rendered["node"].lower()
    assert "AccountNumber" in rendered["account_no"]


def test_bootstrap_indexes_the_schema_and_selects_from_it(engine):
    """The whole path: reflect, catalog, select. If the dialect hooks raise
    on a real server this is where it shows, because `bootstrap` is what
    every user calls."""
    from schemagate import Catalog
    cat = Catalog()
    cat.bootstrap(engine, schemas=[SCHEMA])
    names = {d.name.lower() for d in cat._docs.values()}
    assert "accounts" in names
    assert "customers" in names
    assert "v_accounts" in names, "the view did not survive reflection"
    sel = cat.select("which customers are linked to which accounts", top_k=3)
    assert {d.name.lower() for d in sel.objects} & {"customers", "accounts"}
