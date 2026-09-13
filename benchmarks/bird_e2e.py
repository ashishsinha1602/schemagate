"""schemagate end to end on BIRD dev: execution accuracy, not table recall.

Every other number in this repo scores retrieval -- did the right tables get
selected. This one scores the thing the benchmark scores: run the SQL, run
BIRD's reference SQL, and compare the rows. That is execution accuracy, the
metric published systems report, and it is the only number here that is
directly comparable to anything outside this project.

The pipeline is the shipped one: Catalog.select() picks the tables,
generate_sql() writes the query against only those tables, run_sql() executes
it. No retries beyond what the library already does, no hand-holding, and the
model never sees a table selection did not return.

A stratified sample rather than all 1,534 questions, because each one is a
frontier-model call. The sample is seeded, so it is the same sample every run,
and the per-database counts are proportional.

Comparison of results is set-based on the returned rows, which is how BIRD's
own evaluator does it: order is not scored, and a query that returns the right
rows in a different order is correct.
"""
import json
import os
import pathlib
import random
import sqlite3
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent

from schemagate import Catalog                                # noqa: E402
from schemagate.answer import UnsafeSQL, generate_sql         # noqa: E402
from schemagate.ai.providers import AnthropicProvider         # noqa: E402

DEV = HERE / "dev_20240627" / "dev.json"
DBROOT = HERE / "dev_databases"
SAMPLE = int(os.environ.get("BIRD_SAMPLE", "150"))
TOP_K = int(os.environ.get("BIRD_TOP_K", "10"))
MODEL = os.environ.get("SG_MODEL", "claude-opus-5")
USE_EVIDENCE = os.environ.get("BIRD_EVIDENCE", "1") == "1"


def rows_of(db_path, sql, limit=2000):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        con.text_factory = lambda b: b.decode("utf-8", "replace")
        cur = con.execute(sql)
        return cur.fetchmany(limit)
    finally:
        con.close()


def same(a, b):
    """Set comparison on rows, the way BIRD's evaluator scores it."""
    if a is None or b is None:
        return False
    return {tuple(map(repr, r)) for r in a} == {tuple(map(repr, r)) for r in b}


def main():
    dev = json.loads(DEV.read_text("utf-8"))
    rnd = random.Random(20260913)
    by_db = {}
    for r in dev:
        by_db.setdefault(r["db_id"], []).append(r)

    picked = []
    for db, rs in sorted(by_db.items()):
        n = max(1, round(SAMPLE * len(rs) / len(dev)))
        picked += rnd.sample(rs, min(n, len(rs)))
    rnd.shuffle(picked)
    print(f"BIRD dev: {len(dev)} questions, sampling {len(picked)} "
          f"across {len(by_db)} databases (seeded)")
    print(f"model {MODEL}, top_k {TOP_K}, "
          f"evidence {'passed through' if USE_EVIDENCE else 'withheld'}\n")

    cats = {}
    for db in sorted({r["db_id"] for r in picked}):
        f = DBROOT / db / f"{db}.sqlite"
        cat = Catalog().bootstrap(f"sqlite:///{f}")
        cat.infer_foreign_keys()
        cats[db] = (cat.index(), f)

    prov = AnthropicProvider(model=MODEL)
    ok = ran = wrote = 0
    t0 = time.time()
    for i, r in enumerate(picked, 1):
        db = r["db_id"]
        cat, path = cats[db]
        q = r["question"]
        if USE_EVIDENCE and (r.get("evidence") or "").strip():
            q = q + " " + r["evidence"].strip()
        try:
            sql = generate_sql(prov, q, cat.select(q, top_k=TOP_K).prompt_fragment(),
                               dialect="SQLite")
            wrote += 1
        except UnsafeSQL:
            print(f"  {i:3}/{len(picked)} {db[:22]:22} REFUSED")
            continue
        except Exception as e:                               # noqa: BLE001
            print(f"  {i:3}/{len(picked)} {db[:22]:22} ERROR {type(e).__name__}")
            continue
        try:
            got = rows_of(path, sql)
            ran += 1
        except Exception as e:                               # noqa: BLE001
            print(f"  {i:3}/{len(picked)} {db[:22]:22} SQL FAILED "
                  f"{str(e).splitlines()[0][:44]}")
            continue
        try:
            want = rows_of(path, r["SQL"])
        except Exception:                                    # noqa: BLE001
            print(f"  {i:3}/{len(picked)} {db[:22]:22} (gold itself failed)")
            continue
        hit = same(got, want)
        ok += hit
        if i % 10 == 0 or not hit:
            print(f"  {i:3}/{len(picked)} {db[:22]:22} "
                  f"{'correct' if hit else 'wrong  '}  running EA "
                  f"{100*ok/i:5.1f}%")

    n = len(picked)
    print(f"\nBIRD dev, n={n}, {MODEL}")
    print(f"  SQL written           {wrote}/{n} ({100*wrote/n:.1f}%)")
    print(f"  executed without error {ran}/{n} ({100*ran/n:.1f}%)")
    print(f"  EXECUTION ACCURACY    {ok}/{n} ({100*ok/n:.1f}%)")
    print(f"  ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
