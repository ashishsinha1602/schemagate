"""Concepts learned from a question history: does what one half of the questions taught help the other half?

Spider dev, all 166 Spider databases pooled into one catalog (876 tables, no database hint). For each
database, its questions are split by position: even = history (question + gold SQL), odd = test. Concepts
are learned from the history only (Catalog.learn_concepts, default thresholds) and the TEST questions are
scored with and without them: all gold tables of the question's own database present in the top k. Paired,
McNemar exact. Nothing about the test questions is seen while learning.

    python benchmarks/learn_concepts.py            # SCHEMAGATE_AUTO_EMBEDDER=0 for the base embedder
"""
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pandas as pd  # noqa: E402
from schemagate import Catalog  # noqa: E402
import spider  # noqa: E402


def mcnemar_p(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def pooled(schemas):
    cat = Catalog()
    for db, docs in schemas.items():
        for d in docs:
            cat.add(d)
    cat.index()
    return cat


def main(ks=(5, 10)):
    schemas = spider.parse_schemas(HERE / "spider_schema.json")
    dev = pd.read_parquet(HERE / "spider_dev.parquet")
    history, test, seen = [], [], {}
    for _, r in dev.iterrows():
        if r.db_id not in schemas:
            continue
        gold = spider.gold_tables(r["query"])
        if not gold:
            continue
        i = seen.get(r.db_id, 0); seen[r.db_id] = i + 1
        qualified = [f"{r.db_id}.{t}" for t in gold]
        (history if i % 2 == 0 else test).append((r.question, qualified, r.db_id, gold))

    base = pooled(schemas)
    learned = pooled(schemas)
    sugg = learned.learn_concepts([(q, tabs) for q, tabs, _, _ in history], apply=True)
    print(f"embedder: {base.embedder.name}   history {len(history)} questions, test {len(test)}")
    print(f"learned {len(sugg)} concepts; strongest: "
          + "; ".join(f"{s['phrase']!r}->{s['object']} ({s['support']}, {s['precision']})" for s in sugg[:6]))
    for k in ks:
        a = [];  b = []
        for q, _, db, gold in test:
            for cat, out in ((base, a), (learned, b)):
                picked = {h.doc.name.lower() for h in cat.select(q, top_k=k).hits if h.doc.schema == db}
                out.append(gold <= picked)
        fixed = sum(1 for x, y in zip(a, b) if y and not x)
        broken = sum(1 for x, y in zip(a, b) if x and not y)
        n = len(test)
        print(f"top_k={k:2}: without {sum(a)}/{n} ({100*sum(a)/n:.1f}%)   with learned {sum(b)}/{n} "
              f"({100*sum(b)/n:.1f}%)   fixed {fixed} broken {broken}   McNemar p={mcnemar_p(fixed, broken):.4f}")


if __name__ == "__main__":
    main()
