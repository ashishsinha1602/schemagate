"""Spider, pooled: how many misses are a missing *bridge* table between two tables that were found.

A bridge miss: the selection holds two gold tables of the right database, and the gold table it lacks lies
on a foreign-key path between them. That is the gap ranking cannot close -- `order_line` between `orders`
and `products` shares no words with "which customers bought red shoes" -- and the one a schema graph can.

Scored per database (the selection's tables must belong to the question's database, so a same-named table
in another database never counts as a hit). Measured 2026-10-04 on the hashed embedder: 2 of 266 misses at
top_k=5 and 5 of 148 at top_k=10 are bridge misses -- one-step FK expansion already brings most bridges in,
so join-path completion was not built. Re-run this on a real warehouse before building it.

    python benchmarks/join_paths.py            # hashed embedder: SCHEMAGATE_AUTO_EMBEDDER=0
"""
import pathlib
import sys
from collections import deque

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pandas as pd  # noqa: E402
from schemagate import Catalog  # noqa: E402
import spider  # noqa: E402


def graph(docs):
    g = {}
    names = {d.name.lower() for d in docs}
    for d in docs:
        a = d.name.lower()
        g.setdefault(a, set())
        for fk in d.foreign_keys:
            b = fk.ref_table.lower()
            if b in names and b != a:
                g[a].add(b); g.setdefault(b, set()).add(a)
    return g


def on_path(g, src, dst, node, limit=3):
    """Is `node` on some shortest src->dst path of at most `limit` edges?"""
    def bfs(s):
        dist = {s: 0}; q = deque([s])
        while q:
            u = q.popleft()
            for v in g.get(u, ()):
                if v not in dist:
                    dist[v] = dist[u] + 1; q.append(v)
        return dist
    ds, dd = bfs(src), bfs(dst)
    if dst not in ds or ds[dst] > limit:
        return False
    return node in ds and node in dd and ds[node] + dd[node] == ds[dst]


def run(k=5):
    schemas = spider.parse_schemas(HERE / "spider_schema.json")
    dev = pd.read_parquet(HERE / "spider_dev.parquet")
    pooled = Catalog()
    for db, docs in schemas.items():
        for d in docs:
            pooled.add(d)
    pooled.index()
    results, bridge_misses = [], 0
    for _, r in dev.iterrows():
        db, gold = r.db_id, spider.gold_tables(r["query"])
        if db not in schemas or not gold:
            continue
        sel = pooled.select(r.question, top_k=k)
        picked = {h.doc.name.lower() for h in sel.hits if h.doc.schema == db}
        ok = gold <= picked
        results.append(ok)
        if not ok:
            g = graph(schemas[db])
            have = sorted(gold & picked)
            for m in gold - picked:
                if any(on_path(g, a, b, m) for i, a in enumerate(have) for b in have[i + 1:]):
                    bridge_misses += 1
                    break
    return results, bridge_misses


if __name__ == "__main__":
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    base, bridges = run(k=k)
    print(f"top_k={k}  questions {len(base)}  all gold tables present: {sum(base)} ({100*sum(base)/len(base):.1f}%)")
    print(f"  misses {len(base) - sum(base)}, of which a missing BRIDGE between two found gold tables: {bridges}")
