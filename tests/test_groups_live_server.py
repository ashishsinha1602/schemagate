"""Groups defined in a table, on a real database, through the real server.

No demo catalog anywhere in this file. A membership table is created on the
live server, the MCP server is started as a subprocess against that same
database with a ``groups`` block naming the table, and a real MCP client
asks it questions. What is checked is the whole promise: a client that
claims ``payroll`` does not see the payroll table, a user the table says is
in payroll does, and ``run_query`` returns that user real rows.

    SGBENCH_PG_URL=postgresql://postgres:pw@127.0.0.1:5434/sgbench   pytest tests/test_groups_live_server.py
    SCHEMAGATE_MYSQL_URL=mysql+pymysql://root:pw@127.0.0.1:3307/app    pytest tests/test_groups_live_server.py
"""
from __future__ import annotations

import json
import os
import sys

import pytest
from sqlalchemy import create_engine, text

PG_URL = os.environ.get("SCHEMAGATE_PG_URL") or os.environ.get("SGBENCH_PG_URL")
MY_URL = os.environ.get("SCHEMAGATE_MYSQL_URL")

pytest.importorskip("mcp")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _run(engine, statements):
    with engine.connect() as c:
        for s in statements:
            c.execute(text(s))
        c.commit()


def _params(url, config_path):
    from mcp import StdioServerParameters
    env = dict(os.environ)
    env["SCHEMAGATE_DATABASE_URL"] = url
    env["SCHEMAGATE_CATALOG_CONFIG"] = str(config_path)
    env["SCHEMAGATE_AUTO_DESCRIBE"] = "0"
    env["SCHEMAGATE_AUTO_EMBEDDER"] = "0"
    return StdioServerParameters(command=sys.executable,
                                 args=["-m", "schemagate.mcp_server"], env=env)


async def _call(session, tool, args):
    result = await session.call_tool(tool, args)
    return "".join(getattr(c, "text", "") for c in result.content)


def _config(tmp_path, restrict_table, sql):
    cfg = tmp_path / "catalog.json"
    cfg.write_text(json.dumps({
        "restrict": {restrict_table: ["payroll"]},
        "groups": {"sources": [{"type": "sql", "sql": sql, "for": ["okta"]}],
                   "map": {"Payroll Team": "payroll"}, "passthrough": False},
    }), "utf-8")
    return cfg


async def _exercise(url, cfg, table):
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with stdio_client(_params(url, cfg)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            health = json.loads(await _call(session, "health", {}))
            assert health["groups"]["sources"] == ["sql"], health
            assert health["objects"] > 0

            # the client claims payroll; the table says finance. Claim ignored.
            claimed = await _call(session, "select_schema",
                                  {"question": "salary", "top_k": 10,
                                   "principal": "okta:mbrown", "roles": ["payroll"]})
            assert table not in claimed.lower(), claimed

            # anonymous: nothing restricted
            anon = await _call(session, "select_schema", {"question": "salary", "top_k": 10})
            assert table not in anon.lower()

            # the table says jdoe is in Payroll Team -> mapped to payroll
            member = await _call(session, "select_schema",
                                 {"question": "salary", "top_k": 10, "principal": "okta:jdoe"})
            assert table in member.lower(), member

            listed = json.loads(await _call(session, "list_objects", {"principal": "okta:jdoe"}))
            assert any(o["name"].lower().endswith(table) for o in listed["objects"])
            listed = json.loads(await _call(session, "list_objects", {"principal": "okta:mbrown",
                                                                      "roles": ["payroll"]}))
            assert not any(o["name"].lower().endswith(table) for o in listed["objects"])

            # and real rows come back for the member, an error for the claimant
            rows = json.loads(await _call(session, "run_query",
                                          {"sql": f"SELECT salary FROM {table} ORDER BY salary",
                                           "principal": "okta:jdoe"}))
            assert "rows" in rows, rows
            assert [r[0] for r in rows["rows"]] == [1000, 2000] or \
                   [float(r[0]) for r in rows["rows"]] == [1000.0, 2000.0], rows
            denied = json.loads(await _call(session, "run_query",
                                            {"sql": f"SELECT salary FROM {table}",
                                             "principal": "okta:mbrown", "roles": ["payroll"]}))
            assert "error" in denied and "rows" not in denied

            # someone the table has never heard of: no roles, not an error
            unknown = await _call(session, "select_schema",
                                  {"question": "salary", "top_k": 10, "principal": "okta:nobody"})
            assert table not in unknown.lower()


# --- PostgreSQL ------------------------------------------------------------------

PG_SETUP = [
    "DROP TABLE IF EXISTS public.sg_grp_membership",
    "DROP TABLE IF EXISTS public.sg_grp_payroll",
    "CREATE TABLE public.sg_grp_payroll (id int primary key, salary numeric)",
    "INSERT INTO public.sg_grp_payroll VALUES (1, 2000), (2, 1000)",
    "CREATE TABLE public.sg_grp_membership (user_id text, group_name text)",
    ("INSERT INTO public.sg_grp_membership VALUES ('jdoe', 'Payroll Team'), "
     "('jdoe', 'Everyone'), ('mbrown', 'Finance')"),
]
PG_TEARDOWN = ["DROP TABLE IF EXISTS public.sg_grp_membership",
               "DROP TABLE IF EXISTS public.sg_grp_payroll"]


@pytest.fixture
def pg():
    if not PG_URL:
        pytest.skip("set SCHEMAGATE_PG_URL (or SGBENCH_PG_URL)")
    url = PG_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    eng = create_engine(url, isolation_level="AUTOCOMMIT")
    _run(eng, PG_SETUP)
    yield url
    _run(eng, PG_TEARDOWN)
    eng.dispose()


@pytest.mark.anyio
async def test_pg_groups_in_a_table_through_the_real_server(pg, tmp_path):
    cfg = _config(tmp_path, "sg_grp_payroll",
                  "SELECT group_name FROM public.sg_grp_membership WHERE user_id = :subject")
    await _exercise(pg, cfg, "sg_grp_payroll")


# --- MySQL -------------------------------------------------------------------------

MY_SETUP = [
    "CREATE DATABASE IF NOT EXISTS sg_grp",
    "DROP TABLE IF EXISTS sg_grp.membership",
    "DROP TABLE IF EXISTS sg_grp.payroll",
    "CREATE TABLE sg_grp.payroll (id INT PRIMARY KEY, salary DECIMAL(10,2))",
    "INSERT INTO sg_grp.payroll VALUES (1, 2000), (2, 1000)",
    "CREATE TABLE sg_grp.membership (user_id VARCHAR(80), group_name VARCHAR(80))",
    ("INSERT INTO sg_grp.membership VALUES ('jdoe', 'Payroll Team'), "
     "('jdoe', 'Everyone'), ('mbrown', 'Finance')"),
]
MY_TEARDOWN = ["DROP TABLE IF EXISTS sg_grp.membership", "DROP TABLE IF EXISTS sg_grp.payroll",
               "DROP DATABASE IF EXISTS sg_grp"]


@pytest.fixture
def my():
    if not MY_URL:
        pytest.skip("set SCHEMAGATE_MYSQL_URL")
    eng = create_engine(MY_URL, isolation_level="AUTOCOMMIT")
    _run(eng, MY_SETUP)
    # the server must reflect the sg_grp database, so point it there
    url = MY_URL.rsplit("/", 1)[0] + "/sg_grp"
    yield url
    _run(eng, MY_TEARDOWN)
    eng.dispose()


@pytest.mark.anyio
async def test_mysql_groups_in_a_table_through_the_real_server(my, tmp_path):
    cfg = _config(tmp_path, "payroll",
                  "SELECT group_name FROM sg_grp.membership WHERE user_id = :subject")
    await _exercise(my, cfg, "payroll")
