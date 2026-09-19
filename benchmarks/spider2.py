"""schemagate on Spider 2.0-lite: the benchmark built for real schemas.

Spider 1.0 databases have a median of three tables, which is why the pooled
setting had to be invented to say anything. Spider 2.0 needs no such
invention: 162 databases, 7,892 tables, a median of 14 and a maximum of 785,
taken from real BigQuery and Snowflake warehouses. Retrieval is the
acknowledged bottleneck here rather than a formality.

Scored the same way as the other two: table recall against the tables the
benchmark's own gold SQL reads. Only the questions whose gold SQL is public
are used -- the rest is held out, and guessing at it would be worse than a
smaller sample.

Gold SQL names tables as `project.dataset.table` in backticks, sometimes with
a wildcard suffix (`ga_sessions_*`). Both are reduced to the bare table name,
which is what the catalog holds.
"""
import json
import os
import pathlib
from longpath import read_json, read_text
import re
import statistics
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent

from schemagate import Catalog, Column, ObjectDoc      # noqa: E402

ROOT = HERE / "Spider2" / "spider2-lite"
DBS = ROOT / "resource" / "databases"
GOLD = ROOT / "evaluation_suite" / "gold" / "sql"
QUESTIONS = HERE / "spider2_lite.jsonl"
#: The prose ablation in BENCHMARKS.md: same files, description entries dropped.
NO_DESC = os.environ.get("SPIDER2_NO_DESC") == "1"

#: `proj.dataset.table`, "dataset"."table", bare table -- after FROM or JOIN.
_REF = re.compile(r"\b(?:from|join)\s+([`\"\w.\-*$]+)", re.I)
_CTE = re.compile(r"(?:\bwith\b|,)\s*([A-Za-z_]\w*)\s+as\s*\(", re.I)


def bare(ref: str) -> str:
    """`bigquery-public-data.ga.ga_sessions_*` -> ga_sessions."""
    t = ref.strip().strip("`").strip('"').split(".")[-1].strip('`"')
    return t.rstrip("*").rstrip("_").lower()


def gold_tables(sql: str, known: set) -> set:
    body = re.sub(r"--[^\n]*", " ", sql)
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    ctes = {c.lower() for c in _CTE.findall(body)}
    out = set()
    for ref in _REF.findall(body):
        b = bare(ref)
        if b and b not in ctes and b in known:
            out.add(b)
    return out


def load_db(path: pathlib.Path):
    """ObjectDocs for one Spider 2.0 database directory."""
    docs = []
    for f in path.rglob("*.json"):
        try:
            d = read_json(f)
        except Exception:                                    # noqa: BLE001
            continue
        name = d.get("table_name") or f.stem
        # `nested_column_names` is the flattened list (nested/repeated fields
        # included) and is what the gold SQL references; it is present only
        # when the table has such fields. gnomAD v3_genomes__chr7 has 61
        # top-level columns and 181 flattened.
        nested = d.get("nested_column_names")
        names = nested or d.get("column_names") or []
        types = (d.get("nested_column_types") if nested else d.get("column_types")) or []
        # `description` is not a table description: it is one entry per
        # column, aligned by index to the list above, entries sometimes null
        # (150/150 sampled files, never a string). This used to be joined
        # into one paragraph and stored on the table, which read plausibly
        # and threw away the only column-level text in the dataset.
        desc = None if NO_DESC else d.get("description")
        per_col = list(desc) if isinstance(desc, (list, tuple)) else []
        cols = []
        for i, n in enumerate(names):
            comment = per_col[i] if i < len(per_col) else None
            cols.append(Column(str(n), str(types[i] if i < len(types) else "TEXT"),
                               True, str(comment) if comment else None, False))
        if not cols:
            continue
        docs.append(ObjectDoc(name=str(name), schema=path.name, kind="TABLE",
                              description=(desc if isinstance(desc, str) and desc else None),
                              columns=cols))
    return docs


def main():
    rows = [json.loads(l) for l in QUESTIONS.read_text("utf-8").splitlines() if l.strip()]
    have_gold = {p.stem for p in GOLD.glob("*.sql")}
    dirs = {}
    for eng in DBS.iterdir():
        for db in eng.iterdir():
            if db.is_dir():
                dirs.setdefault(db.name, db)

    cases = [r for r in rows if r["instance_id"] in have_gold and r["db"] in dirs]
    print(f"Spider 2.0-lite: {len(rows)} questions, {len(have_gold)} with public gold SQL")
    print(f"usable (gold + schema on disk): {len(cases)} questions over "
          f"{len({c['db'] for c in cases})} databases")

    sizes = [len(list(dirs[d].rglob('*.json'))) for d in {c['db'] for c in cases}]
    print(f"database size: median {statistics.median(sizes):.0f}, "
          f"max {max(sizes)} tables  (Spider 1.0 median was 3, BIRD 7)\n")

    cats, kn = {}, {}
    for db in sorted({c["db"] for c in cases}):
        docs = load_db(dirs[db])
        cat = Catalog()
        for d in docs:
            cat.add(d)
        # What `Catalog.bootstrap()` does for every real user, and what this
        # script used to skip: a table written one file per day is one table.
        # Spider 2.0's ga4 is 92 `events_2020xxxx` and ga360 is 366, and held
        # apart they differ only by a date -- so they crowd out everything
        # else and none of them can be told from the others. Measuring
        # without this measured a schemagate nobody runs.
        cat.collapse_partitions()
        cat.index()
        cats[db] = cat
        kn[db] = {bare(d.name) for d in cat.objects()}

    prepared = []
    for c in cases:
        sql = read_text(GOLD / f"{c['instance_id']}.sql")
        g = gold_tables(sql, kn[c["db"]])
        if g:
            prepared.append((c["db"], c["question"], g))
    print(f"questions whose gold tables resolve against the schema: {len(prepared)}\n")

    for k in (5, 10, 20):
        full = part = 0
        for db, q, gold in prepared:
            picked = {bare(n.split(".")[-1])
                      for n in cats[db].select(q, top_k=k).table_names}
            full += (gold <= picked)
            part += len(gold & picked) / len(gold)
        n = len(prepared)
        print(f"  top_k={k:2}: all gold tables present {full}/{n} "
              f"({100*full/n:.1f}%)   per-table recall {100*part/n:.1f}%")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\n({time.time()-t0:.0f}s)")
