"""LiveSQLBench-Large-v1 with schemagate + an exploring agent.

Per task:
  1. schemagate selects tables exactly as in lsb_run.py (question + nearest KB entries, FKs followed, top_k)
  2. the model gets the same schema / column meanings / knowledge-base prompt, plus two tools:
       run_sql(sql)     - runs on the task's database inside a transaction that is always rolled back
                          (preprocess_sql first, as the scorer does); returns columns, row count, first rows
       submit_sql(sql)  - the final answer; this is what goes into pred_sqls
     It can look at real values, check formats, test its query and fix it, up to --max-steps tool calls.
  3. predictions are written in the scorer's input format and scored afterwards by the official scorer.

The gold SQL and test cases are never shown to the model. Exact cost per call from response.usage
(prompt caching on the schema prefix). Stops when --max-usd is reached.
"""
import argparse
import json
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).parent))
import lsb_select as L  # noqa: E402
from lsb_run import parse_sql  # noqa: E402

PRICE = {"claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0)}   # $ per 1M input / output

SYSTEM = """You are an expert PostgreSQL analyst. You answer a user's data task on a real database.

You have two tools:
- run_sql: run any SQL on the database and see the result. Everything is rolled back afterwards, so you can also try DDL/DML and check its effect in the same call (separate statements with semicolons; the result of the last statement is shown).
- submit_sql: submit your final SQL. Call it exactly once, at the end.

How to work:
1. Read the task and find every External Knowledge entry it refers to, directly or by meaning. Apply each definition, formula and threshold exactly as written there.
2. Before filtering or computing on a column, look at its real values (SELECT DISTINCT / sample rows): text columns may hold numbers with units or symbols, categories may differ in case or spelling, JSON columns have their own keys. Handle what you actually see.
3. Write the query, run it, and check the result: row count, NULLs, ranges and whether the numbers make sense. Fix it if something is off.
4. Output exactly the columns the user asks for, in the order the user mentions them, and nothing else. Round only where the task asks, to the number of decimals it asks for. Sort as the task asks.
5. For tasks that change the database (create, insert, update, functions, views, triggers), submit the statements that make the change; test them first with run_sql.

Be efficient: a few exploratory queries, then submit."""

TOOLS = [
    {"name": "run_sql", "description": "Run SQL on the task database (rolled back afterwards). Returns the columns, the row count and up to 20 rows of the last statement, or the error.",
     "input_schema": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}},
    {"name": "submit_sql", "description": "Submit the final PostgreSQL for the task. Ends the task.",
     "input_schema": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]},
     "cache_control": {"type": "ephemeral"}},
]


def task_prompt(db, query, tables):
    schema = "\n\n".join(db.blocks[t] for t in sorted(tables))
    meanings = json.dumps(db.table_meanings(tables), indent=2)
    return (f"# Database Schema (the tables most relevant to the task; others exist and can be inspected via information_schema):\n{schema}\n\n"
            f"# Column Meanings:\n{meanings}\n\n# External Knowledge:\n{db.kb_text()}")


def run_sql(dbname, pre, sql, port):
    conn = psycopg2.connect(host="localhost", port=port, user="root", password="123123", dbname=dbname)
    try:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '30s'")
        for p in pre or []:
            if p and p.strip():
                cur.execute(p)
        cur.execute(sql)
        if cur.description is None:
            return f"OK (no result set; rowcount {cur.rowcount})"
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(5001)
        n = len(rows)
        shown = [[(str(v)[:120] if v is not None else None) for v in r] for r in rows[:20]]
        return json.dumps({"columns": cols, "row_count": n if n <= 5000 else ">5000", "rows": shown}, default=str)[:6000]
    except Exception as e:                                   # noqa: BLE001
        return "ERROR: " + str(e).strip().splitlines()[0][:500]
    finally:
        conn.rollback()
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--top-k", type=int, default=24)
    ap.add_argument("--kb", type=int, default=10)
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--only", default="", help="comma-separated instance ids")
    ap.add_argument("--max-steps", type=int, default=10)
    ap.add_argument("--max-usd", type=float, default=40.0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--port", type=int, default=5435)
    ap.add_argument("--out", required=True)
    ap.add_argument("--env-file", default=r"E:\dev_xdott_new\frontend\xdott-crm-dev-backend\.env")
    a = ap.parse_args()

    import anthropic
    import os
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key and a.env_file:                    # only this one line is read; the value is never printed
        for line in open(a.env_file, encoding="utf-8-sig", errors="ignore"):
            m = re.match(r"\s*(?:export\s+)?ANTHROPIC_API_KEY\s*=\s*(.*)$", line)
            if m and m.group(1).strip().strip('"').strip("'"):
                key = m.group(1).strip().strip('"').strip("'")
    if not key:
        raise SystemExit("no ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=key, max_retries=4)
    pin, pout = PRICE[a.model]

    rows = [json.loads(l) for l in open(L.BASE / "work/full.jsonl", encoding="utf-8")]
    if a.sample:                                   # same stratified sample as lsb_run.py
        rnd = random.Random(a.seed)
        by_db = {}
        for r in rows:
            by_db.setdefault(r["selected_database"], []).append(r)
        per = max(1, a.sample // len(by_db))
        picked = []
        for name in sorted(by_db):
            rnd.shuffle(by_db[name])
            picked += by_db[name][:per]
        rest = [r for r in rows if r not in picked]
        rnd.shuffle(rest)
        rows = (picked + rest)[:a.sample]
    if a.only:
        want = set(a.only.split(","))
        rows = [r for r in rows if r["instance_id"] in want]

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    done = {}
    pred_path = out / "predictions.jsonl"
    if pred_path.exists():
        for l in open(pred_path, encoding="utf-8"):
            d = json.loads(l)
            done[d["instance_id"]] = d
    dbs, lock = {}, threading.Lock()
    spend = {"usd": sum(d.get("cost_usd", 0) for d in done.values())}
    trace = open(out / "trace.jsonl", "a", encoding="utf-8")
    preds = open(pred_path, "a", encoding="utf-8")

    def get_db(name):
        with lock:
            if name not in dbs:
                dbs[name] = L.DB(name)
            return dbs[name]

    def call(messages):
        with lock:
            if spend["usd"] >= a.max_usd:
                raise SystemExit(f"--max-usd {a.max_usd} reached")
        with client.messages.stream(model=a.model, max_tokens=32000, system=SYSTEM, tools=TOOLS, messages=messages,
                                    thinking={"type": "adaptive"},
                                    extra_body={"output_config": {"effort": a.effort}}) as s:
            r = s.get_final_message()
        u = r.usage
        cw = getattr(u, "cache_creation_input_tokens", 0) or 0
        cr = getattr(u, "cache_read_input_tokens", 0) or 0
        cost = (u.input_tokens * pin + cw * pin * 1.25 + cr * pin * 0.1 + u.output_tokens * pout) / 1e6
        with lock:
            spend["usd"] += cost
        return r, cost, {"in": u.input_tokens, "cw": cw, "cr": cr, "out": u.output_tokens}

    def solve(r):
        iid = r["instance_id"]
        if iid in done:
            return
        db = get_db(r["selected_database"])
        sel = {t.lower() for t in db.cat.select(db.selection_question(r["query"], a.kb), top_k=a.top_k).table_names}
        tmpl = r["selected_database"] + "_template"
        pre = r.get("preprocess_sql") or []
        messages = [{"role": "user", "content": [
            {"type": "text", "text": task_prompt(db, r["query"], sel), "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": f"# User Task:\n{r['query']}"}]}]
        t0, cost, steps, final, last_sql = time.time(), 0.0, [], None, None
        for step in range(a.max_steps + 1):
            if step == a.max_steps:
                messages.append({"role": "user", "content": "Step limit reached. Call submit_sql now with your best query."})
            resp, c, use = call(messages)
            cost += c
            messages.append({"role": "assistant", "content": resp.content})
            uses = [b for b in resp.content if b.type == "tool_use"]
            if not uses:
                text = "".join(b.text for b in resp.content if b.type == "text")
                final = parse_sql(text) if "```" in text else last_sql
                steps.append({"use": use, "note": "no tool call"})
                break
            results = []
            for b in uses:
                sql = (b.input or {}).get("sql") if isinstance(b.input, dict) else None
                if not isinstance(sql, str) or not sql.strip():
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": "ERROR: missing sql", "is_error": True})
                    continue
                if b.name == "submit_sql":
                    final = sql
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": "submitted"})
                else:
                    last_sql = sql
                    res = run_sql(tmpl, pre, sql, a.port)
                    steps.append({"use": use, "sql": sql[:2000], "res": res[:300]})
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": res})
            if final is not None:
                steps.append({"use": use, "submit": final[:4000]})
                break
            messages.append({"role": "user", "content": results})
        final = final or last_sql or ""
        rec = {**r, "pred_sqls": [final], "cost_usd": round(cost, 5)}
        gold = L.gold_tables(r["sol_sql"], set(db.blocks))
        with lock:
            preds.write(json.dumps(rec, ensure_ascii=False) + "\n")
            preds.flush()
            trace.write(json.dumps({"id": iid, "model": a.model, "tables": sorted(sel), "gold_tables_covered": gold <= sel,
                                    "steps": steps, "cost_usd": round(cost, 5), "secs": round(time.time() - t0, 1)},
                                   ensure_ascii=False, default=str) + "\n")
            trace.flush()
            print(f"{iid:<40} steps={len(steps)} ${cost:.3f}  total ${spend['usd']:.2f}", flush=True)

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(solve, rows))
    print(f"DONE {len(rows)} tasks, spend ${spend['usd']:.2f}")


if __name__ == "__main__":
    main()
