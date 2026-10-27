# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Prompt tokens with and without schemagate, on public benchmarks.

    python benchmarks/token_savings/measure.py --bird <BIRD dev dir> --spider2 <spider2-lite dir> \
        --spider2-dbs <dir of local SQLite files>

No model is called. For every question it counts the tokens of the schema a
text-to-SQL prompt would carry, two ways: every table in the database (what
you send without selection), and what ``Catalog.select(question, top_k)``
returns (which caps a wide table at 40 columns, as every schemagate prompt does). For BIRD it also reports
how often the tables the gold SQL reads were all in the selection, so the
savings are not bought by dropping tables the query needs.

Counts use tiktoken's cl100k_base; other tokenizers differ by a few percent,
and the ratio barely moves.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

import sqlglot
import tiktoken

from schemagate import Catalog, Column, ObjectDoc

ENC = tiktoken.get_encoding("cl100k_base")


def tokens(text: str) -> int:
    return len(ENC.encode(text))


def gold_tables(sql: str, dialect: str = "sqlite") -> set:
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return set()
    ctes = {c.alias_or_name.lower() for c in tree.find_all(sqlglot.exp.CTE)}
    return {t.name.lower() for t in tree.find_all(sqlglot.exp.Table) if t.name and t.name.lower() not in ctes}


def warehouse_catalog(path: pathlib.Path) -> Catalog:
    """One Spider 2.0 BigQuery/Snowflake database: a folder of one JSON file per table.

    Columns are the flattened list when the table has nested fields (what the gold SQL names).
    A table written one file per day is one table, as ``bootstrap`` makes it for every user."""
    cat = Catalog(name=path.name)
    for f in path.rglob("*.json"):
        try:
            d = json.loads(f.read_text("utf-8"))
        except Exception:
            continue
        names = d.get("nested_column_names") or d.get("column_names") or []
        types = (d.get("nested_column_types") if d.get("nested_column_names") else d.get("column_types")) or []
        cols = [Column(str(n), str(types[i] if i < len(types) else "TEXT"), True, None, False)
                for i, n in enumerate(names)]
        if cols:
            cat.add(ObjectDoc(name=str(d.get("table_name") or f.stem), schema=path.name, kind="TABLE", columns=cols))
    cat.collapse_partitions()
    return cat.index()


def measure(name, by_db, top_k, db_path, catalog=None):
    rows = []
    for db, qs in sorted(by_db.items()):
        cat = catalog(db) if catalog else Catalog(name=db).bootstrap(f"sqlite:///{db_path(db).as_posix()}")
        # every column of every table: what a prompt carries with no selection at all
        full = tokens("\n\n".join(d.render_ddl(max_columns=10**6) for d in cat._docs.values()))
        for q in qs:
            sel = cat.select(q["question"], top_k=top_k)
            got = {n.split(".")[-1].lower() for n in sel.table_names}
            need = gold_tables(q["sql"], q.get("dialect", "sqlite")) if q.get("sql") else set()
            rows.append({"db": db, "objects": len(cat._docs), "full": full,
                         "selected": tokens(sel.prompt_fragment()), "tables_sent": len(got),
                         "gold_covered": (need <= got) if need else None})
    full = sum(r["full"] for r in rows)
    sel = sum(r["selected"] for r in rows)
    cov = [r["gold_covered"] for r in rows if r["gold_covered"] is not None]
    out = {
        "benchmark": name, "questions": len(rows), "databases": len(by_db), "top_k": top_k,
        "objects_median": statistics.median(r["objects"] for r in rows),
        "full_tokens_mean": round(full / len(rows)), "selected_tokens_mean": round(sel / len(rows)),
        "reduction": round(1 - sel / full, 4),
        "tables_sent_median": statistics.median(r["tables_sent"] for r in rows),
        "gold_tables_all_selected": round(sum(cov) / len(cov), 4) if cov else None,
    }
    per_db = {}
    for r in rows:
        d = per_db.setdefault(r["db"], {"objects": r["objects"], "full": r["full"], "sel": []})
        d["sel"].append(r["selected"])
    out["per_db"] = {db: {"objects": d["objects"], "full_tokens": d["full"],
                          "selected_tokens_mean": round(statistics.mean(d["sel"])),
                          "reduction": round(1 - statistics.mean(d["sel"]) / d["full"], 4)}
                     for db, d in sorted(per_db.items())}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bird", help="BIRD dev folder (dev.json, dev_databases/)")
    ap.add_argument("--spider2", help="spider2-lite folder (spider2-lite.jsonl)")
    ap.add_argument("--spider2-dbs", help="folder of the local tasks' SQLite files")
    ap.add_argument("--warehouse", action="store_true",
                    help="also the BigQuery/Snowflake tasks, from --spider2's resource/databases")
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--spider2-top-k", type=int, default=12)
    ap.add_argument("--out", default=str(pathlib.Path(__file__).with_name("results.json")))
    a = ap.parse_args()
    results = []
    if a.bird:
        root = pathlib.Path(a.bird)
        by_db = {}
        for q in json.loads((root / "dev.json").read_text("utf-8")):
            by_db.setdefault(q["db_id"], []).append({"question": q["question"], "sql": q["SQL"]})
        results.append(measure("BIRD dev (all 1,534 questions)", by_db, a.top_k,
                               lambda db: root / "dev_databases" / db / f"{db}.sqlite"))
    if a.spider2:
        dbs = pathlib.Path(a.spider2_dbs)
        by_db = {}
        for line in (pathlib.Path(a.spider2) / "spider2-lite.jsonl").read_text("utf-8").splitlines():
            q = json.loads(line)
            if q["instance_id"].startswith("local") and (dbs / f"{q['db']}.sqlite").exists():
                by_db.setdefault(q["db"], []).append({"question": q["question"]})
        results.append(measure("Spider 2.0-lite, local SQLite tasks", by_db, a.spider2_top_k,
                               lambda db: dbs / f"{db}.sqlite"))
    if a.spider2 and a.warehouse:
        root = pathlib.Path(a.spider2)
        dirs = {}
        for eng in ("bigquery", "snowflake"):
            for d in (root / "resource" / "databases" / eng).iterdir():
                if d.is_dir():
                    dirs.setdefault(d.name, (eng, d))
        gold = root / "evaluation_suite" / "gold" / "sql"
        by_db = {}
        for line in (root / "spider2-lite.jsonl").read_text("utf-8").splitlines():
            q = json.loads(line)
            if q["instance_id"].startswith("local") or q["db"] not in dirs:
                continue
            g = gold / f"{q['instance_id']}.sql"
            eng = dirs[q["db"]][0]
            by_db.setdefault(q["db"], []).append(
                {"question": q["question"], "sql": g.read_text("utf-8") if g.exists() else None,
                 "dialect": "bigquery" if eng == "bigquery" else "snowflake"})
        results.append(measure("Spider 2.0-lite, BigQuery and Snowflake tasks", by_db, a.spider2_top_k,
                               None, catalog=lambda db: warehouse_catalog(dirs[db][1])))
    pathlib.Path(a.out).write_text(json.dumps(results, indent=2) + "\n", "utf-8")
    for r in results:
        print(f"{r['benchmark']}: {r['questions']} questions, {r['databases']} databases, top_k={r['top_k']}")
        print(f"  full schema {r['full_tokens_mean']:,} tokens/question, selected {r['selected_tokens_mean']:,}"
              f"  ->  {100 * r['reduction']:.1f}% fewer")
        if r["gold_tables_all_selected"] is not None:
            print(f"  every gold table in the selection: {100 * r['gold_tables_all_selected']:.1f}% of questions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
