"""Run the prose-cap ablation for ONE cap, in its own process.

cap_sweep.py holds every database's documents for the unlimited case and then
builds 162 catalogues per cap on top of that, five times over. On this machine
it died twice partway through -- silently, mid-run, with the shell reporting
success because the exit code came from the pipe rather than from Python.

One cap per process fixes that without changing what is measured: the
catalogues for a cap are built, scored, written out, and the process exits,
so nothing accumulates across caps. The aggregation and McNemar then run over
the saved outcomes.

    python sweep_one_cap.py 0          -> outcome_0.json
    python sweep_one_cap.py unlimited  -> outcome_unlimited.json
"""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import cap_sweep as CS                                       # noqa: E402
from schemagate import Catalog                               # noqa: E402


def main():
    arg = sys.argv[1]
    cap = None if arg == "unlimited" else int(arg)

    rows = [json.loads(l) for l in CS.QUESTIONS.read_text("utf-8").splitlines() if l.strip()]
    have_gold = {p.stem for p in CS.GOLD.glob("*.sql")}
    dirs = {}
    for eng in CS.DBS.iterdir():
        for db in eng.iterdir():
            if db.is_dir():
                dirs.setdefault(db.name, db)
    cases = [r for r in rows if r["instance_id"] in have_gold and r["db"] in dirs]

    # Gold tables resolve against the schema, which does not depend on the cap.
    prepared = []
    known = {}
    for db in sorted({c["db"] for c in cases}):
        known[db] = {d.name.lower() for d in CS.load_db(dirs[db], None)}
    for c in cases:
        sql = CS.read_text(CS.GOLD / f"{c['instance_id']}.sql") \
            if hasattr(CS, "read_text") else (CS.GOLD / f"{c['instance_id']}.sql").read_text(
                "utf-8", errors="ignore")
        g = CS.gold_tables(sql, known[c["db"]])
        if g:
            prepared.append((c["instance_id"], c["db"], c["question"], sorted(g)))

    t0 = time.time()
    out = {str(k): {} for k in CS.KS}
    for db in sorted({p[1] for p in prepared}):
        cat = Catalog()
        for d in CS.load_db(dirs[db], cap):
            cat.add(d)
        cat.index()
        for iid, qdb, q, gold in prepared:
            if qdb != db:
                continue
            for k in CS.KS:
                picked = {n.split(".")[-1].lower() for n in cat.select(q, top_k=k).table_names}
                out[str(k)][iid] = set(gold) <= picked
        del cat

    emb = Catalog().embedder.name
    tag = "hashed" if emb.startswith("hashing") else "minilm"
    dest = pathlib.Path(__file__).resolve().parent / ("outcome_%s_%s.json" % (tag, arg))
    dest.write_text(json.dumps({"cap": arg, "embedder": emb, "n": len(prepared),
                                "seconds": round(time.time() - t0),
                                "outcome": out}), "utf-8")
    hits = "  ".join("k=%s:%d" % (k, sum(v.values())) for k, v in out.items())
    print("%-7s cap=%-9s n=%d  %s  (%ds)" % (tag, arg, len(prepared), hits, time.time() - t0))


if __name__ == "__main__":
    sys.exit(main())
