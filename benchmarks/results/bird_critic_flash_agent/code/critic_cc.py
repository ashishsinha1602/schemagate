"""BIRD-CRITIC 1.0 (Flash, PostgreSQL) with a Claude Code agent (`claude -p`, the user's Max plan) per task.

The agent sees the official baseline prompt's content (schema with sample rows, the user's issue, the problematic
SQL) and one tool, critic_sql.py, which runs SQL on the task's own database copy (preprocess_sql applied, every
call rolled back). It ends with its corrected SQL in ```sql blocks; the official baseline extractor
(baseline/src/util.py: sql_response_extract) turns the reply into pred_sqls. sol_sql and test_cases are never
shown to the agent.

Output: predictions.jsonl (the task record + pred_sqls + prompt_flow, the submission format).

    python critic_cc.py --out C:\\birdcritic\\out_flash --workers 8
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "repo" / "baseline" / "src"))
from util import sql_response_extract  # noqa: E402

TASKS = HERE / "flash.jsonl"
SCHEMAS = HERE / "repo" / "baseline" / "data" / "flash_schema.jsonl"
TOOL = "/c/Python313/python.exe C:/birdcritic/critic_sql.py"
DSN = "host=127.0.0.1 port=5544 user=root"

SYSTEM = """You are a PostgreSQL 14 expert. A user reports an issue with their SQL; you diagnose it and write the corrected SQL that does exactly what the user wants.

Your only tool is Bash, and the only command you may run is the SQL tool, always in this form:

{tool} {iid} <<'SQL'
<one or more SQL statements>
SQL

It runs on the user's own database (in its current state) inside a transaction that is rolled back afterwards, so you can test any statement, including UPDATE/INSERT/DELETE/CREATE/ALTER, and check its effect within the same call.

How to work:
1. Read the issue carefully: what result or behaviour does the user actually want?
2. Run the problematic SQL and inspect the relevant tables and values to see what goes wrong.
3. Write the corrected SQL and test it. Check the output matches what the user asked for (columns, rows, order, types).
4. Keep the user's intent and style: change what is wrong; do not add unrequested columns, filters or ordering.
5. If the task needs several statements (e.g. create a function, then call it), give them in order.
Use at most 20 tool calls.

Final answer: put each SQL statement of the solution in its own ```sql block, in execution order, and nothing else in ```sql blocks. Do not include exploratory queries in ```sql blocks in your final answer."""


def _claude():
    exts = sorted(Path.home().glob(".vscode/extensions/anthropic.claude-code-*-win32-x64/resources/native-binary/claude.exe"),
                  key=lambda p: p.stat().st_mtime)
    return str(exts[-1])


def make_db(t):
    db = f"crit_{t['instance_id']}"
    with psycopg.connect(f"{DSN} dbname=postgres", autocommit=True) as con:
        con.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db}'")
        con.execute(f'DROP DATABASE IF EXISTS "{db}"')
        con.execute(f'CREATE DATABASE "{db}" TEMPLATE "{t["db_id"]}_template"')
    pre = t.get("preprocess_sql") or []
    if pre:
        with psycopg.connect(f"{DSN} dbname={db}", autocommit=True) as con:
            for s in pre:
                try:
                    con.execute(s)
                except psycopg.Error as e:
                    print(f"  preprocess error {t['instance_id']}: {str(e)[:120]}", flush=True)


def drop_db(t):
    db = f"crit_{t['instance_id']}"
    with psycopg.connect(f"{DSN} dbname=postgres", autocommit=True) as con:
        con.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db}'")
        con.execute(f'DROP DATABASE IF EXISTS "{db}"')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-turns", type=int, default=30)
    ap.add_argument("--effort", default="high")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--tasks", default=str(TASKS))
    ap.add_argument("--schemas", default=str(SCHEMAS))
    a = ap.parse_args()

    tasks = [json.loads(l) for l in open(a.tasks, encoding="utf-8")]
    schema = {str(json.loads(l)["instance_id"]): json.loads(l)["preprocess_schema"] for l in open(a.schemas, encoding="utf-8")}
    missing = [str(t["instance_id"]) for t in tasks if str(t["instance_id"]) not in schema]
    if missing:
        sys.exit(f"no schema for {len(missing)} tasks, e.g. {missing[:5]}")
    if a.only:
        want = set(a.only.split(","))
        tasks = [t for t in tasks if str(t["instance_id"]) in want]
    if a.limit:
        tasks = tasks[:a.limit]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cwd = out / "_cwd"
    cwd.mkdir(exist_ok=True)
    pred_path = out / "predictions.jsonl"
    done = {str(json.loads(l)["instance_id"]) for l in open(pred_path, encoding="utf-8")} if pred_path.exists() else set()
    lock = threading.Lock()
    fh = open(pred_path, "a", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    claude = _claude()
    stop = {"why": None}
    n = {"done": 0}

    def solve(t):
        iid = str(t["instance_id"])
        if iid in done or stop["why"]:
            return
        make_db(t)
        issue = "".join(f"```sql\n{s}\n```\n" for s in t["issue_sql"])
        prompt = (f"# Database Schema:\n{schema[iid]}\n\n# User issue:\n{t['query']}\n\n# Problematic SQL:\n{issue}\n"
                  "Diagnose the issue with the tool, then give the corrected SQL.")
        system = SYSTEM.replace("{tool}", TOOL).replace("{iid}", iid)
        cmd = [claude, "-p", "--model", a.model, "--effort", a.effort, "--output-format", "json",
               "--max-turns", str(a.max_turns), "--tools", "Bash", "--allowedTools", f"Bash({TOOL} {iid}:*)",
               "--system-prompt", system, "--setting-sources", "", "--no-session-persistence"]
        t0 = time.time()
        try:
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", cwd=cwd,
                               env=env, timeout=2400)
            res = json.loads(p.stdout)
        except Exception as e:                      # noqa: BLE001
            res = {"is_error": True, "result": f"runner error: {e}"}
        finally:
            try:
                drop_db(t)
            except Exception:                       # noqa: BLE001
                pass
        text = res.get("result") or ""
        if res.get("is_error") and ("limit" in text.lower() or res.get("api_error_status") in (429,)):
            stop["why"] = text[:300]
            print("STOP:", stop["why"], flush=True)
            return
        preds = sql_response_extract(text)
        rec = dict(t)
        rec["pred_sqls"] = preds
        rec["prompt_flow"] = [{"model": "my_model", "prompt": system + "\n\n" + prompt, "response": text}]
        rec["meta"] = {"turns": res.get("num_turns"), "secs": round(time.time() - t0),
                       "list_cost_usd": res.get("total_cost_usd")}
        with lock:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            n["done"] += 1
            print(f"{iid:<5} {t['db_id']:<24} {t['category']:<15} sqls={len(preds)} turns={res.get('num_turns')} "
                  f"{round(time.time() - t0)}s [{n['done']}]", flush=True)

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(solve, tasks))
    print("DONE" if not stop["why"] else "STOPPED (usage limit) - rerun the same command to resume")


if __name__ == "__main__":
    main()
