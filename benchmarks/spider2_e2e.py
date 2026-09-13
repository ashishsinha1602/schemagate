"""schemagate end to end on Spider 2.0-lite (BigQuery): execution accuracy.

Spider 2.0 is the benchmark built for this problem -- real warehouses, a
median of fifteen tables per database and a largest of 785, against Spider
1.0's median of three. The retrieval numbers are already in BENCHMARKS.md;
this runs the whole pipeline and scores what the benchmark scores: does the
SQL return the rows the reference SQL returns.

Only the `bq` questions with public gold SQL are usable -- Snowflake needs a
separate account, and the rest of the set is held out.

Costs money in principle: BigQuery bills by bytes scanned. Every table here
is a public dataset and the free tier is a terabyte a month, so a run of this
size is comfortably inside it -- but `--dry-run` reports the bytes before
anything executes, because a benchmark that quietly bills someone is a bad
benchmark.
"""
import json
import os
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent

from google.cloud import bigquery                       # noqa: E402
from schemagate import Catalog, Column, ObjectDoc       # noqa: E402
from schemagate.answer import UnsafeSQL, generate_sql   # noqa: E402
from schemagate.ai.providers import AnthropicProvider   # noqa: E402

ROOT = HERE / "Spider2" / "spider2-lite"
DBS = ROOT / "resource" / "databases" / "bigquery"
GOLD = ROOT / "evaluation_suite" / "gold" / "sql"
QUESTIONS = HERE / "spider2_lite.jsonl"

LIMIT = int(os.environ.get("SPIDER2_N", "25"))
TOP_K = int(os.environ.get("SPIDER2_TOP_K", "12"))
MODEL = os.environ.get("SG_MODEL", "claude-opus-5")
MAX_GB = float(os.environ.get("SPIDER2_MAX_GB", "5"))


def load_db(path):
    docs = []
    for f in path.rglob("*.json"):
        try:
            d = json.loads(f.read_text("utf-8"))
        except Exception:                                # noqa: BLE001
            continue
        names = d.get("column_names") or []
        types = d.get("column_types") or []
        cols = [Column(str(n), str(types[i] if i < len(types) else "STRING"),
                       True, None, False) for i, n in enumerate(names)]
        if not cols:
            continue
        desc = d.get("description")
        if isinstance(desc, (list, tuple)):
            desc = " ".join(str(x) for x in desc)
        # The fully-qualified name is what BigQuery SQL must say, so it is what
        # the model has to be shown.
        docs.append(ObjectDoc(name=str(d.get("table_fullname") or d.get("table_name") or f.stem),
                              schema=None, kind="TABLE",
                              description=(str(desc)[:400] if desc else None),
                              columns=cols))
    return docs


def rows_of(client, sql, cap_gb=MAX_GB):
    dry = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True,
                                                               use_query_cache=False))
    gb = (dry.total_bytes_processed or 0) / 1e9
    if gb > cap_gb:
        raise RuntimeError("would scan %.1f GB (cap %.1f)" % (gb, cap_gb))
    job = client.query(sql)
    return [tuple(r.values()) for r in job.result(max_results=1000)], gb


def same(a, b):
    return {tuple(map(repr, r)) for r in a} == {tuple(map(repr, r)) for r in b}


def main():
    client = bigquery.Client()
    rows = [json.loads(l) for l in QUESTIONS.read_text("utf-8").splitlines() if l.strip()]
    have = {p.stem for p in GOLD.glob("*.sql")}
    dirs = {d.name: d for d in DBS.iterdir() if d.is_dir()}

    cases = [r for r in rows
             if r["instance_id"].startswith("bq")
             and r["instance_id"] in have and r["db"] in dirs][:LIMIT]
    print("Spider 2.0-lite (BigQuery): %d questions, model %s, top_k %d"
          % (len(cases), MODEL, TOP_K))

    cats = {}
    for db in sorted({c["db"] for c in cases}):
        docs = load_db(dirs[db])
        cat = Catalog()
        for d in docs:
            cat.add(d)
        cats[db] = (cat.index(), len(docs))
    print("catalogs built: " + ", ".join("%s(%d)" % (k, v[1]) for k, v in list(cats.items())[:6]) + " ...\n")

    prov = AnthropicProvider(model=MODEL)
    wrote = ran = ok = 0
    scanned = 0.0
    t0 = time.time()
    for i, c in enumerate(cases, 1):
        cat, ntab = cats[c["db"]]
        q = c["question"]
        if (c.get("external_knowledge") or "").strip():
            q += "  (see: %s)" % c["external_knowledge"]
        try:
            sql = generate_sql(prov, q, cat.select(q, top_k=TOP_K).prompt_fragment(),
                               dialect="BigQuery Standard SQL")
            wrote += 1
        except UnsafeSQL as e:
            print("  %2d/%d %-22s REFUSED %s" % (i, len(cases), c["db"][:22], str(e)[:38]))
            continue
        except Exception as e:                           # noqa: BLE001
            print("  %2d/%d %-22s ERROR %s" % (i, len(cases), c["db"][:22], type(e).__name__))
            continue
        try:
            got, gb = rows_of(client, sql)
            ran += 1
            scanned += gb
        except Exception as e:                           # noqa: BLE001
            print("  %2d/%d %-22s SQL FAILED %s" % (i, len(cases), c["db"][:22],
                                                    str(e).splitlines()[0][:44]))
            continue
        try:
            want, gb2 = rows_of(client, (GOLD / (c["instance_id"] + ".sql")).read_text("utf-8"))
            scanned += gb2
        except Exception:                                # noqa: BLE001
            print("  %2d/%d %-22s (gold itself failed)" % (i, len(cases), c["db"][:22]))
            continue
        hit = same(got, want)
        ok += hit
        print("  %2d/%d %-22s %s  %d rows, %.2f GB" % (
            i, len(cases), c["db"][:22], "correct" if hit else "wrong  ", len(got), gb))

    n = len(cases)
    print("\nSpider 2.0-lite (BigQuery), n=%d, %s" % (n, MODEL))
    print("  SQL written            %d/%d" % (wrote, n))
    print("  executed on BigQuery   %d/%d" % (ran, n))
    print("  EXECUTION ACCURACY     %d/%d (%.1f%%)" % (ok, n, 100 * ok / n if n else 0))
    print("  bytes scanned          %.1f GB   (%.0fs)" % (scanned, time.time() - t0))


if __name__ == "__main__":
    main()
