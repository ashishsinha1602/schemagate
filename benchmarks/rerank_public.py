# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Does the LLM reranker help on the public benchmarks? Spider and BIRD, pooled, paired.

rerank_eval.py measured the reranker on the 58 questions of the six schemas in this
repository, which are invented. This asks the same question of Spider dev and BIRD dev in the
POOLED setting -- every database in one catalogue, no hint which one a question belongs to --
because that is the setting where the order inside the shortlist decides the answer.

Each question is scored twice on the same catalogue, embedder and top_k: once on the maths
order (RRF of the lexical, vector, name and prose rankings), once with a model reordering the
top `candidates`. Metric: all gold tables in the top_k. Paired, so the report is discordant
pairs and McNemar's exact test. Every model reply is logged to a JSONL file, so a run resumes.

    BIRD_DIR=E:/bird/dev_20240627 SG_MODEL=claude-haiku-5-5 python benchmarks/rerank_public.py [spider|bird ...]
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import math
import os
import pathlib
import sys
import tempfile
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

MODEL = os.environ.get("SG_MODEL", "claude-haiku-5-5")
TOP_K = int(os.environ.get("SG_TOP_K", "5"))
CANDIDATES = int(os.environ.get("SG_CANDIDATES", "20"))
WORKERS = int(os.environ.get("SG_WORKERS", "8"))
OUT = pathlib.Path(os.environ.get("SG_OUT", str(pathlib.Path(tempfile.gettempdir()) / "rerank_public.jsonl")))


def mcnemar_p(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def spider_cases():
    import pandas as pd
    import spider
    schemas = spider.parse_schemas(HERE / "spider_schema.json")
    dev = pd.read_parquet(HERE / "spider_dev.parquet")
    docs = [d for ds in schemas.values() for d in ds]
    cases = [(r.question, spider.gold_tables(r["query"])) for _, r in dev.iterrows()]
    return docs, [(q, g) for q, g in cases if g]


def bird_cases():
    import bird
    root = pathlib.Path(os.environ.get("BIRD_DIR", str(HERE / "dev_20240627")))   # as bird_ontology.py
    bird.DEV, bird.TABLES = root / "dev.json", root / "dev_tables.json"
    specs = {s["db_id"]: s for s in json.loads(bird.TABLES.read_text("utf-8"))}
    per_db = {db: bird.build_docs(s) for db, s in specs.items()}
    known = {db: {d.name.lower() for d in ds} for db, ds in per_db.items()}
    cases = [(r["question"], bird.gold_tables(r["SQL"], known.get(r["db_id"], set())))
             for r in json.loads(bird.DEV.read_text("utf-8"))]
    return [d for ds in per_db.values() for d in ds], [(q, g) for q, g in cases if g]


def run(name, docs, cases, provider, log):
    from schemagate import Catalog
    cat = Catalog()
    for d in docs:
        cat.add(d)
    cat.index()

    def picked(sel):
        return {n.split(".")[-1].lower() for n in sel.table_names}

    done = {}
    if OUT.exists():
        for line in OUT.read_text("utf-8").splitlines():
            e = json.loads(line)
            if e["set"] == name and e["model"] == MODEL:
                done[e["i"]] = e
    lock = threading.Lock()

    def one(i):
        q, gold = cases[i]
        if i in done:
            return done[i]
        base = gold <= picked(cat.select(q, top_k=TOP_K))
        calls = []

        class Logged:
            def complete(self, system, prompt, max_tokens=1024):
                r = provider.complete(system, prompt, max_tokens=max_tokens)
                calls.append(r)
                return r
        sel = cat.select(q, top_k=TOP_K, reranker=Logged(), rerank_candidates=CANDIDATES)
        e = {"set": name, "i": i, "model": MODEL, "base": base, "rerank": gold <= picked(sel),
             "model_answered": bool(calls), "reply": (calls[-1] if calls else "")[:80]}
        with lock:
            log.write(json.dumps(e) + "\n")
            log.flush()
        return e

    t0 = time.time()
    with cf.ThreadPoolExecutor(WORKERS) as pool:
        res = list(pool.map(one, range(len(cases))))
    n = len(res)
    base = sum(r["base"] for r in res)
    rr = sum(r["rerank"] for r in res)
    b = sum(1 for r in res if r["rerank"] and not r["base"])
    c = sum(1 for r in res if r["base"] and not r["rerank"])
    answered = sum(r["model_answered"] for r in res)
    print(f"{name:7} pooled {len(cat)} tables, n={n}, top_k={TOP_K}, candidates={CANDIDATES}, "
          f"{MODEL} ({time.time()-t0:.0f}s)")
    print(f"   maths order   {base}/{n} ({100*base/n:.1f}%)")
    print(f"   reranked      {rr}/{n} ({100*rr/n:.1f}%)   +{b} / -{c}   McNemar p={mcnemar_p(b, c):.4g}")
    print(f"   model answered {answered}/{n} calls (the rest fell back to the maths order)")
    return res


def main():
    from schemagate.ai.providers import AnthropicProvider
    provider = AnthropicProvider(model=MODEL)
    sets = sys.argv[1:] or ["spider", "bird"]
    with OUT.open("a", encoding="utf-8") as log:
        for name in sets:
            docs, cases = {"spider": spider_cases, "bird": bird_cases}[name]()
            run(name, docs, cases, provider, log)
    print(f"per-question log: {OUT}")


if __name__ == "__main__":
    main()
