# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""schemagate on UniQL's Oracle dialect (1,534 BIRD dev questions), scored by UniQL's own evaluator.

UniQL (github.com/JerryGao818/UniQL) translates BIRD dev into 16 SQL dialects; its Oracle data is
BIRD's 11 dev databases loaded by its migration/oracle/insert_to_oracle.py, one Oracle user per
database. Per question, in BIRD's standard setting (question plus its evidence hint): schemagate
reflects that user's tables, with sampled values for short text columns, selects the tables the
question needs, adds BIRD's column descriptions for those tables, and asks the model for one Oracle
query. A database error is shown back to the model for up to --repairs fixes. If the model declines,
it is asked once for its best reading, since every question has an answer. The gold SQL is never
shown to the model; it is copied into the output file only because UniQL's evaluator reads it there.

--dry-run uses each question's gold SQL as the "prediction" and calls no model: it checks the
catalogue, the prompt and the evaluator end to end, for free.

    python benchmarks/uniql_oracle.py --queries <UniQL>/data/queries/oracle.json \
        --bird-db-root <BIRD dev_databases> --out oracle_flash.json [--dry-run] [--limit N]
Environment: UNIQL_ORACLE_DSN, UNIQL_ORACLE_PASSWORD; OCI config for the oci provider.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import importlib.util
import json
import os
import pathlib
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("bird_minidev", HERE / "bird_minidev.py")
_bm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bm)
descriptions, REPAIR = _bm.descriptions, _bm.REPAIR
BEST_EFFORT = _bm.BEST_EFFORT.format(dialect="Oracle")
_ck = importlib.util.spec_from_file_location("uniql_oracle_check", HERE / "uniql_oracle_check.py")
_check = importlib.util.module_from_spec(_ck)
_ck.loader.exec_module(_check)
#: The session UniQL's evaluator scores in. The repair loop runs each query to see whether it errors,
#: so it has to run it where the evaluator will, or a correct query gets "repaired".
UNIQL_SESSION = _check.UNIQL_SESSION


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--queries", required=True, help="UniQL data/queries/oracle.json")
    ap.add_argument("--bird-db-root", required=True, help="BIRD dev_databases (for database_description/)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--provider", choices=["oci", "oci-key", "gemini", "anthropic"], default="oci",
                    help="oci: OCI Generative AI with an ~/.oci signing key; oci-key: OCI Generative AI with a "
                         "Generative AI API key (OCI_GENAI_API_KEY, optional OCI_GENAI_PROJECT, OCI_GENAI_REGION) "
                         "on its OpenAI-compatible endpoint; gemini: Google's Gemini API (GEMINI_API_KEY)")
    ap.add_argument("--model", default=None,
                    help="default: google.gemini-2.5-flash on oci/oci-key, gemini-2.5-flash on gemini")
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--repairs", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true", help="gold SQL as the prediction; no model is called")
    a = ap.parse_args()

    import sqlalchemy as sa

    from schemagate import Catalog
    from schemagate.answer import UnsafeSQL, _strip_fences, check_read_only, generate_sql

    qs = json.load(open(a.queries, encoding="utf-8"))
    if a.limit:
        qs = qs[:a.limit]
    dsn, pw = os.environ.get("UNIQL_ORACLE_DSN", "localhost:1521/FREEPDB1"), os.environ["UNIQL_ORACLE_PASSWORD"]
    root = pathlib.Path(a.bird_db_root)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {r["question_id"]: r for r in json.loads(out.read_text("utf-8"))} if out.exists() else {}
    log = out.with_suffix(".log.jsonl").open("a", encoding="utf-8")
    prov = None
    if not a.dry_run:
        if a.provider == "oci":
            import oci

            from schemagate.ai.providers import OCIGenAIProvider
            prov = OCIGenAIProvider(model=a.model or "google.gemini-2.5-flash", timeout=300,
                                    compartment_id=os.environ.get("OCI_COMPARTMENT_ID")
                                    or oci.config.from_file()["tenancy"])
        elif a.provider == "oci-key":
            import openai

            from schemagate.ai.providers import OpenAIProvider
            region = os.environ.get("OCI_GENAI_REGION") or "us-chicago-1"
            client = openai.OpenAI(
                api_key=os.environ["OCI_GENAI_API_KEY"], timeout=300,
                base_url=f"https://inference.generativeai.{region}.oci.oraclecloud.com/openai/v1",
                project=os.environ.get("OCI_GENAI_PROJECT") or None)
            prov = OpenAIProvider(model=a.model or "google.gemini-2.5-flash", client=client)
        elif a.provider == "gemini":
            from schemagate.ai.providers import GeminiProvider
            prov = GeminiProvider(model=a.model or "gemini-2.5-flash")
        else:
            from schemagate.ai.providers import AnthropicProvider
            prov = AnthropicProvider(model=a.model)
    cats, lock = {}, threading.Lock()

    def catalog(db):
        with lock:
            if db not in cats:
                eng = sa.create_engine(f"oracle+oracledb://{db.upper()}:{pw}@{dsn.split('/')[0]}"
                                       f"/?service_name={dsn.split('/')[1]}", pool_size=a.workers)

                @sa.event.listens_for(eng, "connect")
                def _session(dbapi_conn, _record):
                    with dbapi_conn.cursor() as cur:
                        for stmt in UNIQL_SESSION:
                            cur.execute(stmt)
                # Name the user's own schema. UniQL's loader before 2026-11-12 created each user with
                # _ORACLE_SCRIPT=true (Oracle-maintained, which schemagate skips); naming it works for both.
                own = sa.inspect(eng).default_schema_name
                cat = Catalog(name=db).bootstrap(eng, schemas=[own], sample_values=True)
                cat.infer_foreign_keys()
                if not cat.objects():
                    insp = sa.inspect(eng)
                    print(f"[{db}] schemagate reflected 0 objects; default schema {insp.default_schema_name!r}, "
                          f"tables {insp.get_table_names()[:5]}", flush=True)
                else:
                    print(f"[{db}] {len(cat.objects())} objects, e.g. {[o.qname for o in cat.objects()][:3]}", flush=True)
                cats[db] = (cat.index(), eng)
        return cats[db]

    def run(eng, sql, limit=5, timeout_s=60):
        with eng.connect() as c:
            c.connection.driver_connection.call_timeout = timeout_s * 1000
            try:
                return c.execute(sa.text(sql.replace(":", "\\:"))).fetchmany(limit)
            finally:
                c.rollback()

    def patient(fn, *args, **kw):
        for attempt in range(8):
            try:
                return fn(*args, **kw)
            except UnsafeSQL:
                raise
            except Exception as ex:                                # noqa: BLE001
                # 502/503 too: 8 questions of the 2026-11-13 run got no SQL from a passing Gemini outage
                if attempt == 7 or not any(s in str(ex) for s in ("429", "502", "503", "UNAVAILABLE", "Circuit",
                                                                   "OPEN", "Timeout", "timed out")):
                    raise
                time.sleep(min(120, 15 * (attempt + 1)))

    def solve(q):
        qid = q["question_id"]
        if qid in done:
            return None
        cat, eng = catalog(q["db_id"])
        question = q["question"] + (("\nHint: " + q["evidence"].strip()) if (q.get("evidence") or "").strip() else "")
        sel = cat.select(question, top_k=a.top_k)
        frag = sel.prompt_fragment()
        notes = descriptions(root / q["db_id"], sel.table_names)
        if notes:
            frag += "\n\n" + notes
        e = {"question_id": qid, "db": q["db_id"], "tables": sel.table_names, "tries": []}
        sql = None
        if a.dry_run:
            sql = q["SQL-Oracle"]
            e["prompt_chars"] = len(frag)
        else:
            try:
                sql = patient(generate_sql, prov, question, frag, dialect="Oracle", max_tokens=a.max_tokens)
            except UnsafeSQL:
                e["declined"] = True
                try:
                    reply = patient(prov.complete, "You write Oracle queries.",
                                    f"Question:\n{question}\n\nSchema:\n{frag}\n\n" + BEST_EFFORT, max_tokens=a.max_tokens)
                    sql = check_read_only(_strip_fences(reply))
                except Exception as ex:                            # noqa: BLE001
                    e["error"] = f"best effort: {type(ex).__name__}: {str(ex)[:150]}"
            except Exception as ex:                                # noqa: BLE001
                e["error"] = f"{type(ex).__name__}: {str(ex)[:150]}"
            for _ in range(a.repairs + 1):
                if not sql:
                    break
                try:
                    run(eng, sql)
                    break
                except Exception as ex:                            # noqa: BLE001
                    err = f"{type(ex).__name__}: {str(ex)[:300]}"
                    e["tries"].append(err[:120])
                    try:
                        reply = patient(prov.complete, "You write Oracle queries.",
                                        f"Question:\n{question}\n\nSchema:\n{frag}\n\n"
                                        + REPAIR.format(err=err, sql=sql, dialect="Oracle"), max_tokens=a.max_tokens)
                        sql = check_read_only(_strip_fences(reply))
                    except Exception:                              # noqa: BLE001
                        break
        e["sql"] = sql
        rec = {"question_id": qid, "db_id": q["db_id"], "difficulty": q.get("difficulty", ""),
               "annotation_source": q.get("annotation_source", "unknown"),
               "pred_sqls": [" ".join((sql or "SELECT 0 FROM DUAL").split())],
               "ground_truth_sql": q["SQL-Oracle"]}               # read by UniQL's evaluator only
        with lock:
            done[qid] = rec
            out.write_text(json.dumps([done[k] for k in sorted(done)], indent=1), "utf-8")
            log.write(json.dumps(e) + "\n")
            log.flush()
        return e

    t0, n = time.time(), 0
    with cf.ThreadPoolExecutor(a.workers) as pool:
        for _ in pool.map(solve, qs):
            n += 1
            if n % 50 == 0:
                print(f"  {n}/{len(qs)}  {time.time() - t0:.0f}s", flush=True)
    print(f"{len(qs)} questions -> {out} ({len(done)} predictions, {time.time() - t0:.0f}s)")
    if a.dry_run:
        q0 = qs[0]
        sample = catalog(q0["db_id"])[0]
        print("--- sample prompt fragment ---")
        print(sample.select(q0["question"], top_k=a.top_k).prompt_fragment()[:1500])


if __name__ == "__main__":
    main()
