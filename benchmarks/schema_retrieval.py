"""schemagate on Snowflake's SQL-Schema-Retrieval benchmark, table level.

The benchmark (Zeng, Yu, Mehta, Zhao, Samdani, "Finding the Right Tables and
Columns", arXiv:2607.13311; data at huggingface.co/datasets/Snowflake/SQL-Schema-Retrieval)
recasts five text-to-SQL sets as retrieval: given a question, find the tables
its gold SQL reads, ranking only the one database's schema. Metrics are
recall@10 and nDCG@10. Five table-level subsets: Spider, BIRD, BEAVER,
LiveSQLBench and LiveSQLBench-Large -- the last one 18 databases of 971 tables
whose column names are codes (`questregistry`, `climtune`), which is where a
lexical retriever goes wrong and where this file earned its keep.

What schemagate sees per table is what its catalog would hold: the name, the
columns with types and keys, foreign keys, column comments (the benchmark's
"Column Meanings", JSON sub-fields folded into their column), and the sample
values for the markdown-table subsets. No sample rows otherwise, no DDL text.

    python benchmarks/schema_retrieval.py                       # all five, hashed embedder
    python benchmarks/schema_retrieval.py --embedder st:all-MiniLM-L6-v2
    python benchmarks/schema_retrieval.py --subset livesqlbench_large_table --misses out.jsonl

Downloads the data (about 90 MB) into benchmarks/data/sql_schema_retrieval on
first run; `pip install huggingface_hub` for that. No model is called unless
`--embedder st:...` names a sentence-transformers model.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import time
from collections import Counter, defaultdict

from schemagate import Catalog, Column, ForeignKey, ObjectDoc

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data" / "sql_schema_retrieval"
SUBSETS = ("spider", "bird", "beaver", "livesqlbench_table", "livesqlbench_large_table")

COL_LINE = re.compile(r'^\s*"?([^"\s,]+)"?\s+([A-Za-z][\w ]*?(?:\([^)]*\))?)\s*(NOT NULL|NULL)?\s*,?\s*$')
PK_LINE = re.compile(r'PRIMARY KEY\s*\(([^)]*)\)', re.I)
FK_LINE = re.compile(r'FOREIGN KEY\s*\(([^)]*)\)\s*REFERENCES\s+"?([\w.]+)"?\s*\(([^)]*)\)', re.I)
MEANING = re.compile(r'^- ([^:]+):\s*(.*)$')


def download() -> pathlib.Path:
    if all((DATA / s / "corpus.jsonl").is_file() for s in SUBSETS):
        return DATA
    from huggingface_hub import snapshot_download
    snapshot_download("Snowflake/SQL-Schema-Retrieval", repo_type="dataset", local_dir=str(DATA),
                      allow_patterns=["*/corpus.jsonl", "*/queries.jsonl", "*/qrels/test.tsv"])
    return DATA


def _idents(s: str):
    return [x.strip().strip('"') for x in s.split(",") if x.strip()]


def parse_doc(rec: dict) -> ObjectDoc:
    db, _, table = rec["_id"].partition("__")
    text = rec["text"]
    m = re.search(r"CREATE TABLE[^(]*\((.*?)\n\);", text, re.S)
    body = m.group(1) if m else ""
    pks, fks, cols = set(), [], []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        pk = PK_LINE.search(line)
        if pk:
            pks.update(x.lower() for x in _idents(pk.group(1)))
            continue
        fk = FK_LINE.search(line)
        if fk:
            fks.append(ForeignKey(_idents(fk.group(1)), fk.group(2).split(".")[-1], _idents(fk.group(3))))
            continue
        if line.upper().startswith(("UNIQUE", "CHECK", "CONSTRAINT")):
            continue
        cm = COL_LINE.match(line)
        if cm:
            cols.append(Column(cm.group(1), cm.group(2).strip().upper(),
                               (cm.group(3) or "NULL").upper() != "NOT NULL"))
    for c in cols:
        c.pk = c.name.lower() in pks
    meanings: dict = {}
    mm = re.search(r"Column Meanings:\n(.*)$", text, re.S)
    if mm:
        for line in mm.group(1).splitlines():
            x = MEANING.match(line.strip())
            if not x:
                continue
            name, meaning = x.group(1).strip().strip('"'), x.group(2).strip()
            meaning = re.sub(r"^[A-Z][\w() ,]*\.\s*", "", meaning, count=1)      # the leading type word
            if "." in name:                                                     # a JSON sub-field
                parent, _, sub = name.partition(".")
                if parent.lower() in meanings:
                    meanings[parent.lower()] += f" {sub.replace('_', ' ')}: {meaning}"
                continue
            meanings[name.lower()] = meaning
    for c in cols:
        if c.name.lower() in meanings:
            c.comment = meanings[c.name.lower()]
    if not cols:                       # markdown table: header row, then sample rows
        rows = [[p.strip() for p in line.strip().strip("|").split("|")]
                for line in text.splitlines() if line.strip().startswith("|")]
        rows = [r for r in rows if r and not all(set(c) <= set("-: ") for c in r)]
        if rows:
            cols = [Column(h, "TEXT") for h in rows[0] if h]
            for j, c in enumerate(cols):
                seen: list = []
                for r in rows[1:]:
                    if j < len(r) and r[j] not in ("None", "") and r[j] not in seen:
                        seen.append(r[j])
                if seen and len(seen) <= 10:
                    c.values = seen
    return ObjectDoc(name=table, schema=db, kind="TABLE", columns=cols, foreign_keys=fks)


def load(subset_dir: pathlib.Path):
    docs, by_db = {}, defaultdict(list)
    for line in (subset_dir / "corpus.jsonl").open(encoding="utf-8"):
        rec = json.loads(line)
        d = parse_doc(rec)
        docs[rec["_id"]] = d
        by_db[d.schema].append(d)
    queries = {}
    for line in (subset_dir / "queries.jsonl").open(encoding="utf-8"):
        rec = json.loads(line)
        queries[rec["_id"]] = rec["text"]
    qrels = defaultdict(set)
    with (subset_dir / "qrels" / "test.tsv").open(encoding="utf-8") as f:
        next(f)
        for line in f:
            q, c, s = line.rstrip("\n").split("\t")
            if float(s) > 0:
                qrels[q].add(c)
    return docs, by_db, queries, qrels


def make_embedder(spec: str):
    if spec == "hashed":
        from schemagate.embedder import HashingEmbedder
        return HashingEmbedder()
    if spec.startswith("st:"):
        from schemagate.embedders.hf import SentenceTransformerEmbedder
        return SentenceTransformerEmbedder(spec[3:])
    raise SystemExit(f"unknown embedder {spec!r}: hashed or st:<sentence-transformers model>")


def ndcg(ranked, gold, k):
    dcg = sum(1.0 / math.log2(i + 2) for i, c in enumerate(ranked[:k]) if c in gold)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(gold), k)))
    return dcg / ideal if ideal else 0.0


def run(subset: str, embedder, k: int = 10, fk: bool = False, misses=None, infer: bool = False,
        join_weight=None, join_window=None, log_loo: bool = False, **select_kw):
    """recall@k, nDCG@k, n, seconds, and a dict of extras: `all` (questions with every gold
    table in the top k) and, over the whole selection including any FK expansion,
    `sel_recall`, `sel_precision` and `sel_size`."""
    docs, by_db, queries, qrels = load(DATA / subset)
    log_pairs = None
    if log_loo:
        # A stand-in query log: the tables every *other* question of the database reads,
        # as pairs read together. Leave-one-out, so a question never sees its own answer.
        from schemagate.querylog import LogFacts
        log_pairs = defaultdict(Counter)
        for g in qrels.values():
            names = sorted({c.partition("__")[2] for c in g})
            db0 = next(iter(g)).partition("__")[0]
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    log_pairs[db0][frozenset((f"{db0}.{a}", f"{db0}.{b}"))] += 1
    cats, n = {}, 0
    rec_sum = ndcg_sum = all_sum = srec = sprec = ssize = 0.0
    t0 = time.time()
    for qid, text in queries.items():
        gold = qrels.get(qid)
        if not gold:
            continue
        db = next(iter(gold)).partition("__")[0]
        if db not in cats:
            cat = Catalog(embedder=embedder, name=db)
            cat.add_all(by_db[db])
            if infer:
                cat.infer_foreign_keys()
            if join_weight is not None:
                cat.join_weight = join_weight
            if join_window is not None:
                cat.join_window = join_window
            cats[db] = cat.index()
        if log_pairs is not None:
            names = sorted({c.partition("__")[2] for c in gold})
            own = Counter(frozenset((f"{db}.{a}", f"{db}.{b}"))
                          for i, a in enumerate(names) for b in names[i + 1:])
            cats[db].query_log = LogFacts(together=log_pairs[db] - own)
        sel = cats[db].select(text, top_k=k, expand_fks=fk, **select_kw)
        every = [f"{sc.doc.schema}__{sc.doc.name}" for sc in sel.hits]
        ranked = every[:k]
        r = len(gold & set(ranked)) / len(gold)
        rec_sum += r
        all_sum += r == 1.0
        ndcg_sum += ndcg(ranked, gold, k)
        srec += len(gold & set(every)) / len(gold)
        sprec += len(gold & set(every)) / max(1, len(every))
        ssize += len(every)
        n += 1
        if misses is not None and r < 1.0:
            misses.append({"qid": qid, "db": db, "question": text, "gold": sorted(gold),
                           "missed": sorted(gold - set(ranked)), "ranked": ranked})
    extra = {"all": 100 * all_sum / n, "sel_recall": 100 * srec / n,
             "sel_precision": 100 * sprec / n, "sel_size": ssize / n}
    return 100 * rec_sum / n, 100 * ndcg_sum / n, n, time.time() - t0, extra


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--subset", action="append", choices=SUBSETS, help="default: all five")
    ap.add_argument("--embedder", default="hashed", help="hashed (default) or st:<model>")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--fk", action="store_true", help="expand foreign keys (off: pure ranking)")
    ap.add_argument("--vector-weight", type=float, default=1.0)
    ap.add_argument("--lexical-weight", type=float, default=None, help="default: the library's")
    ap.add_argument("--misses", help="write the questions that missed a gold table here (JSONL)")
    ap.add_argument("--infer", action="store_true",
                    help="infer foreign keys from column names first, as Catalog.introspect does")
    ap.add_argument("--join-weight", type=float, default=None,
                    help="Catalog.join_weight (default: the library's; 0 turns the join graph's vote off)")
    ap.add_argument("--join-window", type=int, default=None, help="Catalog.join_window")
    ap.add_argument("--log-loo", action="store_true",
                    help="give each question a stand-in query log: the table pairs the database's "
                         "other questions read together (leave-one-out)")
    args = ap.parse_args()
    download()
    embedder = make_embedder(args.embedder)
    kw = {"vector_weight": args.vector_weight}
    if args.lexical_weight is not None:
        kw["lexical_weight"] = args.lexical_weight
    print(f"embedder={args.embedder} k={args.k} fk={args.fk} infer={args.infer} "
          f"join_weight={args.join_weight} join_window={args.join_window} log_loo={args.log_loo}")
    print(f"{'subset':26s} {'n':>5s} {'recall@k':>9s} {'nDCG@k':>7s} {'all@k':>6s}"
          f" {'sel_rec':>8s} {'sel_prec':>8s} {'sel_n':>6s}")
    misses = [] if args.misses else None
    for s in args.subset or SUBSETS:
        r, d, n, secs, x = run(s, embedder, args.k, args.fk, misses, infer=args.infer,
                               join_weight=args.join_weight, join_window=args.join_window,
                               log_loo=args.log_loo, **kw)
        print(f"{s:26s} {n:5d} {r:9.1f} {d:7.1f} {x['all']:6.1f} {x['sel_recall']:8.1f}"
              f" {x['sel_precision']:8.1f} {x['sel_size']:6.1f}   ({secs:.0f}s)", flush=True)
    if misses is not None:
        with open(args.misses, "w", encoding="utf-8") as f:
            for m in misses:
                f.write(json.dumps(m) + "\n")
        print(f"{len(misses)} misses -> {args.misses}")


if __name__ == "__main__":
    main()
