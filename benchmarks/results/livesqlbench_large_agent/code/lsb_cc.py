"""LiveSQLBench-Large-v1 with schemagate + the exploring agent, driven through Claude Code (`claude -p`, the user's
Max subscription) instead of the API.

Same task prompt and table selection as lsb_agent.py. The only tool is Bash, and the only command allowed is
lsb_sql.py (read-only: always rolled back). The final answer is the last ```postgresql block of the reply.
The gold SQL and test cases are never shown to the model.

    python lsb_cc.py --sample 40 --seed 7 --out E:\\livesqlbench\\work\\cc_pilot
"""
import argparse
import json
import os
import random
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lsb_select as L  # noqa: E402
from lsb_agent import task_prompt  # noqa: E402
from lsb_run import parse_sql  # noqa: E402

def _claude():   # the newest Claude Code binary from the VS Code extension (its version changes on update)
    exts = sorted(Path.home().glob(".vscode/extensions/anthropic.claude-code-*-win32-x64/resources/native-binary/claude.exe"),
                  key=lambda p: p.stat().st_mtime)
    return str(exts[-1])


CLAUDE = _claude()
TOOL = "/c/Python313/python.exe E:/livesqlbench/work/lsb_sql.py"

SYSTEM = """You are an expert PostgreSQL analyst. You answer a user's data task on a real database.

Your only tool is Bash, and the only command you may run is the SQL runner, always in exactly this form:

/c/Python313/python.exe E:/livesqlbench/work/lsb_sql.py {iid} <<'SQL'
<your SQL here>
SQL

It runs the SQL on the task database and prints the columns, the row count and up to 20 rows of the last statement, or the error. Everything is rolled back afterwards, so you can also try DDL/DML and check its effect in the same call (separate statements with semicolons).

How to work:
1. Read the task and find every External Knowledge entry it refers to, directly or by meaning. Apply each definition, formula and threshold exactly as written there.
2. Before filtering or computing on a column, look at its real values (SELECT DISTINCT / sample rows): text columns may hold numbers with units or symbols, categories may differ in case or spelling, JSON columns have their own keys. Handle what you actually see.
3. Write the query, run it, and check the result: row count, NULLs, ranges and whether the numbers make sense. Fix it if something is off.
4. Output exactly the columns the user asks for, in the order the user mentions them, and nothing else. Round only where the task asks, to the number of decimals it asks for. Sort as the task asks.
5. For tasks that change the database (create, insert, update, functions, views, triggers), the answer is the statements that make the change; test them first.
6. Keep output minimal: one identifier plus the requested values; no extra name/label columns. In CREATE TABLE AS / views keep the source column names unless the user names the output columns.
7. Add no DDL the user did not ask for: no extra foreign keys, NOT NULL, primary keys or columns.
8. Name new objects conventionally: an index is idx_<table>_<column>, with the exact column name lowercased and no added underscores.
9. Map each phrase of the task to its External Knowledge entry first, then find the column whose name matches that entry's term.

Take the time to get it right: check every value, join and formula you rely on before you answer. End your final reply with the final PostgreSQL in one ```postgresql block (semicolons between statements if there are several)."""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=24)
    ap.add_argument("--kb", type=int, default=10)
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--only", default="")
    ap.add_argument("--max-turns", type=int, default=14)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--effort", default="high")
    ap.add_argument("--model", default="opus", help="Claude Code model alias or id, e.g. opus or claude-fable-5-2")
    ap.add_argument("--defs", default="", help="dir of kb_build.py outputs")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(L.BASE / "work/full.jsonl", encoding="utf-8")]
    if a.sample:                                   # same stratified sample as lsb_run.py / lsb_agent.py
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
    cwd = out / "cwd"                               # empty working dir: no CLAUDE.md / project memory loaded
    cwd.mkdir(exist_ok=True)
    pred_path = out / "predictions.jsonl"
    done = {json.loads(l)["instance_id"] for l in open(pred_path, encoding="utf-8")} if pred_path.exists() else set()
    dbs, lock = {}, threading.Lock()
    trace = open(out / "trace.jsonl", "a", encoding="utf-8")
    preds = open(pred_path, "a", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}  # subscription login only
    stop = {"why": None}

    def get_db(name):
        with lock:
            if name not in dbs:
                dbs[name] = L.DB(name)
            return dbs[name]

    def solve(r):
        iid = r["instance_id"]
        if iid in done or stop["why"]:
            return
        db = get_db(r["selected_database"])
        sel = {t.lower() for t in db.cat.select(db.selection_question(r["query"], a.kb), top_k=a.top_k).table_names}
        prompt = task_prompt(db, r["query"], sel)
        if a.defs:                                  # the verified definitions layer built offline by kb_build.py
            dp = Path(a.defs) / f"{r['selected_database']}.json"
            if dp.exists():
                prompt += ("\n\n# Verified SQL for the External Knowledge entries (built and tested on this database; "
                           "when the task uses one of these terms, use this exact expression, thresholds and casts, "
                           "and adapt only the aliases):\n" + dp.read_text("utf-8"))
        prompt += f"\n\n# User Task:\n{r['query']}"
        cmd = [CLAUDE, "-p", "--model", a.model, "--effort", a.effort, "--output-format", "json", "--max-turns", str(a.max_turns),
               "--tools", "Bash", "--allowedTools", f"Bash({TOOL} {iid}:*)",
               "--system-prompt", SYSTEM.replace("{iid}", iid), "--setting-sources", "", "--no-session-persistence"]
        t0 = time.time()
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", cwd=cwd, env=env, timeout=1800)
        try:
            res = json.loads(p.stdout)
        except Exception:                           # noqa: BLE001
            res = {"is_error": True, "result": (p.stdout or "")[-500:] + (p.stderr or "")[-500:]}
        text = res.get("result") or ""
        if res.get("is_error") and ("limit" in text.lower() or res.get("api_error_status") in (429,)):
            stop["why"] = text[:300]                # usage limit hit: stop cleanly, resume later
            print("STOP:", stop["why"], flush=True)
            return
        sql = parse_sql(text) if "```" in text else ""
        rec = {**r, "pred_sqls": [sql]}
        with lock:
            preds.write(json.dumps(rec, ensure_ascii=False) + "\n")
            preds.flush()
            trace.write(json.dumps({"id": iid, "tables": sorted(sel), "turns": res.get("num_turns"),
                                    "list_cost_usd": res.get("total_cost_usd"), "denials": res.get("permission_denials"),
                                    "is_error": res.get("is_error"), "subtype": res.get("subtype"),
                                    "result": text[-3000:], "secs": round(time.time() - t0, 1)},
                                   ensure_ascii=False, default=str) + "\n")
            trace.flush()
            print(f"{iid:<40} turns={res.get('num_turns')} sql={'yes' if sql else 'NO'} {round(time.time() - t0)}s", flush=True)

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(solve, rows))
    print("DONE" if not stop["why"] else "STOPPED (usage limit) - rerun the same command to resume")


if __name__ == "__main__":
    main()
