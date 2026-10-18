# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""`schemagate-mcp` end to end against a real database server, the way a user starts it.

Run by .github/workflows/mcp-e2e.yml once per engine (postgres, mysql, mssql, oracle). Not a pytest
module: it needs a live server and network, and it installs the package with real `uvx`.

The scenario is the one the 1.3.1 advisory was about: the same table name in two schemas. A visible
`<app>.salary` holds public pay bands; a restricted `hr.salary` holds confidential pay. Through an MCP
client over stdio it checks what each role sees, that real rows come back, that `hr.salary` is refused
however it is written (qualified, quoted the engine's way, upper case, join, subquery), that the bare
ambiguous name is refused and points only to the visible table, that writes are refused, and that the
data is unchanged afterwards. Exit status is non-zero if any check fails.

Environment:
  SGE_ENGINE      postgres | mysql | mssql | oracle
  SGE_ADMIN_URL   SQLAlchemy URL with rights to create the fixture
  SGE_URL         SQLAlchemy URL schemagate connects with
  SGE_EXTRA       the driver extra for uvx, e.g. postgres
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from decimal import Decimal

import sqlalchemy as sa

ENGINE = os.environ["SGE_ENGINE"]
ADMIN_URL = os.environ["SGE_ADMIN_URL"]
URL = os.environ["SGE_URL"]
EXTRA = os.environ["SGE_EXTRA"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# per engine: the visible schema, the quoted form of the hidden table, and the fixture DDL
SPEC = {
    "postgres": dict(app="public", quoted='"hr"."salary"', setup=[
        "CREATE SCHEMA IF NOT EXISTS hr",
        "CREATE TABLE public.customers (id int PRIMARY KEY, name varchar(40), region varchar(20))",
        "CREATE TABLE public.salary (id int PRIMARY KEY, band varchar(10), note varchar(40))",
        "CREATE TABLE hr.salary (id int PRIMARY KEY, employee varchar(40), annual_amount numeric(12,2))",
    ]),
    "mysql": dict(app="app", quoted="`hr`.`salary`", setup=[
        "CREATE DATABASE IF NOT EXISTS hr",
        "CREATE TABLE app.customers (id int PRIMARY KEY, name varchar(40), region varchar(20))",
        "CREATE TABLE app.salary (id int PRIMARY KEY, band varchar(10), note varchar(40))",
        "CREATE TABLE hr.salary (id int PRIMARY KEY, employee varchar(40), annual_amount decimal(12,2))",
    ]),
    "mssql": dict(app="dbo", quoted="[hr].[salary]", setup=[
        "CREATE SCHEMA hr",
        "CREATE TABLE dbo.customers (id int PRIMARY KEY, name varchar(40), region varchar(20))",
        "CREATE TABLE dbo.salary (id int PRIMARY KEY, band varchar(10), note varchar(40))",
        "CREATE TABLE hr.salary (id int PRIMARY KEY, employee varchar(40), annual_amount decimal(12,2))",
    ]),
    "oracle": dict(app="app", quoted='"HR"."SALARY"', setup=[
        # APP comes from the container (APP_USER); HR is made here. Throwaway, one CI job long.
        "CREATE USER hr IDENTIFIED BY \"Sg_CI_throwaway_2026\"",
        "GRANT UNLIMITED TABLESPACE TO hr",
        "GRANT UNLIMITED TABLESPACE TO app",
        "CREATE TABLE app.customers (id number PRIMARY KEY, name varchar2(40), region varchar2(20))",
        "CREATE TABLE app.salary (id number PRIMARY KEY, band varchar2(10), note varchar2(40))",
        "CREATE TABLE hr.salary (id number PRIMARY KEY, employee varchar2(40), annual_amount number(12,2))",
        "GRANT SELECT ON hr.salary TO app",
    ]),
}[ENGINE]
APP = SPEC["app"]
ROWS = [
    f"INSERT INTO {APP}.customers VALUES (1, 'Acme', 'west')",
    f"INSERT INTO {APP}.customers VALUES (2, 'Globex', 'east')",
    f"INSERT INTO {APP}.salary VALUES (1, 'B1', 'entry band')",
    f"INSERT INTO {APP}.salary VALUES (2, 'B2', 'senior band')",
    "INSERT INTO hr.salary VALUES (1, 'alice', 185000)",
    "INSERT INTO hr.salary VALUES (2, 'bob', 172000)",
]
R: list = []


def rec(name: str, ok: bool, detail="") -> None:
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + f"[{ENGINE}] " + name + ("" if ok else f"  ({str(detail)[-400:]})"), flush=True)


def setup() -> None:
    eng = sa.create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        for stmt in SPEC["setup"] + ROWS:
            c.execute(sa.text(stmt))
    eng.dispose()


def counts() -> dict:
    eng = sa.create_engine(ADMIN_URL)
    with eng.connect() as c:
        out = {t: c.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar()
               for t in (f"{APP}.customers", f"{APP}.salary", "hr.salary")}
    eng.dispose()
    return out


def _val(v):
    """Exact decimals come back as strings ('185000.00'); compare numbers as numbers."""
    if isinstance(v, (int, float, Decimal)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return v.strip()
    return v


def norm(rows) -> list:
    return [[_val(v) for v in r] for r in rows or []]


SEEN: list = []        # every prompt the stand-in model received


def fake_model() -> str:
    """An OpenAI-compatible endpoint on loopback that answers `semantic_query` deterministically.

    Filter: keeps the texts containing the criterion. Extract: answers each text upper-cased. Every
    prompt is kept in SEEN, so the run can show restricted rows never reached a model.
    """
    import re
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            system, prompt = (m["content"] for m in body["messages"])
            SEEN.append(prompt)
            items = re.findall(r'^(\d+)\. "(.*)"$', prompt, re.M)
            if prompt.startswith("Criterion: "):
                want = prompt.split("\n", 1)[0][len("Criterion: "):].strip().lower()
                reply = ", ".join(n for n, t in items if want in t.lower()) or "NONE"
            else:
                reply = "\n".join(f"{n}: {t.upper()}" for n, t in items)
            out = json.dumps({"id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
                              "choices": [{"index": 0, "finish_reason": "stop",
                                           "message": {"role": "assistant", "content": reply}}],
                              "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}/v1"


async def drive() -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    cfg = os.path.join(tempfile.mkdtemp(), "roles.json")
    with open(cfg, "w", encoding="utf-8") as f:
        json.dump({"restrict": {"hr.salary": ["payroll"]}}, f)
    env = {k: v for k, v in os.environ.items() if not k.startswith("SCHEMAGATE_")}
    env.update(SCHEMAGATE_DATABASE_URL=URL, SCHEMAGATE_AUTO_DESCRIBE="0", PYTHONIOENCODING="utf-8",
               # semantic_query on, against the loopback stand-in model (not a credential)
               SCHEMAGATE_MCP_SEMANTIC="1", SCHEMAGATE_MCP_PROVIDER="openai", SCHEMAGATE_MCP_MODEL="ci-stand-in",
               OPENAI_API_KEY="ci-stand-in", OPENAI_BASE_URL=fake_model())
    params = StdioServerParameters(command="uvx", args=["--from", f"{ROOT}[mcp,openai,{EXTRA}]", "schemagate-mcp",
                                                        "--config", cfg], env=env)
    before = counts()
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await asyncio.wait_for(s.initialize(), 900)
            info = getattr(init, "server_info", None) or getattr(init, "serverInfo", None)
            rec(f"uvx schemagate-mcp starts and initializes (server {info.version})", bool(info.version))

            async def call(tool, **a):
                res = await s.call_tool(tool, a)
                if getattr(res, "structuredContent", None):
                    return res.structuredContent
                txt = "".join(getattr(c, "text", "") for c in res.content)
                try:
                    return json.loads(txt)
                except ValueError:
                    return {"_text": txt}

            sales = {"principal": "okta:alice", "roles": ["sales"]}
            pay = {"principal": "okta:bob", "roles": ["payroll"]}
            lo = json.dumps(await call("list_objects", **sales)).lower()
            rec("sales: list_objects shows the visible salary and customers, not hr.salary",
                "customers" in lo and f"{APP}.salary" in lo and "hr.salary" not in lo, lo[:400])
            lo = json.dumps(await call("list_objects", **pay)).lower()
            rec("payroll: list_objects includes hr.salary", "hr.salary" in lo, lo[:400])
            sel = json.dumps(await call("select_schema", question="annual pay per employee", **sales)).lower()
            rec("sales: select_schema never shows hr.salary or annual_amount",
                "hr.salary" not in sel and "annual_amount" not in sel, sel[:400])

            out = await call("run_query", sql=f"SELECT name, region FROM {APP}.customers ORDER BY id", **sales)
            rec("sales: real rows from customers", norm(out.get("rows")) == [["Acme", "west"], ["Globex", "east"]], out)
            out = await call("run_query", sql=f"SELECT band FROM {APP}.salary ORDER BY id", **sales)
            rec(f"sales: the visible twin {APP}.salary returns its rows", norm(out.get("rows")) == [["B1"], ["B2"]], out)
            for label, sql in (("qualified", "SELECT * FROM hr.salary"),
                               ("quoted", f"SELECT * FROM {SPEC['quoted']}"),
                               ("upper case", "SELECT * FROM HR.SALARY"),
                               ("join", f"SELECT c.name FROM {APP}.customers c JOIN hr.salary s ON s.id = c.id"),
                               ("subquery", f"SELECT name FROM {APP}.customers WHERE id IN (SELECT id FROM hr.salary)")):
                out = await call("run_query", sql=sql, **sales)
                rec(f"sales: hr.salary refused ({label})", "error" in out and "rows" not in out, out)
            out = await call("run_query", sql="SELECT * FROM salary", **sales)
            msg = str(out.get("error", "")).lower()
            rec(f"sales: bare 'salary' refused, pointed to {APP}.salary, hr not named",
                "rows" not in out and f"{APP}.salary" in msg and "hr." not in msg, out)
            out = await call("run_query", sql="SELECT employee, annual_amount FROM hr.salary ORDER BY id", **pay)
            rec("payroll: real rows from hr.salary",
                norm(out.get("rows")) == [["alice", 185000.0], ["bob", 172000.0]], out)
            for sql in (f"DELETE FROM {APP}.customers", f"UPDATE {APP}.salary SET band = 'X'",
                        f"DROP TABLE {APP}.customers", f"SELECT 1 FROM {APP}.customers; DELETE FROM {APP}.customers"):
                out = await call("run_query", sql=sql, **pay)
                rec(f"write refused: {sql[:40]}", "error" in out and "rows" not in out, out)

            # semantic_query: the same scope check first, then the model reads only what came back
            out = await call("semantic_query", sql=f"SELECT band, note FROM {APP}.salary ORDER BY id",
                             column="note", criterion="senior", **sales)
            rec("sales: semantic_query filter keeps the matching row",
                norm(out.get("rows")) == [["B2", "senior band"]] and out.get("judged") == 2, out)
            out = await call("semantic_query", sql=f"SELECT name, region FROM {APP}.customers ORDER BY id",
                             column="region", extract="the region", **sales)
            rec("sales: semantic_query extract adds one answer per row",
                norm(out.get("rows")) == [["Acme", "west", "WEST"], ["Globex", "east", "EAST"]], out)
            n = len(SEEN)
            for label, sql in (("qualified", "SELECT employee, annual_amount FROM hr.salary"),
                               ("join", f"SELECT s.employee FROM {APP}.customers c JOIN hr.salary s ON s.id = c.id")):
                out = await call("semantic_query", sql=sql, column="employee", criterion="alice", **sales)
                rec(f"sales: semantic_query on hr.salary refused ({label})", "error" in out and "rows" not in out, out)
            rec("sales: no prompt was sent for the refused queries", len(SEEN) == n, SEEN[n:])
            out = await call("semantic_query", sql="SELECT employee FROM hr.salary ORDER BY id",
                             column="employee", criterion="alice", **pay)
            rec("payroll: semantic_query on hr.salary works", norm(out.get("rows")) == [["alice"]], out)
            sent = "\n".join(SEEN[:n]).lower()
            rec("the model never saw hr.salary rows on a sales call", "alice" not in sent and "185000" not in sent, sent)
            health = await call("health")
            rec("health reports semantic on", health.get("semantic") is True, health)
    rec("data unchanged after every refused write", counts() == before, (before, counts()))


if __name__ == "__main__":
    setup()
    asyncio.run(drive())
    print(f"\n[{ENGINE}] RESULT {sum(R)}/{len(R)}")
    sys.exit(0 if R and all(R) else 1)
