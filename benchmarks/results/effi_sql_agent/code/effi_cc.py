"""Effi-SQL (BIRD) with a Claude Code agent (`claude -p`, the user's Max subscription, no API key).

For each of the 300 slow PostgreSQL queries the agent gets the original SQL and its query plan, and one tool:
effi_sql.py (run / explain / compare, always rolled back). It must return a rewrite that gives the same rows and
runs faster; if nothing is faster it returns the original. The benchmark's reference rewrite (optimized_sql) and
its timings are never shown to the agent.

Output: predictions.jsonl = the benchmark record + `prediction` (the final ```sql block), the format Diff-SQL's
evaluator reads with EVAL_SQL_MODE=end2end EVAL_RESPONSE_FIELD=prediction.

    python effi_cc.py --out E:\\effisql\\work\\pilot30 --sample 30
"""
import argparse
import json
import os
import random
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BENCH = Path(r"E:\effisql\Diff-SQL\data\benchmark\effi-sql\effi-sql-pg.jsonl")
TOOL = "/c/Python313/python.exe E:/effisql/work/effi_sql.py"
HIDDEN = ("optimized_sql", "fast_time", "optimized_explain_analyze")   # never in the prompt


def _claude():
    exts = sorted(Path.home().glob(".vscode/extensions/anthropic.claude-code-*-win32-x64/resources/native-binary/claude.exe"),
                  key=lambda p: p.stat().st_mtime)
    return str(exts[-1])


SYSTEM = """You are a PostgreSQL performance expert. You rewrite one slow SQL query so it returns exactly the same result and runs faster.

Your only tool is Bash, and the only command you may run is the SQL tool, always in one of these forms:

{tool} {tid} run <<'SQL'
<sql>
SQL

{tool} {tid} explain <<'SQL'
<sql>
SQL

{tool} {tid} compare <<'SQL'
<your rewrite>
SQL

`run` executes SQL (e.g. to look at schema via information_schema / pg_indexes, row counts, value distributions). `explain` shows EXPLAIN (ANALYZE, BUFFERS). `compare` runs the ORIGINAL query and your rewrite, tells you whether the results are identical and both times. Everything is rolled back; you cannot create indexes or change the database, so only the query text may change.

How to work:
1. Read the original query and its plan; find where the time goes (seq scans over big tables, repeated subqueries, bad joins, sorts/aggregates over too many rows, non-sargable predicates, OR chains, correlated subqueries, DISTINCT/UNION where not needed).
2. Write a semantically equivalent rewrite (same rows, same columns in the same order, same ordering if the original has ORDER BY, same NULL and duplicate behaviour).
3. Check it with `compare`. Only accept a rewrite with identical_results = true. Iterate if it is not faster.
The bar is high: you are scored against an expert rewrite of this same query and only count if yours is clearly faster than that one, so do not stop at the first faster version. Find the dominant cost and remove it; aim for 2x or more over the original, ideally an order of magnitude.
Each `compare` is slow (it runs the queries on a large database), so use `compare` at most 3 times; `explain` also executes the query, so use it sparingly too.
4. Correctness first: if no rewrite is both identical and faster, return the original query unchanged.

End your final reply with exactly one ```sql block containing the final query."""


def parse_sql(text):
    blocks = re.findall(r"```sql\s*(.*?)```", text, re.S | re.I)
    return blocks[-1].strip() if blocks else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--only", default="")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--max-turns", type=int, default=20)
    ap.add_argument("--effort", default="high")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--prev", default="", help="predictions.jsonl of an earlier pass (our own answers)")
    ap.add_argument("--prev-check", default="", help="self_check.jsonl with our measured speedups")
    a = ap.parse_args()
    prev, prev_sp = {}, {}
    if a.prev:
        for l in open(a.prev, encoding="utf-8"):
            r = json.loads(l)
            m = re.findall(r"```sql\s*(.*?)```", r["prediction"], re.S | re.I)
            prev[str(r["id"])] = m[-1].strip() if m else ""
    if a.prev_check:
        for l in open(a.prev_check, encoding="utf-8"):
            r = json.loads(l)
            prev_sp[str(r["id"])] = (r.get("identical"), r.get("speedup_vs_original"))

    rows = [json.loads(l) for l in open(BENCH, encoding="utf-8")]
    if a.sample:                                    # stratified by database and difficulty
        rnd = random.Random(a.seed)
        groups = {}
        for r in rows:
            groups.setdefault((r["db"], r["difficulty"]), []).append(r)
        for g in groups.values():
            rnd.shuffle(g)
        picked = []
        while len(picked) < a.sample and any(groups.values()):
            for k in sorted(groups):
                if groups[k] and len(picked) < a.sample:
                    picked.append(groups[k].pop())
        rows = picked
    if a.only:
        want = set(a.only.split(","))
        rows = [r for r in rows if str(r["id"]) in want]

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cwd = out / "cwd"
    cwd.mkdir(exist_ok=True)
    pred_path = out / "predictions.jsonl"
    done = {str(json.loads(l)["id"]) for l in open(pred_path, encoding="utf-8")} if pred_path.exists() else set()
    lock = threading.Lock()
    preds = open(pred_path, "a", encoding="utf-8")
    trace = open(out / "trace.jsonl", "a", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    claude = _claude()
    stop = {"why": None}

    def solve(r):
        tid = str(r["id"])
        if tid in done or stop["why"]:
            return
        plan = r.get("base_explain_analyze") or ""
        plan = (plan if isinstance(plan, str) else json.dumps(plan, separators=(",", ":")))[:12000]
        prompt = (f"# Database: {r['db']} (PostgreSQL)\n\n# Original slow query:\n```sql\n{r['base_sql']}\n```\n\n"
                  f"# Its EXPLAIN ANALYZE (from the benchmark machine):\n{plan}\n\n"
                  "Rewrite it to run faster with exactly the same result.")
        if prev.get(tid):
            ident, sp = prev_sp.get(tid, (None, None))
            note = ("its results were NOT identical, so it is unusable" if ident is False
                    else f"it measured {sp}x faster than the original" if sp else "its speed is unknown")
            prompt += (f"\n\n# An earlier attempt produced this rewrite ({note}):\n```sql\n{prev[tid]}\n```\n"
                       "That is not good enough. Look for a fundamentally better approach that removes the dominant "
                       "cost. Return whichever correct query is fastest (yours, the earlier one, or the original).")
        cmd = [claude, "-p", "--model", a.model, "--effort", a.effort, "--output-format", "json",
               "--max-turns", str(a.max_turns), "--tools", "Bash", "--allowedTools", f"Bash({TOOL} {tid}:*)",
               "--system-prompt", SYSTEM.replace("{tool}", TOOL).replace("{tid}", tid),
               "--setting-sources", "", "--no-session-persistence"]
        t0 = time.time()
        try:
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", cwd=cwd, env=env, timeout=3600)
            res = json.loads(p.stdout)
        except Exception as e:                      # noqa: BLE001
            res = {"is_error": True, "result": f"runner error: {e}"}
        text = res.get("result") or ""
        if res.get("is_error") and ("limit" in text.lower() or res.get("api_error_status") in (429,)):
            stop["why"] = text[:300]
            print("STOP:", stop["why"], flush=True)
            return
        sql = parse_sql(text) or r["base_sql"]      # no answer: keep the original (correct, no speedup)
        rec = {k: v for k, v in r.items()}
        rec["prediction"] = f"```sql\n{sql}\n```"
        with lock:
            preds.write(json.dumps(rec, ensure_ascii=False) + "\n")
            preds.flush()
            trace.write(json.dumps({"id": tid, "db": r["db"], "turns": res.get("num_turns"),
                                    "list_cost_usd": res.get("total_cost_usd"), "is_error": res.get("is_error"),
                                    "kept_original": sql.strip() == r["base_sql"].strip(),
                                    "result": text[-3000:], "secs": round(time.time() - t0, 1)},
                                   ensure_ascii=False, default=str) + "\n")
            trace.flush()
            print(f"{tid:<6} {r['db']:<24} turns={res.get('num_turns')} "
                  f"{'ORIGINAL' if sql.strip() == r['base_sql'].strip() else 'rewrite'} {round(time.time() - t0)}s", flush=True)

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(solve, rows))
    print("DONE" if not stop["why"] else "STOPPED (usage limit) - rerun the same command to resume")


if __name__ == "__main__":
    main()
