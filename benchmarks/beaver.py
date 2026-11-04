"""schemagate on BEAVER (MIT's enterprise text-to-SQL benchmark, MySQL), one query per question.

Per question: schemagate selects the tables (top 25, plus tables that join *into* the selection from
the top 50 ranked), looks the question's words up in the text columns, and shows the model the three
most similar solved questions from BEAVER's public query set -- never a question being evaluated.
The model writes one MySQL SELECT; a MySQL error goes back to it for up to three repairs, and a query
that returns nothing gets the stored values of its filter columns and one retry. Nothing reads the
gold SQL except the scorer.

Scoring mirrors beaver/eval/utils/ex_acc.py compare_results: values as stripped strings, set of rows,
column names ignored, both empty = match.

Setup::

    pip install "schemagate[gemini]" pandas pyarrow pymysql
    export GEMINI_API_KEY=...
    # load dw.sql / neutron.sql from beaver_db.zip into MySQL 8 (--lower-case-table-names=1)

Public numbers (BEAVER's own seed-77 sample of 100; ``--second-sample`` = 100 others, seed 78)::

    python benchmarks/beaver.py --questions dw-00000-of-00001.parquet --sample --database dw \\
        --db-url "mysql+pymysql://root:pw@127.0.0.1:3306/{db}?charset=utf8mb4" --out dw100.json

A held-out set (every question is evaluated; the public file is the example pool)::

    python benchmarks/beaver.py --questions private_dw.jsonl --pool dw-00000-of-00001.parquet \\
        --database dw --db-url ... --out private_dw.json

``--questions`` is parquet, JSON or JSONL with ``id`` and ``question``; ``sql`` (gold) is optional,
and without it the output holds the predicted SQL per id and no score. Defaults are the settings
behind the reported numbers (gemini-2.5-flash: dw 31% and 35%, neutron 39%).
"""
import argparse
import concurrent.futures as cf
import json
import os
import pathlib
import random
import re
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bird_minidev as bm  # noqa: E402  value_hints, vote, REPAIR, BEST_EFFORT, EXACT

MYSQL_RULES = (
    "MySQL 8 rules: there is no VAR(), FULL OUTER JOIN, QUALIFY, TOP, ILIKE or PIVOT. "
    "Variance is VARIANCE() or VAR_SAMP(); when the question names a function (STDDEV, VARIANCE, MEDIAN-like "
    "wording), use exactly that function name. A window function cannot take DISTINCT "
    "(no COUNT(DISTINCT x) OVER ...): compute the distinct count in a subquery or CTE and join it. "
    "Emulate FULL OUTER JOIN with a LEFT JOIN UNION a RIGHT JOIN. Quote identifiers that are reserved words "
    "with backticks. Never round unless the question asks for rounding. Return exactly the columns the "
    "question lists, in the order it lists them, and nothing extra."
)

EMPTY_RETRY = (
    "The query below ran but returned no rows (or only NULLs):\n{sql}\n\n"
    "Usually a filter uses a value that is not how the data stores it. Real stored values of the columns "
    "the query filters on:\n{values}\n\n"
    "Write a corrected MySQL query for the same question using the stored values. Reply with the SQL only."
)


class BM25:
    """Plain Okapi BM25 over question text, to find the most similar solved questions."""

    def __init__(self, texts, k1=1.5, b=0.75):
        import collections
        import math
        self.k1, self.b = k1, b
        self.docs = [self.toks(t) for t in texts]
        self.avg = sum(map(len, self.docs)) / max(1, len(self.docs))
        df = collections.Counter(w for d in self.docs for w in set(d))
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self.tf = [collections.Counter(d) for d in self.docs]

    @staticmethod
    def toks(t):
        return [w for w in re.findall(r"[a-z0-9]+", t.lower()) if len(w) > 1]

    def top(self, query, n):
        q = set(self.toks(query))
        scores = []
        for i, (tf, d) in enumerate(zip(self.tf, self.docs)):
            s = 0.0
            for w in q:
                if w in tf:
                    f = tf[w]
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avg))
            scores.append((s, i))
        return [i for _, i in sorted(scores, reverse=True)[:n]]


def load(path):
    """Questions from parquet, JSON (a list) or JSONL, as dicts."""
    p = pathlib.Path(path)
    if p.suffix == ".parquet":
        import pandas as pd
        return pd.read_parquet(p).to_dict("records")
    text = p.read_text("utf-8")
    if p.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    return data if isinstance(data, list) else list(data.values())


def filter_values(cat, engine, sql, per_col=25):
    """Distinct stored values of the text columns that appear in the query's WHERE/HAVING/ON clauses."""
    import sqlalchemy as sa
    tail = " ".join(re.split(r"(?i)\b(?:where|having|on)\b", sql)[1:])
    if not tail:
        return ""
    words = {w.upper() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", tail)}
    named = {w.upper() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", sql)}
    out = []
    for doc in cat.objects():
        if doc.name.upper() not in named:
            continue
        for c in doc.columns:
            if c.name.upper() not in words or not any(s in (c.type or "").upper() for s in ("CHAR", "TEXT")):
                continue
            try:
                with engine.connect() as con:
                    con.exec_driver_sql("SET SESSION MAX_EXECUTION_TIME = 5000")
                    vals = [r[0] for r in con.execute(sa.text(
                        f"SELECT DISTINCT `{c.name}` FROM `{doc.name}` WHERE `{c.name}` IS NOT NULL LIMIT {per_col}"))]
            except Exception:  # noqa: BLE001
                continue
            if vals:
                out.append(f"  {doc.name}.{c.name}: " + ", ".join(repr(v) for v in vals))
    return "\n".join(out[:30])


def rows_key(rows):
    return set(tuple(str(v).strip() for v in r) for r in rows)


def same(pred, gold):
    if not pred and not gold:
        return True
    if not pred or not gold:
        return False
    if len(pred[0]) != len(gold[0]):
        return False
    return rows_key(pred) == rows_key(gold)


def execute(engine, sql, timeout=30):
    import sqlalchemy as sa
    with engine.connect() as c:
        c.exec_driver_sql(f"SET SESSION MAX_EXECUTION_TIME = {timeout * 1000}")
        try:
            return [tuple(r) for r in c.execute(sa.text(sql.replace(":", "\\:"))).fetchall()]
        finally:
            c.rollback()


def provider(a):
    if a.provider == "gemini":
        from schemagate.ai.providers import GeminiProvider
        return GeminiProvider(model=a.model)                     # GEMINI_API_KEY
    if a.provider == "anthropic":
        from schemagate.ai.providers import AnthropicProvider
        return AnthropicProvider(model=a.model, timeout=300)     # ANTHROPIC_API_KEY
    import oci
    from schemagate.ai.providers import OCIGenAIProvider
    model = a.model if a.model.startswith("google.") else f"google.{a.model}"
    return OCIGenAIProvider(model=model, timeout=300,
                            compartment_id=os.environ.get("OCI_COMPARTMENT_ID") or oci.config.from_file()["tenancy"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--questions", required=True, help="parquet/JSON/JSONL with id, question[, sql, tables]")
    ap.add_argument("--pool", action="append", default=[],
                    help="solved questions to draw examples from (repeatable); default: --questions itself")
    ap.add_argument("--sample", action="store_true",
                    help="evaluate BEAVER's seed-77 sample of 100 from --questions; the rest is the pool")
    ap.add_argument("--second-sample", action="store_true",
                    help="with --sample: 100 other questions (seed 78); both samples stay out of the pool")
    ap.add_argument("--database", required=True, help="dw or neutron (the MySQL database name)")
    ap.add_argument("--db-url", default=os.environ.get("BEAVER_DB_URL"),
                    help="SQLAlchemy URL; {db} is replaced by --database")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="only the first N questions (0 = all)")
    ap.add_argument("--provider", choices=["gemini", "oci", "anthropic"], default="gemini")
    ap.add_argument("--model", default="gemini-2.5-flash")
    ap.add_argument("--top-k", type=int, default=25)
    ap.add_argument("--inward", type=int, default=50,
                    help="also add tables that join INTO the selection, from the top-N ranked (0 = off)")
    ap.add_argument("--similar", type=int, default=3, help="similar solved questions shown per question")
    ap.add_argument("--repairs", type=int, default=3)
    ap.add_argument("--no-mysql-rules", action="store_true")
    ap.add_argument("--no-empty-retry", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-tokens", type=int, default=16000)
    a = ap.parse_args()
    if not a.db_url:
        raise SystemExit("pass --db-url or set BEAVER_DB_URL")

    import sqlalchemy as sa
    import schemagate.answer as sga
    from schemagate import Catalog
    from schemagate.answer import UnsafeSQL, _strip_fences, check_read_only, generate_sql
    if not a.no_mysql_rules:
        sga.DIALECT_RULES["mysql"] = MYSQL_RULES

    qs = load(a.questions)
    if a.sample:
        random.seed(77)                                  # BEAVER's own sampling (download_hf.py)
        sample = random.sample(qs, min(100, len(qs)))
        held_out = {q["id"] for q in sample}
        if a.second_sample:
            rest = [q for q in qs if q["id"] not in held_out]
            random.seed(78)
            sample = random.sample(rest, min(100, len(rest)))
            held_out |= {q["id"] for q in sample}
        pool = [q for q in qs if q["id"] not in held_out]
        qs = sample
    else:
        pool = [q for p in a.pool for q in load(p)] if a.pool else []
    evaluated = {q["id"] for q in qs}
    pool = [q for q in pool if q["id"] not in evaluated and q.get("sql")]   # never an evaluated question
    if a.limit:
        qs = qs[:a.limit]
    bm25 = BM25([q["question"] for q in pool]) if a.similar and pool else None

    db = a.database
    engine = sa.create_engine(a.db_url.format(db=db), pool_size=a.workers, max_overflow=2)
    t0 = time.time()
    cat = Catalog(name=db).bootstrap(engine, schemas=[db], sample_values=True)
    cat.infer_foreign_keys()
    cat.index()
    incoming = {}
    for d in cat.objects():
        for fk in d.foreign_keys:
            incoming.setdefault(fk.ref_table.split(".")[-1].upper(), set()).add(d.name.upper())
    print(f"catalog: {len(cat.objects())} tables in {time.time() - t0:.0f}s; "
          f"{len(qs)} questions, example pool {len(pool)}", flush=True)

    prov = provider(a)
    usage = {"calls": 0, "in_chars": 0, "out_chars": 0}
    lock = threading.Lock()
    raw = prov.complete

    def counted(system, prompt, max_tokens=1024):
        for attempt in range(8):
            try:
                reply = raw(system, prompt, max_tokens=max_tokens)
                break
            except Exception as ex:  # noqa: BLE001
                transient = ("429", "503", "Circuit", "OPEN", "Timeout", "timed out", "RESOURCE_EXHAUSTED", "UNAVAILABLE")
                if attempt == 7 or not any(s in str(ex) for s in transient):
                    raise
                time.sleep(min(120, 15 * (attempt + 1)))
        with lock:
            usage["calls"] += 1
            usage["in_chars"] += len(system) + len(prompt)
            usage["out_chars"] += len(reply or "")
        return reply

    prov.complete = counted
    dialect = "MySQL"

    def candidate(question, frag, e):
        shots = ()
        if bm25 is not None:
            top = bm25.top(question, a.similar)
            shots = tuple((pool[i]["question"], pool[i]["sql"]) for i in top)
            e["similar"] = [pool[i]["id"] for i in top]
        try:
            sql = generate_sql(prov, question, frag, dialect=dialect, max_tokens=a.max_tokens, examples=shots)
        except UnsafeSQL:
            e["insufficient"] = True
            sql = check_read_only(_strip_fences(prov.complete(
                f"You write {dialect} queries.",
                f"Question:\n{question}\n\nSchema:\n{frag}\n\n" + bm.BEST_EFFORT.format(dialect=dialect),
                max_tokens=a.max_tokens)))
        pred = None
        for k in range(a.repairs + 1):
            try:
                pred = execute(engine, sql)
                break
            except Exception as ex:  # noqa: BLE001
                err = f"{type(ex).__name__}: {str(ex)[:300]}"
                e["tries"].append(err[:160])
                if k == a.repairs:
                    break
                try:
                    sql = check_read_only(_strip_fences(prov.complete(
                        f"You write {dialect} queries.",
                        f"Question:\n{question}\n\nSchema:\n{frag}\n\n"
                        + bm.REPAIR.format(err=err, sql=sql, dialect=dialect), max_tokens=a.max_tokens)))
                except Exception:  # noqa: BLE001
                    break
        blank = pred is not None and (not pred or all(v is None for r in pred for v in r))
        if blank and not a.no_empty_retry:
            vals = filter_values(cat, engine, sql)
            if vals:
                e["empty_retry"] = True
                try:
                    sql2 = check_read_only(_strip_fences(prov.complete(
                        f"You write {dialect} queries.",
                        f"Question:\n{question}\n\nSchema:\n{frag}\n\n" + EMPTY_RETRY.format(sql=sql, values=vals),
                        max_tokens=a.max_tokens)))
                    pred2 = execute(engine, sql2)
                    if pred2 and any(v is not None for r in pred2 for v in r):
                        sql, pred = sql2, pred2
                except Exception as ex:  # noqa: BLE001
                    e["tries"].append(f"empty retry: {str(ex)[:120]}")
        return sql, pred

    def solve(q):
        question = q["question"]
        sel = cat.select(question, top_k=a.top_k)
        if a.inward:
            picked = {t.split(".")[-1].upper() for t in sel.table_names}
            ranked = [t.split(".")[-1].upper() for t in cat.select(question, top_k=a.inward).table_names]
            extra = [t for t in ranked if t not in picked and any(t in incoming.get(p, ()) for p in picked)]
            if extra:
                sel = cat.select(question, top_k=a.top_k + len(extra), pin=[f"{db}.{t}" for t in extra])
        everything = cat.select(question, top_k=len(cat.objects()))
        found = bm.value_hints(cat, engine, everything.table_names, question)
        frag = sel.prompt_fragment() + ("\n\n" + found if found else "")
        e = {"id": q["id"], "selected": sel.table_names, "tries": []}
        try:
            sql, pred = candidate(question, frag, e)
        except Exception as ex:  # noqa: BLE001
            e["tries"].append(str(ex)[:120])
            sql, pred = "SELECT 0", None
        e["sql"] = sql
        if q.get("sql"):
            try:
                e["correct"] = pred is not None and same(pred, execute(engine, q["sql"], timeout=60))
            except Exception as ex:  # noqa: BLE001
                e["gold_error"] = str(ex)[:200]
                e["correct"] = False
        if q.get("tables") is not None:
            gold = {t.lower() for t in (json.loads(q["tables"]) if isinstance(q["tables"], str) else q["tables"])}
            got = {t.split(".")[-1].lower() for t in sel.table_names}
            e["table_recall"] = len(gold & got) / max(1, len(gold))
        return e

    results = []
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for e in ex.map(solve, qs):
            results.append(e)
            mark = "" if "correct" not in e else ("OK" if e["correct"] else "X ")
            print(f"  {len(results)}/{len(qs)} {mark}", flush=True)

    n = len(results)
    scored = [r for r in results if "correct" in r]
    summary = {"database": db, "n": n, "model": a.model, "provider": a.provider,
               "calls": usage["calls"], "est_input_tokens": usage["in_chars"] // 4,
               "est_output_tokens": usage["out_chars"] // 4, "seconds": round(time.time() - t0)}
    if scored:
        ok = sum(r["correct"] for r in scored)
        summary.update(ex_acc=round(100 * ok / len(scored), 2), correct=ok, scored=len(scored),
                       gold_errors=sum("gold_error" in r for r in scored))
    recall = [r["table_recall"] for r in results if "table_recall" in r]
    if recall:
        summary["table_recall"] = round(100 * sum(recall) / len(recall), 1)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "predictions": {r["id"]: r["sql"] for r in results},
                               "results": results}, indent=1, default=str), "utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
