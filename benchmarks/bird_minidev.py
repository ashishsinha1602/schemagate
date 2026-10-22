# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""schemagate on BIRD Mini-Dev (500 questions; SQLite, PostgreSQL or MySQL), scored by BIRD's own evaluator.

Writes a predictions file in Mini-Dev's format ({"<index>": "<sql>\\t----- bird -----\\t<db_id>"}) that
`mini_dev/evaluation/evaluation_ex.py` (and _ves, _f1) score unchanged against the gold SQL.

Per question, in BIRD's standard setting (the question plus its "evidence" hint):
schemagate reflects the database with short sampled values, selects the tables the question needs,
adds BIRD's own column descriptions (database_description/*.csv) for those tables only, and asks the
model for one SQLite query. If the model declines (schemagate lets it say the tables cannot answer),
it is asked once for its best reading instead, since every question here has an answer. If SQLite
raises an error, the model gets the error and tries again, at most `--repairs` times. Nothing reads
the gold SQL.

    python benchmarks/bird_minidev.py --data <minidev>/MINIDEV --out out/bird_minidev.json
    python benchmarks/bird_minidev.py --data <minidev>/MINIDEV --dialect postgresql \
        --url postgresql+psycopg://postgres:...@127.0.0.1:5432/bird --out out/bird_minidev_pg.json

For PostgreSQL and MySQL the eleven databases are loaded from Mini-Dev's dumps into one database; each
question's catalog holds only its own database's tables (dev_tables.json), as the SQLite version does.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import json
import pathlib
import sqlite3
import threading
import time

REPAIR = ("The query below failed on {dialect} with this error:\n{err}\n\nQuery:\n{sql}\n\n"
          "Write a corrected {dialect} query for the same question. Reply with the SQL only.")
DIALECTS = {"sqlite": "SQLite", "postgresql": "PostgreSQL", "mysql": "MySQL"}
SEP = "\t----- bird -----\t"
BEST_EFFORT = ("These tables do answer the question; it may be loosely worded. Read it the way a data analyst "
               "would, use the hint, and write the one {dialect} query that best answers it. Reply with the SQL only.")


def run(db, sql, limit=5, timeout=60):
    if not isinstance(db, pathlib.Path):                          # a SQLAlchemy engine
        import sqlalchemy as sa
        with db.connect() as c:
            if db.dialect.name == "postgresql":
                c.exec_driver_sql(f"SET statement_timeout = {timeout * 1000}")
            elif db.dialect.name == "mysql":
                c.exec_driver_sql(f"SET SESSION MAX_EXECUTION_TIME = {timeout * 1000}")
            try:
                return c.execute(sa.text(sql.replace(":", "\\:"))).fetchmany(limit)
            finally:
                c.rollback()
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=timeout)
    t0 = time.time()
    con.set_progress_handler(lambda: 1 if time.time() - t0 > timeout else 0, 100000)
    try:
        return con.execute(sql).fetchmany(limit)
    finally:
        con.close()


REASON_SYSTEM = "You are an expert data analyst who writes correct {dialect} queries."
REASON_ASK = ("Work it out step by step before writing SQL:\n"
              "1. Which tables and columns hold what the question asks for; read the hint and column notes.\n"
              "2. How the tables join (foreign keys).\n"
              "3. Every filter, with the exact stored value and spelling (see the values found, if listed).\n"
              "4. Exactly which columns to return, in the order asked, and nothing extra; aggregates, ordering, "
              "LIMIT, DISTINCT and division as REAL where a ratio or percentage is asked.\n"
              "Then give the final query, one {dialect} SELECT, in a ```sql block at the end.")
EXACT = ("Return exactly the columns the question asks for, in the order it asks, and nothing else; "
         "no extra id or helper columns.")
STOP = set("""a an the of in on at to for from by with and or not is are was were be been what which who whom whose
how many much list give show name names find tell me all any each per than that this these those there their its
it as please among between does do did has have had top most least more less average total number count percentage
ratio""".split())


def _grams(text: str):
    """Quoted strings, then 3-, 2- and 1-word phrases from the question and hint, lowercased."""
    import re
    quoted = [m.strip() for m in re.findall(r"'([^']{1,60})'|\"([^\"]{1,60})\"", text) for m in m if m.strip()]
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9.\-&/]*", text)
    out = [w.lower() for w in quoted]
    for n in (3, 2, 1):
        for k in range(len(words) - n + 1):
            g = words[k:k + n]
            if all(w.lower() in STOP for w in g) or (n == 1 and (len(g[0]) < 3 or g[0].isdigit())):
                continue
            out.append(" ".join(g).lower())
    seen, keep = set(), []
    for g in out:
        if g not in seen:
            seen.add(g)
            keep.append(g)
    return keep[:80]


_ENGINES: dict = {}


def value_hints(cat, path, tables, question: str, per_query_s: float = 3.0) -> str:
    """Which words of the question are real values in which text columns (case-insensitive exact match).

    One scan per text column of the database's tables: SELECT DISTINCT col WHERE LOWER(col) IN (...).
    Shows the model the stored spelling and casing, the commonest BIRD miss being a filter on the wrong
    literal. Reads values only, never the gold SQL.
    """
    import sqlalchemy as sa
    grams = _grams(question)
    if not grams:
        return ""
    eng = path if not isinstance(path, pathlib.Path) else _ENGINES.setdefault(
        str(path), sa.create_engine(f"sqlite:///file:{path.as_posix()}?mode=ro&uri=true"))
    q = eng.dialect.identifier_preparer.quote
    want = {t.split(".")[-1].lower() for t in tables}
    hits = []
    for doc in cat.objects():
        if doc.name.lower() not in want:
            continue
        for c in doc.columns:
            if not any(s in (c.type or "").upper() for s in ("CHAR", "TEXT", "STRING", "CLOB")):
                continue
            sql = (f"SELECT DISTINCT {q(c.name)} FROM {q(doc.name)} "
                   f"WHERE LOWER({q(c.name)}) IN ({', '.join(f':g{k}' for k in range(len(grams)))}) LIMIT 6")
            try:
                with eng.connect() as con:
                    if eng.dialect.name == "postgresql":
                        con.exec_driver_sql(f"SET statement_timeout = {int(per_query_s * 1000)}")
                    elif eng.dialect.name == "mysql":
                        con.exec_driver_sql(f"SET SESSION MAX_EXECUTION_TIME = {int(per_query_s * 1000)}")
                    vals = [r[0] for r in con.execute(sa.text(sql), {f"g{k}": g for k, g in enumerate(grams)})]
                    con.rollback()
            except Exception:                                      # noqa: BLE001
                continue
            if vals:
                hits.append(f"  {doc.name}.{c.name}: " + ", ".join(repr(v) for v in vals))
    return ("Values from the question found in the database (use this exact spelling):\n"
            + "\n".join(hits[:25])) if hits else ""


def _key(rows):
    return frozenset(tuple(repr(v) for v in r) for r in rows)


def vote(cands, e):
    """The answer most candidates' results agree on; a query that errored never wins, an empty or all-NULL
    result wins only if nothing else ran. Ties go to the earlier candidate (the plain selection first)."""
    if not cands:
        return None
    ran = [(t, s, r) for t, s, r in cands if r is not None]
    useful = [(t, s, r) for t, s, r in ran if r and any(v is not None for row in r for v in row)]
    pool = useful or ran or cands
    if pool is cands or len(pool) == 1:
        e["vote"] = [pool[0][0]]
        return pool[0][1]
    groups: dict = {}
    for t, s, r in pool:
        groups.setdefault(_key(r), []).append((t, s))
    best = max(groups.values(), key=len)          # max keeps the first of equal size: earlier candidate
    e["vote"] = [t for t, _ in best] + [f"of {len(pool)}"]
    return best[0][1]


def descriptions(db_dir: pathlib.Path, tables) -> str:
    """BIRD's column descriptions and value notes for the selected tables, from database_description/."""
    out = []
    d = db_dir / "database_description"
    for t in tables:
        name = t.split(".")[-1]
        f = next((p for p in d.glob("*.csv") if p.stem.lower() == name.lower()), None) if d.exists() else None
        if f is None:
            continue
        lines = []
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                rows = list(csv.DictReader(f.open(encoding=enc, newline="")))
                break
            except UnicodeDecodeError:
                continue
        else:
            continue
        for r in rows:
            col = (r.get("original_column_name") or "").strip()
            bits = [(r.get("column_description") or "").strip(), (r.get("value_description") or "").strip()]
            bits = [" ".join(b.split()) for b in bits if b and b.lower() != "nan"]
            if col and bits:
                lines.append(f"  {col}: " + " | ".join(bits)[:400])
        if lines:
            out.append(f"{name}:\n" + "\n".join(lines))
    return ("Column notes from the database's documentation:\n" + "\n".join(out)) if out else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", help="the MINIDEV folder (mini_dev_sqlite.json, dev_databases/)")
    ap.add_argument("--questions", help="any BIRD question file instead (dev.json, test.json); SQLite only")
    ap.add_argument("--db-root", help="folder with one <db_id>/<db_id>.sqlite per database (with --questions)")
    ap.add_argument("--out", required=True, help="predictions JSON to write")
    ap.add_argument("--model", default="google.gemini-2.5-flash")
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--repairs", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max-calls", type=int, default=0,
                    help="stop after this many model calls (0 = no limit); re-run the same command to resume")
    ap.add_argument("--limit", type=int, default=0, help="only the first N questions (a pilot)")
    ap.add_argument("--dialect", choices=list(DIALECTS), default="sqlite")
    ap.add_argument("--url", help="SQLAlchemy URL of the loaded Mini-Dev database (postgresql, mysql)")
    ap.add_argument("--candidates", type=int, default=1,
                    help="1 = one query (the original run); up to 4 = vote over differently prompted candidates")
    ap.add_argument("--reason", action="store_true",
                    help="ask the model to reason step by step, then take the last ```sql block")
    ap.add_argument("--values", action="store_true",
                    help="look the question's words up in the text columns and show the model the real values")
    ap.add_argument("--provider", choices=["anthropic", "oci"], default="oci",
                    help="oci: OCI Generative AI on demand (compartment = OCI_COMPARTMENT_ID or the tenancy)")
    a = ap.parse_args()

    from schemagate import Catalog
    from schemagate.ai.providers import AnthropicProvider, OCIGenAIProvider
    from schemagate.answer import UnsafeSQL, _strip_fences, check_read_only, generate_sql

    dialect = DIALECTS[a.dialect]
    if a.questions:
        if a.dialect != "sqlite" or not a.db_root:
            ap.error("--questions needs --db-root and the sqlite dialect")
        qs = json.loads(pathlib.Path(a.questions).read_text("utf-8"))
        dbroot = pathlib.Path(a.db_root)
        tables_of = {}
    else:
        root = pathlib.Path(a.data)
        qs = json.loads((root / f"mini_dev_{a.dialect}.json").read_text("utf-8"))
        dbroot = root / "dev_databases"
        tables_of = {d["db_id"]: d["table_names_original"]
                     for d in json.loads((root / "dev_tables.json").read_text("utf-8"))}
    engine = None
    if a.dialect != "sqlite":
        import sqlalchemy as sa
        engine = sa.create_engine(a.url, pool_size=a.workers, max_overflow=2)
    if a.limit:
        qs = qs[:a.limit]
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = json.loads(out.read_text("utf-8")) if out.exists() else {}
    log = out.with_suffix(".log.jsonl").open("a", encoding="utf-8")
    if a.provider == "oci":
        import os

        import oci
        prov = OCIGenAIProvider(model=a.model, timeout=300,
                                compartment_id=os.environ.get("OCI_COMPARTMENT_ID") or oci.config.from_file()["tenancy"])
    else:
        prov = AnthropicProvider(model=a.model)
    cats, lock = {}, threading.Lock()

    def catalog(db):
        with lock:
            if db not in cats:
                d = dbroot / db
                if engine is None:
                    path = d / f"{db}.sqlite"
                    cat = Catalog(name=db).bootstrap(f"sqlite:///{path.as_posix()}", sample_values=True)
                else:
                    path = engine
                    cat = Catalog(name=db).bootstrap(engine, include=tables_of[db], sample_values=True)
                cat.infer_foreign_keys()
                cats[db] = (cat.index(), path, d)
        return cats[db]

    calls = {"n": 0}

    def patient(fn, *args, **kw):
        """Call the model, waiting out rate limits (429, an open circuit) instead of scoring a blank."""
        if a.max_calls and calls["n"] >= a.max_calls:
            raise SystemExit(f"stopped: --max-calls {a.max_calls} reached ({len(done)} predictions written; "
                             "re-run the same command to resume)")
        calls["n"] += 1
        for attempt in range(8):
            try:
                return fn(*args, **kw)
            except UnsafeSQL:
                raise
            except Exception as ex:                                # noqa: BLE001
                if attempt == 7 or not any(s in str(ex) for s in ("429", "Circuit", "OPEN", "Timeout", "timed out")):
                    raise
                time.sleep(min(120, 15 * (attempt + 1)))

    def one(question, frag, e, tag):
        """One candidate: write, run, repair on error. Returns (sql, rows) or (sql, None)."""
        sql = None
        try:
            if a.reason:
                reply = patient(prov.complete, REASON_SYSTEM.format(dialect=dialect),
                                f"{frag}\n\nQuestion:\n{question}\n\n" + REASON_ASK.format(dialect=dialect),
                                max_tokens=a.max_tokens)
                blocks = __import__("re").findall(r"```(?:sql)?\s*(.*?)```", reply, __import__("re").S | __import__("re").I)
                sql = check_read_only(blocks[-1].strip() if blocks else _strip_fences(reply))
            else:
                sql = patient(generate_sql, prov, question, frag, dialect=dialect, max_tokens=a.max_tokens)
        except UnsafeSQL:
            # schemagate's prompt lets the model decline; every benchmark question has an answer here,
            # so ask once for its best reading of the question instead of scoring a blank
            e.setdefault("insufficient", []).append(tag)
            try:
                reply = patient(prov.complete, f"You write {dialect} queries.",
                                f"Question:\n{question}\n\nSchema:\n{frag}\n\n" + BEST_EFFORT.format(dialect=dialect),
                                max_tokens=a.max_tokens)
                sql = check_read_only(_strip_fences(reply))
            except Exception as ex2:                               # noqa: BLE001
                e.setdefault("errors", []).append(f"{tag} best effort: {type(ex2).__name__}: {str(ex2)[:150]}")
                return None, None
        except Exception as ex:                                    # noqa: BLE001
            e.setdefault("errors", []).append(f"{tag}: {type(ex).__name__}: {str(ex)[:150]}")
            return None, None
        for _ in range(a.repairs + 1):
            try:
                return sql, run(path_of(e), sql, limit=1000)
            except Exception as ex:                                # noqa: BLE001
                err = f"{type(ex).__name__}: {str(ex)[:300]}"
                e["tries"].append(f"{tag}: {err[:120]}")
                try:
                    reply = patient(prov.complete, f"You write {dialect} queries.",
                                    f"Question:\n{question}\n\nSchema:\n{frag}\n\n"
                                    + REPAIR.format(err=err, sql=sql, dialect=dialect), max_tokens=a.max_tokens)
                    sql = check_read_only(_strip_fences(reply))
                except Exception:                                  # noqa: BLE001
                    break
        return sql, None

    paths = {}

    def path_of(e):
        return paths[e["db"]]

    def solve(i, q):
        key = str(i)
        if key in done:
            return None
        cat, path, d = catalog(q["db_id"])
        paths[q["db_id"]] = path
        question = q["question"]
        if (q.get("evidence") or "").strip():
            question += "\nHint: " + q["evidence"].strip()
        sel = cat.select(question, top_k=a.top_k)
        everything = cat.select(question, top_k=len(cat.objects()))
        found = value_hints(cat, path, everything.table_names, question) if a.values else ""
        e = {"i": i, "question_id": q.get("question_id"), "db": q["db_id"], "tables": sel.table_names,
             "values": found[:400], "tries": []}

        def frag_of(s, notes=True):
            f = s.prompt_fragment()
            n = descriptions(d, s.table_names) if notes else ""
            return f + ("\n\n" + n if n else "") + ("\n\n" + found if found else "")

        # candidates differ by what the model is shown (temperature is 0, so the prompt is the variety)
        plans = [("selected", question, frag_of(sel)),
                 ("all tables", question, frag_of(everything)),
                 ("no notes", question, frag_of(sel, notes=False)),
                 ("exact columns", question + "\n" + EXACT, frag_of(sel))][:a.candidates]
        cands = []
        for tag, qtext, frag in plans:
            sql, rows = one(qtext, frag, e, tag)
            if sql:
                cands.append((tag, sql, rows))
        sql = vote(cands, e)
        e["sql"] = sql
        line = " ".join((sql or "SELECT 0").split())
        with lock:
            done[key] = line + SEP + q["db_id"]
            # the evaluator pairs predictions with gold lines by position, so keep question order
            out.write_text(json.dumps({k: done[k] for k in sorted(done, key=int)}, indent=1), "utf-8")
            log.write(json.dumps(e) + "\n")
            log.flush()
        return e

    t0 = time.time()
    n = 0
    with cf.ThreadPoolExecutor(a.workers) as pool:
        for _ in pool.map(lambda iq: solve(*iq), enumerate(qs)):
            n += 1
            if n % 25 == 0:
                print(f"  {n}/{len(qs)}  {time.time() - t0:.0f}s", flush=True)
    print(f"{len(qs)} questions -> {out} ({len(done)} predictions, {time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
