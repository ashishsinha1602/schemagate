"""Does an ontology make the SQL more accurate? BIRD dev, execution accuracy, with and without.

The ontology is not written by us. BIRD's annotators attached "evidence" to every dev question --
"female refers to gender = 'F'", "eligible free rate = `Free Meal Count (K-12)` / `Enrollment (K-12)`" --
which is exactly what a company's glossary holds. Protocol:

  1. Each database's questions are split by position: even = HISTORY, odd = TEST.
  2. The ontology is built automatically from the HISTORY questions' evidence only: every clause of the form
     "<term> refers to / means / = <rule>" becomes a concept named <term> whose definition is the clause,
     mapped to the tables whose columns the rule mentions.
  3. TEST questions are asked WITHOUT their evidence, three times each:
       A   no ontology
       A2  no ontology again -- the noise floor: how many answers flip with nothing changed
       B   with the ontology
     The model writes SQL against the selected tables (the shipped pipeline: select -> prompt_fragment ->
     generate_sql), it runs read-only, and the rows are compared set-wise with BIRD's reference answer.

A gain counts only if B beats A by more than A2 differs from A. Seeded sample, stratified by database.

    BIRD_DIR=E:/bird/dev_20240627 SG_MODEL=claude-sonnet-5 BIRD_SAMPLE=200 python benchmarks/bird_ontology.py
"""
import json
import math
import os
import pathlib
import random
import re
import sqlite3
import sys
import time

from schemagate import Catalog
from schemagate.answer import UnsafeSQL, generate_sql
from schemagate.ai.providers import AnthropicProvider

BIRD = pathlib.Path(os.environ.get("BIRD_DIR", "E:/bird/dev_20240627"))
SAMPLE = int(os.environ.get("BIRD_SAMPLE", "200"))
TOP_K = int(os.environ.get("BIRD_TOP_K", "10"))
MODEL = os.environ.get("SG_MODEL", "claude-sonnet-5")
OUT = pathlib.Path(os.environ.get("BIRD_OUT", str(BIRD / "ontology_run.jsonl")))

_CLAUSE = re.compile(r"^\s*(?P<term>[^=;:]{2,80}?)\s+(?:refers?\s+to|means|stands\s+for|is\s+defined\s+as|=)\s+(?P<rule>.+?)\s*$", re.I)


def mcnemar_p(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def rows_of(db_path, sql, limit=2000):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        con.text_factory = lambda b: b.decode("utf-8", "replace")
        return con.execute(sql).fetchmany(limit)
    finally:
        con.close()


def same(a, b):
    if a is None or b is None:
        return False
    return {tuple(map(repr, r)) for r in a} == {tuple(map(repr, r)) for r in b}


def concepts_from_evidence(cat, evidence_list):
    """Concepts from free-text evidence: '<term> refers to <rule>' clauses, tables found from the rule."""
    cols = {}
    for q, d in cat._docs.items():
        for c in d.columns:
            cols.setdefault(c.name.lower(), set()).add(q)
        cols.setdefault(d.name.lower(), set()).add(q)
    # A glossary term has one meaning. Fixed before any test run, not tuned on results:
    #  - a term whose history gives it different rules is ambiguous, and dropped;
    #  - calculation words are phrasing, not business concepts ("percentage" got one
    #    question's formula and would mislead every other question using the word).
    generic = {"percentage", "percent", "average", "avg", "ratio", "rate", "total", "number", "count", "sum",
               "difference", "proportion", "highest", "lowest", "most", "least", "max", "min", "maximum",
               "minimum", "how many", "calculation", "calculate", "times", "increase", "decrease", "full name",
               "name", "id", "list"}
    rules = {}
    for ev in evidence_list:
        for clause in re.split(r";|\n", ev or ""):
            m = _CLAUSE.match(clause)
            if not m:
                continue
            term, rule = m.group("term").strip(" `'\""), m.group("rule").strip().rstrip(".")
            if len(term.split()) > 8 or not re.search(r"[A-Za-z]", term) or term.lower() in generic:
                continue
            rules.setdefault(term.lower(), (term, set()))[1].add(re.sub(r"\s+", " ", rule.lower()))
            rules[term.lower()] = (rules[term.lower()][0], rules[term.lower()][1], rule) \
                if len(rules[term.lower()]) == 2 else (rules[term.lower()][0], rules[term.lower()][1], rules[term.lower()][2])
    made = 0
    for _, (term, variants, rule) in rules.items():
        if len(variants) != 1:
            continue
        mentioned = {x.lower() for x in re.findall(r"`([^`]+)`", rule)}
        mentioned |= {x.lower() for x in re.findall(r"[A-Za-z_][\w]*", rule)}
        tables = sorted({q for name in mentioned for q in cols.get(name, ())})
        try:
            cat.concept(term, maps=tables[:3], definition=f"{term} refers to {rule}", source="bird-evidence")
            made += 1
        except (KeyError, ValueError):
            continue
    return made


def main():
    dev = json.loads((BIRD / "dev.json").read_text("utf-8"))
    by_db = {}
    for r in dev:
        by_db.setdefault(r["db_id"], []).append(r)
    history, test = {}, []
    for db, rs in by_db.items():
        history[db] = [r for i, r in enumerate(rs) if i % 2 == 0]
        test += [r for i, r in enumerate(rs) if i % 2 == 1]
    rnd = random.Random(20261004)
    picked = []
    for db in sorted(by_db):
        pool = [r for r in test if r["db_id"] == db]
        n = max(1, round(SAMPLE * len(pool) / len(test)))
        picked += rnd.sample(pool, min(n, len(pool)))
    rnd.shuffle(picked)

    plain, rich, paths, nconc = {}, {}, {}, {}
    for db in sorted({r["db_id"] for r in picked}):
        f = BIRD / "dev_databases" / db / f"{db}.sqlite"
        paths[db] = f
        a = Catalog().bootstrap(f"sqlite:///{f}"); a.infer_foreign_keys(); plain[db] = a.index()
        b = Catalog().bootstrap(f"sqlite:///{f}"); b.infer_foreign_keys()
        nconc[db] = concepts_from_evidence(b, [r.get("evidence") for r in history[db]])
        rich[db] = b.index()
    print(f"BIRD dev: test half {len(test)}, sample {len(picked)}, model {MODEL}, top_k {TOP_K}")
    print("concepts built from the history half's evidence: "
          + ", ".join(f"{db} {n}" for db, n in sorted(nconc.items())))

    prov = AnthropicProvider(model=MODEL)
    done = {}
    if OUT.exists():
        for line in OUT.read_text("utf-8").splitlines():
            e = json.loads(line); done[(e["question_id"], e["arm"])] = e
    fh = OUT.open("a", encoding="utf-8")
    t0 = time.time()

    def ask(r, arm):
        key = (r["question_id"], arm)
        if key in done:
            return done[key]
        cat = rich[r["db_id"]] if arm == "B" else plain[r["db_id"]]
        sel = cat.select(r["question"], top_k=TOP_K)
        e = {"question_id": r["question_id"], "db": r["db_id"], "arm": arm, "ok": False,
             "matched": [c.name for c, _ in cat.ontology.match(r["question"])], "meanings": len(sel.meanings)}
        try:
            sql = generate_sql(prov, r["question"], sel.prompt_fragment(), dialect="SQLite")
            e["sql"] = sql
            e["ok"] = same(rows_of(paths[r["db_id"]], sql), rows_of(paths[r["db_id"]], r["SQL"]))
        except UnsafeSQL:
            e["err"] = "refused"
        except Exception as ex:                                  # noqa: BLE001
            e["err"] = f"{type(ex).__name__}: {str(ex)[:120]}"
        fh.write(json.dumps(e) + "\n"); fh.flush()
        done[key] = e
        return e

    res = {"A": [], "A2": [], "B": []}
    matched = []
    for i, r in enumerate(picked, 1):
        for arm in ("A", "A2", "B"):
            res[arm].append(ask(r, arm)["ok"])
        matched.append(bool(done[(r["question_id"], "B")]["matched"]))
        if i % 20 == 0:
            n = len(res["A"])
            print(f"  {i:4}/{len(picked)}  A {sum(res['A'])/n:.3f}  A2 {sum(res['A2'])/n:.3f}  "
                  f"B {sum(res['B'])/n:.3f}   ({time.time()-t0:.0f}s)")

    def flips(x, y):
        return sum(1 for a, b in zip(x, y) if b and not a), sum(1 for a, b in zip(x, y) if a and not b)

    n = len(picked)
    print(f"\nBIRD dev test half, n={n}, {MODEL}, evidence withheld")
    for arm in ("A", "A2", "B"):
        print(f"  {arm:3} execution accuracy {sum(res[arm])}/{n} ({100*sum(res[arm])/n:.1f}%)")
    nb, nc = flips(res["A"], res["A2"])
    print(f"  noise floor A -> A2: +{nb} / -{nc}   p={mcnemar_p(nb, nc):.3f}")
    fb, fc = flips(res["A"], res["B"])
    print(f"  ontology   A -> B : +{fb} / -{fc}   p={mcnemar_p(fb, fc):.4f}")
    sub = [i for i, m in enumerate(matched) if m]
    if sub:
        a = [res["A"][i] for i in sub]; b = [res["B"][i] for i in sub]
        sb, sc = flips(a, b)
        print(f"  questions that used a concept: {len(sub)}   A {sum(a)} -> B {sum(b)}   +{sb} / -{sc}   "
              f"p={mcnemar_p(sb, sc):.4f}")


if __name__ == "__main__":
    main()
