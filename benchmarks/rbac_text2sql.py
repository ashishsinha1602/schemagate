# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""schemagate on the RBAC Text-to-SQL benchmark (Fei, Jiang, Yang, Xiao; SIGMOD'27).

    github.com/2020dfff/RBAC-Text2SQL-Benchmark      arXiv 2607.22115

Each row of that benchmark is a question, a role, and a column-level policy: the
tables and columns the role may read. The system must answer it, or refuse with
"Sorry, I cannot answer." when the role cannot read what the answer needs. The
authors score it with six categories, AC-F1, SafeEX and two violation rates; this
script only writes predictions, and their own evaluator scores them, unchanged.

What schemagate does with a row is what it does for a caller in production:

  1. the policy becomes visibility: a table the policy does not list is hidden,
     a column it does not list is hidden, "*" keeps the whole table;
  2. select -> prompt_fragment -> generate_sql, as shipped. The model never sees
     a hidden object, and is told to reply INSUFFICIENT when what it was given
     cannot answer the question -- which becomes the benchmark's refusal;
  3. the SQL goes through run_query's scope check (`_check_scope`), which refuses
     any table or column the caller may not read, or cannot be resolved at all.
     A refused query becomes a refusal: in production it would never run.

Two prediction files come out, aligned to the dataset, so the scope check's own
effect is visible: `*_sg.sql` (all three steps) and `*_noscope.sql` (1 and 2
only, the "role-schema" setting the paper measures).

    python benchmarks/rbac_text2sql.py --dataset bird \\
        --rbac-json data/selected/bird/column_level_rbac_dataset_bird_v3_no_sm.json \\
        --db-dir E:/bird/dev_20240627/dev_databases --out E:/rbac/out/bird \\
        --model claude-sonnet-4-5 [--trials 5] [--questions N]

`--questions N` keeps the first N questions (all their role rows) and writes that
subset's dataset beside the predictions, for a pilot run. Rows outside the
selected trials get a blank line; the evaluator never reads them. Every model
call is logged to `<out>_calls.jsonl` and reused on a re-run.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import pathlib
import random
import sys
import threading
import time

REFUSAL = "Sorry, I cannot answer."
HIDDEN = ["__not_in_this_role_policy__"]



def question_key(row, index):
    """The grouping the benchmark's own fair-comparison sampler uses (access_protocol.question_key)."""
    key = row.get("metadata", {}).get("question_id")
    if isinstance(key, str) and key.strip():
        return key.strip()
    key = row.get("input")
    return key.strip() if isinstance(key, str) and key.strip() else f"question_{index}"


def trial_rows(rows, trials):
    """The row indices the evaluator's `--fair_comparison --num_trials T` will read (seeds 42..)."""
    groups = {}
    for i, row in enumerate(rows):
        groups.setdefault(question_key(row, i), []).append(i)
    needed = set()
    for seed in range(42, 42 + trials):
        rng = random.Random(seed)
        needed.update(rng.choice(g) for g in groups.values())
    return sorted(needed)


def apply_policy(cat, policy):
    """Make the catalogue show exactly what this role's policy lists, and nothing else."""
    pol = {t.lower(): {c.lower() for c in cols} for t, cols in (policy or {}).items()}
    for doc in cat.objects():
        cols = pol.get((doc.name or "").lower())
        doc.roles = None if cols is not None else list(HIDDEN)
        for col in doc.columns:
            col.roles = None if cols is not None and ("*" in cols or col.name.lower() in cols) else list(HIDDEN)


def load_descriptions(cat, db_dir):
    """BIRD ships each table's column notes as database_description/<table>.csv. They go in as column
    comments, which is where a real database keeps them and where schemagate reads them from."""
    import csv
    import io
    folder = pathlib.Path(db_dir) / "database_description"
    for doc in cat.objects():
        f = folder / f"{doc.name}.csv"
        if not f.exists():
            continue
        raw = f.read_bytes()
        text = None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        notes = {}
        for r in csv.DictReader(io.StringIO(text)):
            name = (r.get("original_column_name") or "").strip().lower()
            parts = [(r.get("column_description") or "").strip(), (r.get("value_description") or "").strip()]
            note = " ".join(" ".join(p.split()) for p in parts if p)
            if name and note:
                notes[name] = note
        for col in doc.columns:
            if col.name.lower() in notes and not col.comment:
                col.comment = notes[col.name.lower()]
    cat.index()


def one_line(sql):
    return " ".join(str(sql).split())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dataset", choices=["spider", "bird"], required=True)
    ap.add_argument("--rbac-json", required=True)
    ap.add_argument("--db-dir", required=True, help="directory of <db_id>/<db_id>.sqlite")
    ap.add_argument("--out", required=True, help="output prefix")
    ap.add_argument("--model", default="claude-sonnet-4-5")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--questions", type=int, default=0)
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--descriptions", action="store_true",
                    help="load BIRD's database_description CSVs as column comments")
    ap.add_argument("--notice", action="store_true",
                    help="Catalog.restriction_notice: say in the prompt that the view is partial (no names)")
    a = ap.parse_args()

    from schemagate import Catalog, Principal
    from schemagate.ai.providers import AnthropicProvider
    from schemagate.answer import UnsafeSQL, generate_sql
    from schemagate.mcp_server import _check_scope

    rows = json.loads(pathlib.Path(a.rbac_json).read_text("utf-8-sig"))
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if a.questions:
        keep, seen = [], []
        for i, r in enumerate(rows):
            k = question_key(r, i)
            if k not in seen:
                if len(seen) == a.questions:
                    continue
                seen.append(k)
            if k in seen:
                keep.append(r)
        rows = keep
        subset = out.with_name(out.name + "_dataset.json")
        subset.write_text(json.dumps(rows, ensure_ascii=False), "utf-8")
        print(f"subset: {len(rows)} rows over {len(seen)} questions -> {subset}")
    need = trial_rows(rows, a.trials)
    print(f"{len(rows)} rows; {len(need)} read by {a.trials} fair-comparison trial(s)")

    log_path = out.with_name(out.name + "_calls.jsonl")
    done = {}
    if log_path.exists():
        for line in log_path.read_text("utf-8").splitlines():
            e = json.loads(line)
            if e.get("model") == a.model and e.get("notice", False) == a.notice and e.get("desc", False) == a.descriptions and "error" not in e:
                done[e["i"]] = e
    log = log_path.open("a", encoding="utf-8")
    lock = threading.Lock()
    prov = AnthropicProvider(model=a.model)
    who = Principal("bench:rbac")
    # One catalogue per database, read once; the policy is applied per row under a lock
    # (visibility lives on the shared docs), and only the model call runs in parallel.
    cats, cat_locks = {}, {}

    def catalog(db_id):
        with lock:
            if db_id not in cats:
                path = pathlib.Path(a.db_dir) / db_id / f"{db_id}.sqlite"
                cats[db_id] = Catalog(name=db_id).bootstrap(f"sqlite:///{path.as_posix()}")
                if a.descriptions:
                    load_descriptions(cats[db_id], path.parent)
                cat_locks[db_id] = threading.Lock()
        return cats[db_id], cat_locks[db_id]

    def run(i):
        if i in done:
            return done[i]
        row = rows[i]
        question = row["input"]
        ev = (row.get("metadata") or {}).get("evidence")
        if a.dataset == "bird" and ev:
            question = f"{question}\nHint: {ev}"
        cat, cl = catalog(row["db_id"])
        with cl:
            apply_policy(cat, row.get("policy"))
            cat.restriction_notice = a.notice                 # the library's own notice, as shipped
            sel = cat.select(question, top_k=a.top_k, principal=who)
            fragment = sel.prompt_fragment()
            snapshot = [(d, d.roles, [(c, c.roles) for c in d.columns]) for d in cat.objects()]
        e = {"i": i, "model": a.model, "notice": a.notice, "desc": a.descriptions, "db_id": row["db_id"], "role": row.get("role"),
             "gold": (row.get("metadata") or {}).get("permission")}
        try:
            sql = generate_sql(prov, question, fragment, dialect="SQLite")
            e["sql"] = one_line(sql)
        except UnsafeSQL as ex:
            e["insufficient"] = str(ex)[:120]
        except Exception as ex:                                  # noqa: BLE001
            e["error"] = f"{type(ex).__name__}: {str(ex)[:200]}"
        if "sql" in e:
            with cl:
                for d, roles, cols in snapshot:                   # this row's policy, again
                    d.roles = roles
                    for c, r in cols:
                        c.roles = r
                e["scope"] = _check_scope(cat, e["sql"], who)
        with lock:
            log.write(json.dumps(e, ensure_ascii=False) + "\n")
            log.flush()
        return e

    t0 = time.time()
    results = {}
    with cf.ThreadPoolExecutor(a.workers) as pool:
        for n, e in enumerate(pool.map(run, need), 1):
            results[e["i"]] = e
            if n % 50 == 0:
                print(f"  {n}/{len(need)}  {time.time() - t0:.0f}s", flush=True)

    sg, noscope = [""] * len(rows), [""] * len(rows)
    for i, e in results.items():
        if "sql" in e:
            noscope[i] = e["sql"]
            sg[i] = REFUSAL if e.get("scope") else e["sql"]
        else:
            noscope[i] = sg[i] = REFUSAL                          # INSUFFICIENT, or a call that failed
    tag = ("_desc" if a.descriptions else "") + ("_notice" if a.notice else "")
    for name, preds in (("sg" + tag, sg), ("noscope" + tag, noscope)):
        p = out.with_name(f"{out.name}_{name}.sql")
        p.write_text("\n".join(preds) + "\n", "utf-8")
        print(f"wrote {p}")
    errs = sum("error" in e for e in results.values())
    blocked = sum(bool(e.get("scope")) for e in results.values())
    insuff = sum("insufficient" in e for e in results.values())
    print(f"done in {time.time() - t0:.0f}s: {len(results)} rows, {insuff} INSUFFICIENT, "
          f"{blocked} refused by the scope check, {errs} call errors")
    if errs:
        print("call errors are written as refusals; re-run to retry them", file=sys.stderr)


if __name__ == "__main__":
    main()
