# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""schemagate end to end on Spider 2.0-lite's BigQuery and Snowflake questions, in the leaderboard's format.

Spider 2.0-lite has 547 questions: 135 on SQLite (`benchmarks/spider2_local.py`), 205 on BigQuery (`bq*`,
`ga*`) and 207 on Snowflake (`sf*`, `sf_bq*`). This runs the warehouse ones. Per question:

1. the database's tables come from Spider 2.0's own metadata files (`resource/databases/<platform>/<db>/...json`:
   names, types, nested fields, descriptions, sample rows), so no warehouse round trip is needed to see a schema;
2. schemagate selects the tables the question needs (`--top-k`, default 12);
3. the prompt gets those tables' DDL with sample values, the question's external-knowledge document when Spider
   2.0 provides one, and the dialect's rules;
4. the model writes **one** query; it runs on the warehouse; if the warehouse raises an error the model sees the
   error and the query and tries again, at most `--repairs` times;
5. the final query is written as `<id>.sql`, its result as `<id>.csv`, and everything the system did (selection,
   prompts' shape, every attempt, every error, timestamps) as `<id>.trace.md`: the three things a leaderboard
   submission must contain.

Nothing reads the gold SQL or the gold results. BigQuery bills by bytes scanned: every query is dry-run first and
refused above `--max-gb` (default 5), and the total is printed. Snowflake access is the Spider 2.0 participant
account (free, queued).

    export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json           # BigQuery
    export SPIDER2_SNOWFLAKE_CREDENTIAL=/path/to/snowflake_credential.json        # Snowflake
    export ANTHROPIC_API_KEY=...
    python benchmarks/spider2_lite.py --spider2 <Spider2>/spider2-lite --platform bigquery \\
        --out out/spider2_bq --model claude-sonnet-5-5
    cd <Spider2>/spider2-lite/evaluation_suite && python evaluate.py --mode sql --result_dir out/spider2_bq
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import json
import os
import pathlib
import re
import threading
import time

PLATFORM_OF = {"bq": "bigquery", "ga": "bigquery", "sf": "snowflake", "sf_bq": "snowflake", "local": "sqlite"}

#: Dialect facts the model is told. They are the kind of thing a warehouse's own documentation says on page one;
#: none came from a Spider 2.0 question or its answer.
HINTS = {
    "bigquery": (
        "BigQuery Standard SQL. Always use the fully-qualified table name shown in the schema, in backticks: "
        "`project.dataset.table`. Arrays and structs: use UNNEST(...) for REPEATED fields and dot paths for "
        "RECORD fields. Date-sharded tables such as events_2021* are addressed with a wildcard and _TABLE_SUFFIX. "
        "Prefer SAFE_DIVIDE, SAFE_CAST, DATE()/TIMESTAMP() conversions and standard aggregate functions; no "
        "LIMIT is needed unless the question asks for a top-n. Return exactly the columns the question asks for."),
    "snowflake": (
        "Snowflake SQL. Always use the fully-qualified name shown in the schema: DATABASE.SCHEMA.TABLE. Unquoted "
        "identifiers are upper-cased; quote an identifier only if the schema shows it in mixed or lower case. "
        "Semi-structured VARIANT columns are read with column:field and LATERAL FLATTEN(input => ...). "
        "Use DATE_TRUNC, DATEADD, DATEDIFF, TO_DATE, and ILIKE for case-insensitive matches; QUALIFY is available. "
        "Return exactly the columns the question asks for."),
}

REPAIR = ("The query below failed on {platform} with this error:\n{err}\n\nQuery:\n{sql}\n\n"
          "Write a corrected {platform} query for the same question. Reply with the SQL only.")
BEST_EFFORT = ("\nIf the schema seems not to contain everything the question needs, do not refuse: use the "
               "closest tables and columns available and write your best reading of the question as one query.")


#: A trailing date or year on a table name: ga_sessions_20170101, events_20210131, gsod2019, ghcnd_1990.
_SHARD = re.compile(r"^(?P<stem>.*?[A-Za-z])_?(?P<suffix>\d{8}|\d{6}|\d{4})$")


def _collapse_shards(tables: list) -> list:
    """BigQuery date-sharded families as one wildcard table each.

    ga360 is 366 copies of ga_sessions_YYYYMMDD, ga4 92 of events_*, noaa 96 of gsod<year>, ghcn_d 262. Offered
    one by one they fill every selection slot with random dates and the model declines ("no table for January
    2017"). Three or more tables sharing a stem and the same columns become `stem_*`, addressed with
    _TABLE_SUFFIX, with the suffix range in the description. That is how BigQuery documents querying them."""
    fams: dict = {}
    for t in tables:
        m = _SHARD.match(t["name"])
        key = (t["prefix"], m.group("stem")) if m else None
        fams.setdefault(key, []).append((t, m.group("suffix") if m else None))
    out = []
    for key, members in fams.items():
        if key is None or len(members) < 3:
            out.extend(t for t, _ in members)
            continue
        prefix, stem = key
        suffixes = sorted(s for _, s in members)
        head = dict(members[0][0])
        # shards drift over the years (ga_sessions gained columns in 2017): the family shows the union
        seen_cols = set()
        columns = []
        for t, _ in members:
            for col in t["columns"]:
                if col[0] not in seen_cols:
                    seen_cols.add(col[0])
                    columns.append(col)
        head["columns"], head["cols"] = columns, [c[0] for c in columns]
        sep = "_" if any(t["name"].startswith(stem + "_") for t, _ in members) else ""
        head["name"] = f"{stem}{sep}*"
        head["full"] = f"{prefix}.{stem}{sep}*"
        head["desc"] = (f"Date-sharded family: {len(members)} tables {stem}{sep}{suffixes[0]} .. {stem}{sep}{suffixes[-1]}. "
                        f"Query with the wildcard name and filter _TABLE_SUFFIX (e.g. _TABLE_SUFFIX BETWEEN "
                        f"'{suffixes[0]}' AND '{suffixes[-1]}'). " + (head.get("desc") or ""))[:400]
        out.append(head)
    return out


def _docs_for(db_dir: pathlib.Path, platform: str):
    """Spider 2.0's metadata JSON files as schemagate ObjectDocs: one per table (one per shard family on
    BigQuery), nested fields flattened into dotted column names, sample values carried in the column comment
    (that is what the DDL fragment prints)."""
    from schemagate import Column, ObjectDoc

    tables = []
    for f in sorted(db_dir.rglob("*.json")):
        try:
            d = json.loads(f.read_text("utf-8"))
        except Exception:                                  # noqa: BLE001  DDL.csv and friends are not tables
            continue
        names = list(d.get("column_names") or [])
        types = list(d.get("column_types") or [])
        nnames = list(d.get("nested_column_names") or [])
        ntypes = list(d.get("nested_column_types") or [])
        if not names and not nnames:
            continue
        samples: dict = {}
        for row in (d.get("sample_rows") or [])[:3]:
            if isinstance(row, dict):
                for k, v in row.items():
                    s = str(v)
                    if s and s != "None" and len(s) <= 40:
                        samples.setdefault(k, [])
                        if s not in samples[k]:
                            samples[k].append(s)
        # Spider 2.0's `description` is a list aligned with column_names (one entry per column), not a
        # table description; a string, when it is one, describes the table.
        desc = d.get("description")
        col_desc: dict = {}
        table_desc = None
        if isinstance(desc, (list, tuple)):
            if len(desc) == len(names):
                col_desc = {str(n): str(x) for n, x in zip(names, desc) if x and str(x) != "None"}
            else:
                table_desc = " ".join(str(x) for x in desc if x)[:400] or None
        elif desc:
            table_desc = str(desc)[:400]
        cols = []
        seen = set()
        for i, n in enumerate(names):
            t = types[i] if i < len(types) else "STRING"
            parts = []
            if col_desc.get(str(n)):
                parts.append(col_desc[str(n)][:200])
            if samples.get(n):
                parts.append("e.g. " + ", ".join(samples[n][:3]))
            cols.append((str(n), str(t), " ".join(parts) if parts else None))
            seen.add(str(n))
        for i, n in enumerate(nnames):                      # nested paths the plain list does not have
            if str(n) in seen:
                continue
            t = ntypes[i] if i < len(ntypes) else "STRING"
            cols.append((str(n), str(t), None))
        full = ".".join(p.strip() for p in str(d.get("table_fullname") or d.get("table_name") or f.stem).split("."))
        prefix, _, name = full.rpartition(".")
        tables.append({"full": full, "prefix": prefix, "name": name, "desc": table_desc,
                       "cols": [c[0] for c in cols], "columns": cols})
    if platform == "bigquery":
        tables = _collapse_shards(tables)
    return [ObjectDoc(name=t["full"], schema=None, kind="TABLE", description=t["desc"],
                      columns=[Column(n, ty, True, cm, False) for n, ty, cm in t["columns"]])
            for t in tables]


class BigQueryRunner:
    platform = "bigquery"
    dialect = "BigQuery Standard SQL"

    def __init__(self, max_gb: float):
        from google.cloud import bigquery
        self._bq = bigquery
        self.client = bigquery.Client()
        self.max_gb = max_gb
        self.scanned_gb = 0.0
        self._lock = threading.Lock()

    def run(self, sql: str, limit: int = 1000):
        dry = self.client.query(sql, job_config=self._bq.QueryJobConfig(dry_run=True, use_query_cache=False))
        gb = (dry.total_bytes_processed or 0) / 1e9
        if gb > self.max_gb:
            raise RuntimeError(f"refused: the query would scan {gb:.1f} GB, above the {self.max_gb:.0f} GB cap")
        job = self.client.query(sql)
        rows = job.result(max_results=limit)
        cols = [f.name for f in rows.schema]
        data = [list(r.values()) for r in rows]
        with self._lock:
            self.scanned_gb += gb
        return cols, data


class SnowflakeRunner:
    platform = "snowflake"
    dialect = "Snowflake SQL"

    def __init__(self, credential_path: str):
        import snowflake.connector
        cred = json.loads(pathlib.Path(credential_path).read_text("utf-8"))
        self._connect = lambda: snowflake.connector.connect(
            user=cred.get("username") or cred.get("user"), password=cred["password"], account=cred["account"],
            role=cred.get("role"), warehouse=cred.get("warehouse"), login_timeout=60, network_timeout=600)
        self.scanned_gb = 0.0

    def run(self, sql: str, limit: int = 1000):
        con = self._connect()
        try:
            cur = con.cursor()
            cur.execute(sql)
            cols = [d[0] for d in cur.description]
            data = [list(r) for r in cur.fetchmany(limit)]
            return cols, data
        finally:
            con.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spider2", required=True, help="the spider2-lite folder (metadata, documents, spider2-lite.jsonl)")
    ap.add_argument("--platform", choices=["bigquery", "snowflake"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--provider", choices=["anthropic", "oci"], default="anthropic")
    ap.add_argument("--top-k", type=int, default=12)
    ap.add_argument("--repairs", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--max-gb", type=float, default=5.0, help="BigQuery: refuse a query that would scan more")
    ap.add_argument("--max-frag-chars", type=int, default=60000,
                    help="shrink top_k until the schema fragment fits this many characters")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--limit", type=int, default=None, help="first N questions only (a pilot)")
    ap.add_argument("--max-calls", type=int, default=None, help="stop after this many model calls (resumable)")
    ap.add_argument("--full-schema", action="store_true", help="control arm: every table, no selection")
    a = ap.parse_args()

    from schemagate import Catalog
    from schemagate.ai.providers import AnthropicProvider, OCIGenAIProvider
    from schemagate.answer import UnsafeSQL, _strip_fences, check_read_only, generate_sql

    root = pathlib.Path(a.spider2)
    qs = [json.loads(line) for line in (root / "spider2-lite.jsonl").read_text("utf-8").splitlines() if line.strip()]
    prefix = lambda iid: "sf_bq" if iid.startswith("sf_bq") else iid.rstrip("0123456789")  # noqa: E731
    qs = [q for q in qs if PLATFORM_OF.get(prefix(q["instance_id"])) == a.platform
          and (not a.only or q["instance_id"] in a.only)]
    if a.limit:
        qs = qs[:a.limit]
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log = out.with_name(out.name + "_log.jsonl").open("a", encoding="utf-8")

    if a.provider == "oci":
        import oci
        prov = OCIGenAIProvider(model=a.model, timeout=300,
                                compartment_id=os.environ.get("OCI_COMPARTMENT_ID") or oci.config.from_file()["tenancy"])
    else:
        prov = AnthropicProvider(model=a.model)
    runner = (BigQueryRunner(a.max_gb) if a.platform == "bigquery"
              else SnowflakeRunner(os.environ["SPIDER2_SNOWFLAKE_CREDENTIAL"]))

    calls = {"n": 0}
    lock = threading.Lock()
    cats: dict = {}

    def catalog(db: str):
        with lock:
            if db not in cats:
                cat = Catalog(name=db)
                for d in _docs_for(root / "resource" / "databases" / a.platform / db, a.platform):
                    cat.add(d)
                cat.index()
                cats[db] = cat
        return cats[db]

    def count_call():
        with lock:
            calls["n"] += 1
            if a.max_calls and calls["n"] > a.max_calls:
                raise SystemExit(f"--max-calls {a.max_calls} reached; re-run to continue")

    def solve(q):
        iid = q["instance_id"]
        if (out / f"{iid}.sql").exists():
            return {"id": iid, "skipped": True}
        trace = [f"# {iid}", f"- database: {q['db']}", f"- platform: {a.platform}", f"- model: {a.model}",
                 f"- started: {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}", "",
                 "## Question", q["question"], ""]
        cat = catalog(q["db"])
        question = q["question"]
        doc = q.get("external_knowledge")
        if doc:
            p = root / "resource" / "documents" / doc
            if p.exists():
                question += "\n\nReference document:\n" + p.read_text("utf-8", errors="replace")
                trace.append(f"- reference document: {doc} ({p.stat().st_size} bytes, appended to the question)")
        question += "\n\n" + HINTS[a.platform]
        n_all = len(cat.objects())
        k = n_all if a.full_schema else min(a.top_k, n_all)
        sel = cat.select(q["question"], top_k=k)
        frag = sel.prompt_fragment()
        # Some warehouses (the census tables: 250 columns each, every one described) blow the prompt up; a
        # budget on the fragment, met by taking fewer tables, keeps cost and attention in proportion.
        while len(frag) > a.max_frag_chars and k > 3 and not a.full_schema:
            k = max(3, k * 2 // 3)
            sel = cat.select(q["question"], top_k=k)
            frag = sel.prompt_fragment()
        trace += ["", f"## Tables selected by schemagate ({len(sel.table_names)} of {n_all})"] + \
                 [f"- {t}" for t in sel.table_names] + ["", f"Prompt schema fragment: {len(frag)} characters.", ""]
        e = {"id": iid, "db": q["db"], "tables": sel.table_names, "model": a.model, "tries": []}
        sql = None
        try:
            count_call()
            try:
                sql = generate_sql(prov, question, frag, dialect=runner.dialect, max_tokens=a.max_tokens)
            except UnsafeSQL as ex:
                # a decline is always scored wrong; ask once more for the best reading of the question
                trace += ["## Attempt 1", f"The model declined: {str(ex)[:300]}", "Asked again, best effort:", ""]
                e["declined_first"] = str(ex)[:160]
                count_call()
                sql = generate_sql(prov, question + BEST_EFFORT, frag, dialect=runner.dialect, max_tokens=a.max_tokens)
            trace += ["## Attempt 1", "```sql", sql, "```", ""]
        except UnsafeSQL as ex:
            e["insufficient"] = str(ex)[:160]
            trace += [f"Declined again: {str(ex)[:300]}", ""]
        except SystemExit:
            raise
        except Exception as ex:                                     # noqa: BLE001
            e["error"] = f"{type(ex).__name__}: {str(ex)[:200]}"
            trace += ["## Attempt 1", f"Model error: {e['error']}", ""]
        cols, data = None, None
        for attempt in range(a.repairs + 1):
            if sql is None:
                break
            try:
                cols, data = runner.run(sql)
                e["tries"].append("ok")
                trace.append(f"Ran on {a.platform}: {len(data)} row(s), {len(cols)} column(s).")
                break
            except Exception as ex:                                 # noqa: BLE001
                err = f"{type(ex).__name__}: {str(ex)[:400]}"
                e["tries"].append(err)
                trace.append(f"{a.platform} error: {err}")
                if attempt == a.repairs:
                    break
                try:
                    count_call()
                    reply = prov.complete(f"You write {runner.dialect} queries.",
                                          f"Question:\n{question}\n\nSchema:\n{frag}\n\n"
                                          + REPAIR.format(platform=runner.dialect, err=err, sql=sql),
                                          max_tokens=a.max_tokens)
                    sql = check_read_only(_strip_fences(reply))
                    trace += ["", f"## Attempt {attempt + 2} (repair)", "```sql", sql, "```", ""]
                except SystemExit:
                    raise
                except Exception as ex2:                            # noqa: BLE001
                    e["repair_error"] = f"{type(ex2).__name__}: {str(ex2)[:200]}"
                    trace.append(f"Repair call failed: {e['repair_error']}")
                    break
        if sql:
            (out / f"{iid}.sql").write_text(sql, "utf-8")
        if cols is not None:
            with (out / f"{iid}.csv").open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(cols)
                for r in data:
                    w.writerow(["" if v is None else v for v in r])
        e["sql"] = sql
        e["rows"] = None if data is None else len(data)
        trace += ["", f"- finished: {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}",
                  f"- final: {'ran, result saved as CSV' if cols is not None else ('SQL saved, did not run' if sql else 'no SQL')}"]
        (out / f"{iid}.trace.md").write_text("\n".join(trace), "utf-8")
        with lock:
            log.write(json.dumps(e) + "\n")
            log.flush()
        return e

    t0 = time.time()
    done = ok = 0
    print(f"Spider 2.0-lite {a.platform}: {len(qs)} questions, model {a.model}, top_k {a.top_k}", flush=True)
    with cf.ThreadPoolExecutor(a.workers) as pool:
        for e in pool.map(solve, qs):
            done += 1
            ok += bool(e.get("rows") is not None)
            if done % 10 == 0:
                print(f"  {done}/{len(qs)}  ran {ok}  calls {calls['n']}  {time.time() - t0:.0f}s"
                      + (f"  scanned {runner.scanned_gb:.1f} GB" if a.platform == "bigquery" else ""), flush=True)
    print(f"{len(qs)} questions, {len(list(out.glob('*.sql')))} .sql and {len(list(out.glob('*.csv')))} .csv files "
          f"in {out}; {calls['n']} model calls; {time.time() - t0:.0f}s"
          + (f"; BigQuery scanned {runner.scanned_gb:.1f} GB" if a.platform == "bigquery" else ""))


if __name__ == "__main__":
    main()
