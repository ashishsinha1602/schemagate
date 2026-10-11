# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Catalogue max age against a real database server: a GRANT and a REVOKE in the database reach the server
within SCHEMAGATE_CATALOG_MAX_AGE, and when the server can no longer read the database it refuses instead of
answering from the old permissions, then recovers.

Run by .github/workflows/mcp-e2e.yml per engine, after tests/mcp_command_e2e.py. Not a pytest module.

  postgres, mysql, oracle: visibility comes from the database's GRANTs (SCHEMAGATE_RESTRICT_FROM_GRANTS=1);
      the change is a real GRANT / REVOKE on hr.pay to the sales role.
  mssql: no grant reader exists for SQL Server, so visibility comes from the config file; the change is
      an edit to that file. The failure and recovery steps are the same on every engine.

The server connects as its own login (sgserver). "The database stops answering" is that login being locked
(ALTER ROLE ... NOLOGIN / ACCOUNT LOCK / DISABLE); recovery is unlocking it.

Environment: SGE_ENGINE, SGE_ADMIN_URL (fixture rights), SGE_SERVER_URL (the sgserver login), SGE_EXTRA.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile

import sqlalchemy as sa

ENGINE = os.environ["SGE_ENGINE"]
ADMIN_URL = os.environ["SGE_ADMIN_URL"]
SERVER_URL = os.environ["SGE_SERVER_URL"]
EXTRA = os.environ["SGE_EXTRA"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_AGE = 3.0
PW = "Sg_CI_throwaway_2026x"          # throwaway; the server lives one CI job on the runner's loopback

# Oracle keeps role names upper case, and a caller must name the role the way the database does.
SALES = "ROLE_SALES" if ENGINE == "oracle" else "role_sales"
PAYROLL = "ROLE_PAYROLL" if ENGINE == "oracle" else "role_payroll"

SPEC = {
    "postgres": dict(grants=True, app="public", setup=[
        "CREATE SCHEMA hr",
        "CREATE TABLE public.customers (id int PRIMARY KEY, name varchar(40))",
        "CREATE TABLE hr.pay (id int PRIMARY KEY, employee varchar(40), amount numeric(12,2))",
        "INSERT INTO public.customers VALUES (1, 'Acme'), (2, 'Globex')",
        "INSERT INTO hr.pay VALUES (1, 'alice', 185000), (2, 'bob', 172000)",
        "CREATE ROLE role_sales", "CREATE ROLE role_payroll",
        f"CREATE ROLE sgserver LOGIN PASSWORD '{PW}'",
        "GRANT USAGE ON SCHEMA hr TO sgserver, role_sales, role_payroll",
        "GRANT SELECT ON public.customers TO role_sales",
        "GRANT SELECT ON hr.pay TO role_payroll",
        "GRANT SELECT ON public.customers, hr.pay TO sgserver",
    ], grant="GRANT SELECT ON hr.pay TO role_sales", revoke="REVOKE SELECT ON hr.pay FROM role_sales",
        lock=["ALTER ROLE sgserver NOLOGIN",
              "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = 'sgserver'"],
        unlock=["ALTER ROLE sgserver LOGIN"]),
    "mysql": dict(grants=True, app="app", setup=[
        "CREATE DATABASE hr",
        "CREATE TABLE app.customers (id int PRIMARY KEY, name varchar(40))",
        "CREATE TABLE hr.pay (id int PRIMARY KEY, employee varchar(40), amount decimal(12,2))",
        "INSERT INTO app.customers VALUES (1, 'Acme'), (2, 'Globex')",
        "INSERT INTO hr.pay VALUES (1, 'alice', 185000), (2, 'bob', 172000)",
        "CREATE ROLE role_sales, role_payroll",
        f"CREATE USER sgserver IDENTIFIED BY '{PW}'",
        "GRANT SELECT ON app.customers TO role_sales",
        "GRANT SELECT ON hr.pay TO role_payroll",
        "GRANT SELECT ON app.customers TO sgserver", "GRANT SELECT ON hr.pay TO sgserver",
        "GRANT SELECT ON mysql.* TO sgserver",             # the grant reader reads mysql.tables_priv / role_edges
    ], grant="GRANT SELECT ON hr.pay TO role_sales", revoke="REVOKE SELECT ON hr.pay FROM role_sales",
        lock=["ALTER USER sgserver ACCOUNT LOCK"], unlock=["ALTER USER sgserver ACCOUNT UNLOCK"]),
    "oracle": dict(grants=True, app="app", setup=[
        f"CREATE USER hr IDENTIFIED BY \"{PW}\"", "GRANT UNLIMITED TABLESPACE TO hr", "GRANT UNLIMITED TABLESPACE TO app",
        "CREATE TABLE app.customers (id number PRIMARY KEY, name varchar2(40))",
        "CREATE TABLE hr.pay (id number PRIMARY KEY, employee varchar2(40), amount number(12,2))",
        "INSERT INTO app.customers VALUES (1, 'Acme')", "INSERT INTO app.customers VALUES (2, 'Globex')",
        "INSERT INTO hr.pay VALUES (1, 'alice', 185000)", "INSERT INTO hr.pay VALUES (2, 'bob', 172000)",
        "CREATE ROLE role_sales", "CREATE ROLE role_payroll",
        f"CREATE USER sgserver IDENTIFIED BY \"{PW}\"", "GRANT CREATE SESSION, SELECT_CATALOG_ROLE TO sgserver",
        "GRANT SELECT ON app.customers TO role_sales", "GRANT SELECT ON hr.pay TO role_payroll",
        "GRANT SELECT ON app.customers TO sgserver", "GRANT SELECT ON hr.pay TO sgserver",
    ], grant="GRANT SELECT ON hr.pay TO role_sales", revoke="REVOKE SELECT ON hr.pay FROM role_sales",
        lock=["ALTER USER sgserver ACCOUNT LOCK"], unlock=["ALTER USER sgserver ACCOUNT UNLOCK"]),
    "mssql": dict(grants=False, app="dbo", setup=[
        "CREATE SCHEMA hr",
        "CREATE TABLE dbo.customers (id int PRIMARY KEY, name varchar(40))",
        "CREATE TABLE hr.pay (id int PRIMARY KEY, employee varchar(40), amount decimal(12,2))",
        "INSERT INTO dbo.customers VALUES (1, 'Acme'), (2, 'Globex')",
        "INSERT INTO hr.pay VALUES (1, 'alice', 185000), (2, 'bob', 172000)",
        f"CREATE LOGIN sgserver WITH PASSWORD = '{PW}', CHECK_POLICY = OFF",
        "CREATE USER sgserver FOR LOGIN sgserver",
        "GRANT SELECT ON dbo.customers TO sgserver", "GRANT SELECT ON hr.pay TO sgserver",
        "GRANT VIEW DEFINITION TO sgserver",
    ], grant=None, revoke=None,
        lock=["ALTER LOGIN sgserver DISABLE"], unlock=["ALTER LOGIN sgserver ENABLE"]),
}[ENGINE]
APP = SPEC["app"]
R: list = []


def rec(name, ok, detail=""):
    ok = bool(ok)
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + f"[{ENGINE}/freshness] " + name + ("" if ok else f"  ({str(detail)[-500:]})"),
          flush=True)


def admin(stmts):
    eng = sa.create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        for s in stmts:
            c.execute(sa.text(s))
    eng.dispose()


def write_config(path, restrict_pay_to):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"restrict": {} if SPEC["grants"] else
                   {"customers": [SALES, "sgserver"], "hr.pay": restrict_pay_to}}, f)


async def drive():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    cfg = os.path.join(tempfile.mkdtemp(), "roles.json")
    write_config(cfg, [PAYROLL])
    env = {k: v for k, v in os.environ.items() if not k.startswith("SCHEMAGATE_")}
    env.update(SCHEMAGATE_DATABASE_URL=SERVER_URL, SCHEMAGATE_CATALOG_CONFIG=cfg, SCHEMAGATE_AUTO_DESCRIBE="0",
               SCHEMAGATE_CATALOG_MAX_AGE=str(MAX_AGE), PYTHONIOENCODING="utf-8")
    if SPEC["grants"]:
        env["SCHEMAGATE_RESTRICT_FROM_GRANTS"] = "1"
    params = StdioServerParameters(command="uvx", args=["--from", f"{ROOT}[mcp,{EXTRA}]", "schemagate-mcp"], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await asyncio.wait_for(s.initialize(), 900)

            async def call(tool, **a):
                res = await s.call_tool(tool, a)
                if getattr(res, "structuredContent", None):
                    return res.structuredContent
                txt = "".join(getattr(c, "text", "") for c in res.content)
                try:
                    return json.loads(txt)
                except ValueError:
                    return {"_text": txt}

            sales = {"principal": "okta:alice", "roles": [SALES]}
            pay_sql = "SELECT employee FROM hr.pay ORDER BY id"

            def sees_pay(lo):
                return "hr.pay" in json.dumps(lo).lower()

            h = await call("health")
            rec("health reports the max age", h.get("catalog_max_age_seconds") == MAX_AGE and h.get("catalog_stale") is False, h)

            lo = await call("list_objects", **sales)
            rec("before: sales sees customers, not hr.pay", "customers" in json.dumps(lo).lower() and not sees_pay(lo), lo)
            out = await call("run_query", sql=pay_sql, **sales)
            rec("before: sales is refused hr.pay", "error" in out and "rows" not in out, out)

            # --- the change: GRANT in the database (or the config file on SQL Server)
            if SPEC["grants"]:
                admin([SPEC["grant"]])
            else:
                write_config(cfg, [PAYROLL, SALES])
            lo = await call("list_objects", **sales)
            rec("inside the window: the old permissions still apply (documented)", not sees_pay(lo), lo)
            await asyncio.sleep(MAX_AGE + 1.5)
            lo = await call("list_objects", **sales)
            rec("past the window: the grant is visible", sees_pay(lo), lo)
            out = await call("run_query", sql=pay_sql, **sales)
            rec("past the window: sales reads real rows of hr.pay",
                [str(x[0]).strip() for x in out.get("rows", [])] == ["alice", "bob"], out)

            # --- REVOKE
            if SPEC["grants"]:
                admin([SPEC["revoke"]])
            else:
                write_config(cfg, [PAYROLL])
            await asyncio.sleep(MAX_AGE + 1.5)
            lo = await call("list_objects", **sales)
            rec("revoke: hidden again past the window", not sees_pay(lo), lo)
            out = await call("run_query", sql=pay_sql, **sales)
            rec("revoke: sales refused again", "error" in out and "rows" not in out, out)

            # --- the database stops answering the server's login
            admin(SPEC["lock"])
            await asyncio.sleep(MAX_AGE + 1.5)
            for tool, args in (("list_objects", {}), ("select_schema", {"question": "customer names"}),
                               ("describe_object", {"name": "customers"}),
                               ("run_query", {"sql": f"SELECT name FROM {APP}.customers"})):
                out = await call(tool, **args, **sales)
                rec(f"login locked: {tool} refuses as stale",
                    "permissions are stale" in str(out.get("error", "")) and "rows" not in out, out)
            h = await call("health")
            rec("login locked: health says stale and why", h.get("catalog_stale") is True and bool(h.get("last_error")), h)
            leaked = json.dumps(await call("list_objects", **sales))
            rec("login locked: the refusal carries no database error text",
                "sgserver" not in leaked and "password" not in leaked.lower(), leaked)

            # --- recovery
            admin(SPEC["unlock"])
            await asyncio.sleep(6.0)                      # past STALE_RETRY_SECONDS
            lo = await call("list_objects", **sales)
            rec("unlocked: the server answers again", "error" not in lo and "customers" in json.dumps(lo).lower(), lo)
            out = await call("run_query", sql=f"SELECT name FROM {APP}.customers ORDER BY id", **sales)
            rec("unlocked: real rows again", [str(x[0]).strip() for x in out.get("rows", [])] == ["Acme", "Globex"], out)
            h = await call("health")
            rec("unlocked: health no longer stale", h.get("catalog_stale") is False, h)


if __name__ == "__main__":
    admin(SPEC["setup"])
    asyncio.run(drive())
    print(f"\n[{ENGINE}/freshness] RESULT {sum(R)}/{len(R)}")
    sys.exit(0 if R and all(R) else 1)
