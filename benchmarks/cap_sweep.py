"""Sweep the prose cap on Spider 2.0, and test the pairs properly.

Two things the first ablation got wrong.

It reported net margins -- "+7 questions" -- for a paired design. A net of +7
is p=0.016 if seven questions flipped one way and nothing flipped back, and
p=0.19 if twenty-one flipped. The margin cannot tell those apart, so the
per-question outcomes are kept here and McNemar's exact test is run on the
discordant pairs.

And it tested one endpoint against the other. Truncating a description at 0
words or leaving it at 16,537 are two points; the question is where in between
the prose stops helping and starts hurting, which is a curve. Caps: 0, 40,
200, 1000, unlimited. The curve picks the default rather than me picking it.

Nothing else changes: same questions, same databases, same names, columns and
types. Only the number of words kept from `description`.
"""
import json
import math
import os
import pathlib
import re
import statistics
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent

from schemagate import Catalog, Column, ObjectDoc          # noqa: E402

ROOT = HERE / "Spider2" / "spider2-lite"
DBS = ROOT / "resource" / "databases"
GOLD = ROOT / "evaluation_suite" / "gold" / "sql"
QUESTIONS = HERE / "spider2_lite.jsonl"

CAPS = [0, 40, 200, 1000, None]          # None = unlimited, the shipped state
KS = [5, 10, 20]

_REF = re.compile(r"\b(?:from|join)\s+([`\"\w.\-*$]+)", re.I)
_CTE = re.compile(r"(?:\bwith\b|,)\s*([A-Za-z_]\w*)\s+as\s*\(", re.I)


def bare(ref):
    t = ref.strip().strip("`").strip('"').split(".")[-1].strip('`"')
    return t.rstrip("*").rstrip("_").lower()


def gold_tables(sql, known):
    body = re.sub(r"--[^\n]*", " ", sql)
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    ctes = {c.lower() for c in _CTE.findall(body)}
    return {b for b in (bare(r) for r in _REF.findall(body))
            if b and b not in ctes and b in known}


def raw_desc(d):
    v = d.get("description")
    if isinstance(v, (list, tuple)):
        v = " ".join(str(x) for x in v)
    return str(v) if v else None


def load_db(path, cap):
    docs = []
    for f in path.rglob("*.json"):
        try:
            d = json.loads(f.read_text("utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        names = d.get("column_names") or []
        types = d.get("column_types") or []
        cols = [Column(str(n), str(types[i] if i < len(types) else "TEXT"),
                       True, None, False) for i, n in enumerate(names)]
        if not cols:
            continue
        desc = raw_desc(d)
        if desc is not None and cap is not None:
            desc = " ".join(desc.split()[:cap]) or None
        docs.append(ObjectDoc(name=str(d.get("table_name") or f.stem),
                              schema=path.name, kind="TABLE",
                              description=desc, columns=cols))
    return docs


def mcnemar(b, c):
    """Exact two-sided binomial on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def main():
    rows = [json.loads(l) for l in QUESTIONS.read_text("utf-8").splitlines() if l.strip()]
    have_gold = {p.stem for p in GOLD.glob("*.sql")}
    dirs = {}
    for eng in DBS.iterdir():
        for db in eng.iterdir():
            if db.is_dir():
                dirs.setdefault(db.name, db)
    cases = [r for r in rows if r["instance_id"] in have_gold and r["db"] in dirs]

    emb = "MiniLM" if os.environ.get("SCHEMAGATE_AUTO_EMBEDDER") != "0" else "hashed"
    print(f"embedder: {emb}")

    # gold tables resolve against the schema, which does not depend on the cap
    known, prepared = {}, []
    base = {db: load_db(dirs[db], None) for db in sorted({c["db"] for c in cases})}
    for db, docs in base.items():
        known[db] = {d.name.lower() for d in docs}
    for c in cases:
        sql = (GOLD / f"{c['instance_id']}.sql").read_text("utf-8", errors="ignore")
        g = gold_tables(sql, known[c["db"]])
        if g:
            prepared.append((c["instance_id"], c["db"], c["question"], g))
    print(f"questions: {len(prepared)}\n")

    lens = []
    for db in base:
        for f in dirs[db].rglob("*.json"):
            try:                       # a few paths exceed what Windows opens
                n_ = len((raw_desc(json.loads(f.read_text("utf-8"))) or "").split())
            except Exception:          # noqa: BLE001
                continue
            if n_:
                lens.append(n_)
    if lens:
        print(f"descriptions on these databases: n={len(lens)}, "
              f"median {statistics.median(lens):.0f} words, max {max(lens):,}\n")

    # outcome[cap][k] = {instance_id: bool}
    outcome = {}
    for cap in CAPS:
        t0 = time.time()
        cats = {}
        for db in base:
            cat = Catalog()
            for d in load_db(dirs[db], cap):
                cat.add(d)
            cats[db] = cat.index()
        outcome[cap] = {k: {} for k in KS}
        for iid, db, q, gold in prepared:
            for k in KS:
                picked = {n.split(".")[-1].lower()
                          for n in cats[db].select(q, top_k=k).table_names}
                outcome[cap][k][iid] = gold <= picked
        label = "unlimited" if cap is None else f"cap={cap}"
        hits = " ".join(f"k={k}:{sum(outcome[cap][k].values()):3}" for k in KS)
        print(f"  {label:10} {hits}   ({time.time()-t0:.0f}s)")

    n = len(prepared)
    print(f"\nstrict recall, n={n}")
    print(f"  {'cap':>10} " + " ".join(f"{'k='+str(k):>13}" for k in KS))
    for cap in CAPS:
        label = "unlimited" if cap is None else str(cap)
        cells = []
        for k in KS:
            h = sum(outcome[cap][k].values())
            cells.append(f"{h:3}/{n} {100*h/n:5.1f}%")
        print(f"  {label:>10} " + " ".join(f"{c:>13}" for c in cells))

    print(f"\nMcNemar vs unlimited (b = fixed by the cap, c = broken by it)")
    for cap in CAPS[:-1]:
        for k in KS:
            u = outcome[None][k]
            v = outcome[cap][k]
            b = sum(1 for i in u if not u[i] and v[i])
            c = sum(1 for i in u if u[i] and not v[i])
            p = mcnemar(b, c)
            star = "  *" if p < 0.05 else ""
            print(f"  cap={str(cap):>9} k={k:<3} b={b:2} c={c:2} "
                  f"net={b-c:+3}  discordant={b+c:2}  p={p:.3f}{star}")


if __name__ == "__main__":
    main()
