# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Head-to-head table selection, no model calls: full schema, BM25, embeddings, schemagate.

    pip install sentence-transformers tiktoken sqlglot
    python benchmarks/token_savings/compare.py --spider2 <spider2-lite dir> --bird <BIRD dev dir>

Same questions, same catalog (schemagate's, with partitions folded, so the baselines get that
for free), same number of tables. The embedding baseline is `all-MiniLM-L6-v2`, the default way
LangChain, LlamaIndex and Vanna pick tables from a vector store; with sentence-transformers
installed, schemagate uses the same model, so the difference is ranking and join expansion.
Scored with measure.py's covers() and cl100k tokens of the DDL each method would send.
"""
import argparse
import collections
import json
import math
import pathlib
import re
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from measure import covers, gold_tables, tokens, warehouse_catalog  # noqa: E402

from schemagate import Catalog  # noqa: E402

WORD = re.compile(r"[a-z0-9]+")
METHODS = ("full schema", "BM25", "embeddings (MiniLM)", "schemagate")


def words(text):
    return WORD.findall(text.lower().replace("_", " "))


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.tf = [collections.Counter(words(d)) for d in docs]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.len) / max(1, len(self.len))
        df = collections.Counter(w for t in self.tf for w in t)
        self.idf = {w: math.log(1 + (len(docs) - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self.k1, self.b = k1, b

    def rank(self, query):
        q = words(query)
        scores = []
        for i, t in enumerate(self.tf):
            norm = self.k1 * (1 - self.b + self.b * self.len[i] / self.avg)
            scores.append(sum(self.idf[w] * t[w] * (self.k1 + 1) / (t[w] + norm) for w in q if w in t))
        return sorted(range(len(scores)), key=lambda i: -scores[i])


_model = None


def encode(texts):
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
    return _model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)


def run(name, by_db, top_k, make_catalog):
    res = collections.defaultdict(list)
    for db, qs in sorted(by_db.items()):
        cat = make_catalog(db)
        docs = list(cat._docs.values())
        ddl = [d.render_ddl() for d in docs]
        dnames = [d.name.lower() for d in docs]
        names = set(dnames)
        full = tokens("\n\n".join(d.render_ddl(max_columns=10**6) for d in docs))
        bm = BM25(ddl)
        emb = encode(ddl)
        for q in qs:
            need = gold_tables(q["sql"], q.get("dialect", "sqlite"))
            if not need:
                continue
            res["full schema"].append((covers(need, names, names), full))
            order = bm.rank(q["question"])[:top_k]
            res["BM25"].append((covers(need, {dnames[i] for i in order}, names),
                                tokens("\n\n".join(ddl[i] for i in order))))
            sims = emb @ encode([q["question"]])[0]
            order = sorted(range(len(docs)), key=lambda i: -sims[i])[:top_k]
            res["embeddings (MiniLM)"].append((covers(need, {dnames[i] for i in order}, names),
                                               tokens("\n\n".join(ddl[i] for i in order))))
            sel = cat.select(q["question"], top_k=top_k)
            got = {n.split(".")[-1].lower() for n in sel.table_names}
            res["schemagate"].append((covers(need, got, names), tokens(sel.prompt_fragment())))
    print(f"\n{name}  (top_k={top_k}, {len(res['schemagate'])} questions with gold tables)")
    print(f"  {'method':22} {'all gold tables':>16} {'mean tokens':>12}")
    out = {"benchmark": name, "top_k": top_k, "questions": len(res["schemagate"]), "methods": {}}
    for m in METHODS:
        rows = res[m]
        cov, mean = sum(h for h, _ in rows) / len(rows), statistics.mean(t for _, t in rows)
        print(f"  {m:22} {cov:>15.1%} {mean:>12,.0f}")
        out["methods"][m] = {"gold_tables_all_selected": round(cov, 4), "mean_tokens": round(mean)}
    sg = [h for h, _ in res["schemagate"]]
    for m in ("BM25", "embeddings (MiniLM)"):
        other = [h for h, _ in res[m]]
        wins = sum(1 for a, b in zip(sg, other) if a and not b)
        losses = sum(1 for a, b in zip(sg, other) if b and not a)
        print(f"  paired vs {m}: schemagate only {wins}, {m} only {losses}")
        out["methods"][m]["paired_schemagate_only"], out["methods"][m]["paired_other_only"] = wins, losses
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spider2", help="spider2-lite folder (spider2-lite.jsonl, resource/databases)")
    ap.add_argument("--bird", help="BIRD dev folder (dev.json, dev_databases/)")
    ap.add_argument("--out", default=str(pathlib.Path(__file__).with_name("compare_results.json")))
    a = ap.parse_args()
    results = []
    if a.spider2:
        root = pathlib.Path(a.spider2)
        dirs = {}
        for eng in ("bigquery", "snowflake"):
            for d in (root / "resource" / "databases" / eng).iterdir():
                if d.is_dir():
                    dirs.setdefault(d.name, (eng, d))
        gold = root / "evaluation_suite" / "gold" / "sql"
        by_db = collections.defaultdict(list)
        for line in (root / "spider2-lite.jsonl").read_text("utf-8").splitlines():
            q = json.loads(line)
            if q["instance_id"].startswith("local") or q["db"] not in dirs:
                continue
            g = gold / f"{q['instance_id']}.sql"
            if g.exists():
                by_db[q["db"]].append({"question": q["question"], "sql": g.read_text("utf-8"),
                                       "dialect": "bigquery" if dirs[q["db"]][0] == "bigquery" else "snowflake"})
        results.append(run("Spider 2.0-lite, BigQuery and Snowflake", by_db, 12,
                           lambda db: warehouse_catalog(dirs[db][1])))
    if a.bird:
        root = pathlib.Path(a.bird)
        by_db = collections.defaultdict(list)
        for q in json.loads((root / "dev.json").read_text("utf-8")):
            by_db[q["db_id"]].append({"question": q["question"], "sql": q["SQL"]})
        results.append(run("BIRD dev", by_db, 6, lambda db: Catalog(name=db).bootstrap(
            f"sqlite:///{(root / 'dev_databases' / db / f'{db}.sqlite').as_posix()}")))
    pathlib.Path(a.out).write_text(json.dumps(results, indent=2) + "\n", "utf-8")


if __name__ == "__main__":
    main()
