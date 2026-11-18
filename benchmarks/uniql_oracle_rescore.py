# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""UniQL on Oracle, last step: score again the questions the database refused to connect for.

UniQL's evaluator opens fresh Oracle connections for every question. On Oracle Free a long run can
exhaust the listener's handlers (DPY-6005 / ORA-12516, "Listener refused connection") and every
question scored while that lasts counts as wrong without its SQL ever running: 170 of 1,534 in one
dry run in which the gold SQL itself was the prediction. Nothing about those questions was judged.

This finds them in the evaluator's output, runs UniQL's evaluator again on just those (same
predictions, same gold, same comparison), puts the new verdicts in place, and prints the totals the
evaluator prints. Questions that fail to connect again stay wrong and are counted.

    python benchmarks/uniql_oracle_rescore.py --predictions out/oracle_full.json \
        --results out/eval/schemagate-full/oracle_schemagate-full.json \
        --uniql uniql --db-root bird_dev/dev_databases --model schemagate-full --out out/eval/final.json
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import subprocess
import sys

REFUSED = ("DPY-6005", "ORA-12516", "Listener refused connection", "Prediction not dispatched")


def refused(row) -> bool:
    return not row.get("res") and any(s in (row.get("error") or "") for s in REFUSED)


def totals(preds, verdict):
    by = collections.defaultdict(lambda: [0, 0])
    for i, p in enumerate(preds):
        for key in (p.get("difficulty") or "unknown", "total"):
            by[key][0] += 1
            by[key][1] += bool(verdict[i])
    return {k: {"count": n, "accuracy": round(100.0 * ok / n, 2)} for k, (n, ok) in by.items()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictions", required=True)
    ap.add_argument("--results", required=True, help="the evaluator's oracle_<model>.json")
    ap.add_argument("--uniql", required=True, help="UniQL checkout")
    ap.add_argument("--db-root", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rounds", type=int, default=3)
    a = ap.parse_args(argv)

    preds = json.loads(pathlib.Path(a.predictions).read_text("utf-8"))
    rows = json.loads(pathlib.Path(a.results).read_text("utf-8"))
    if len(rows) != len(preds):
        sys.exit(f"{len(rows)} results for {len(preds)} predictions")
    by_idx = {r["sql_idx"]: r for r in rows}
    verdict = [bool(by_idx[i].get("res")) for i in range(len(preds))]
    pending = [i for i in range(len(preds)) if refused(by_idx[i])]
    first = len(pending)
    work = pathlib.Path(a.out).parent / "rescore"
    work.mkdir(parents=True, exist_ok=True)
    for rnd in range(1, a.rounds + 1):
        if not pending:
            break
        sub = work / f"round{rnd}.json"
        sub.write_text(json.dumps([preds[i] for i in pending], indent=1), "utf-8")
        model = f"{a.model}-rescore{rnd}"
        subprocess.run([sys.executable, "evaluate.py", "--predicted_sql_path", str(sub.resolve()),
                        "--dialect", "oracle", "--db_root_path", str(pathlib.Path(a.db_root).resolve()),
                        "--num_cpus", "1", "--model", model, "--output_dir", str(work.resolve())],
                       cwd=pathlib.Path(a.uniql) / "evaluation", check=True,
                       stdout=subprocess.DEVNULL)
        again = json.loads((work / model / f"oracle_{model}.json").read_text("utf-8"))
        still = []
        for r in again:
            i = pending[r["sql_idx"]]
            if r.get("predicted_sql") not in (None, preds[i]["pred_sqls"][0]):
                sys.exit(f"rescore row {r['sql_idx']} is not question index {i}")
            verdict[i] = bool(r.get("res"))
            if refused(r):
                still.append(i)
        print(f"round {rnd}: rescored {len(pending)}, still refused {len(still)}", flush=True)
        pending = still

    summary = {"refused_first_pass": first, "refused_after_rescore": len(pending),
               "accuracy": totals(preds, verdict)}
    pathlib.Path(a.out).write_text(json.dumps({"summary": summary, "verdicts": [
        {"question_id": p["question_id"], "difficulty": p.get("difficulty"), "res": int(v)}
        for p, v in zip(preds, verdict)]}, indent=1), "utf-8")
    acc = summary["accuracy"]
    print("            " + "  ".join(f"{k:>11}" for k in ("simple", "moderate", "challenging", "total")))
    print("count       " + "  ".join(f"{acc.get(k, {}).get('count', 0):>11}"
                                     for k in ("simple", "moderate", "challenging", "total")))
    print("accuracy    " + "  ".join(f"{acc.get(k, {}).get('accuracy', 0):>11}"
                                     for k in ("simple", "moderate", "challenging", "total")))
    print(f"refused to connect: {first} on the first pass, {len(pending)} after rescoring")


if __name__ == "__main__":
    main()
