"""BIRD Mini-Dev (2026 update): BIRD's fixed baseline prompt + Claude Opus 5.5 + execution-guided repair.

This is the setup behind benchmarks/results/bird_minidev_2026/. It does NOT use schemagate's table
selection: on Mini-Dev's small databases, showing the model the full schema in BIRD's own prompt scored
higher (see the README there). What it adds to the plain model is an execution loop:

  1. Send BIRD's fixed prompt for the question (baseline_inference/mini_dev_<dialect>.jsonl, "prompt").
  2. Run the returned SQL read-only. If it errors, send the error back and ask for a corrected query
     (up to 3 tries).
  3. If it runs but returns no rows (or only NULLs), ask the model once to re-check filter values and
     joins; keep the new query only if it returns data.

Gold SQL is never shown to the model; it is used only by BIRD's evaluator afterwards.

    python benchmarks/bird_minidev_2026.py --dialect sqlite --data <bird_mini_dev snapshot> \
        --db-root <MINIDEV>/dev_databases --out predict_mini_dev_sqlite.json
    python benchmarks/bird_minidev_2026.py --dialect postgresql --data ... \
        --url postgresql+psycopg://postgres:...@127.0.0.1:5432/bird --out predict_mini_dev_postgresql.json

Needs ANTHROPIC_API_KEY. Output is Mini-Dev's prediction format ({"<id>": "<sql>\\t----- bird -----\\t<db_id>"}),
scored with Mini-Dev's evaluation/evaluation_ex.py.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import pathlib
import re
import sqlite3
import threading
import time

MODEL = "claude-opus-5-5"
EFFORT = "medium"
NAMES = {"sqlite": "SQLite", "mysql": "MySQL", "postgresql": "PostgreSQL"}
SEP = "\t----- bird -----\t"
SYSTEM = "You are a helpful assistant."
REPAIR = ("The query below failed on {dialect} with this error:\n{err}\n\nQuery:\n{sql}\n\n"
          "Write a corrected {dialect} query for the same question. Reply with the SQL only.")
EMPTY_ASK = ("The query below ran on {dialect} but returned {what}:\n{sql}\n\n"
             "Re-check every filter value against the sample values (format, case, leading zeros, spelling), the join keys, "
             "and whether a filter is stricter than the question asks. If the query is in fact right, repeat it unchanged. "
             "Reply with one {dialect} query only.")
FENCE = "\nEnclose the SQL in a ```sql code block."


def extract(reply: str) -> str:
    m = re.findall(r"```(?:sql|sqlite|mysql|postgresql|postgres)?\s*(.*?)```", reply, re.S | re.I)
    return (m[-1] if m else reply).strip()


def empty(rows) -> bool:
    return not rows or all(v is None for r in rows for v in r)


class Runner:
    def __init__(self, dialect, db_root=None, url=None, timeout=60.0):
        self.dialect, self.db_root, self.timeout = dialect, db_root, timeout
        self.engine = None
        if dialect != "sqlite":
            import sqlalchemy as sa
            self.engine = sa.create_engine(url, pool_pre_ping=True)

    def run(self, db_id, sql):
        if self.dialect == "sqlite":
            path = pathlib.Path(self.db_root) / db_id / f"{db_id}.sqlite"
            con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
            t0 = time.time()
            con.set_progress_handler(lambda: 1 if time.time() - t0 > self.timeout else 0, 10000)
            try:
                return con.execute(sql).fetchall()
            finally:
                con.close()
        # the driver's own cursor with no parameters, so '%' in LIKE patterns and date formats is sent as-is
        raw = self.engine.raw_connection()
        try:
            cur = raw.cursor()
            if self.dialect == "postgresql":
                cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
                cur.execute(f"SET statement_timeout = {int(self.timeout * 1000)}")
            else:
                cur.execute("SET SESSION TRANSACTION READ ONLY")
                cur.execute(f"SET SESSION max_execution_time = {int(self.timeout * 1000)}")
            raw.commit()
            cur.execute(sql)
            rows = [tuple(r) for r in cur.fetchall()]
            raw.rollback()
            return rows
        except Exception:
            try:
                raw.rollback()
            except Exception:  # noqa: BLE001
                pass
            raise
        finally:
            raw.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dialect", required=True, choices=list(NAMES))
    ap.add_argument("--data", required=True, help="bird_mini_dev snapshot (has baseline_inference/)")
    ap.add_argument("--db-root", help="MINIDEV/dev_databases (sqlite)")
    ap.add_argument("--url", help="SQLAlchemy URL of the loaded Mini-Dev database (postgresql, mysql)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    import anthropic

    dialect = NAMES[a.dialect]
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=300, max_retries=6)
    runner = Runner(a.dialect, a.db_root, a.url)
    rows = [json.loads(line) for line in
            open(pathlib.Path(a.data) / "baseline_inference" / f"mini_dev_{a.dialect}.jsonl", encoding="utf-8")]

    def ask(prompt):
        msg = client.messages.create(model=MODEL, max_tokens=8000, system=SYSTEM,
                                     messages=[{"role": "user", "content": prompt}],
                                     extra_body={"output_config": {"effort": EFFORT}})
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")

    def solve(q):
        base = q["prompt"]
        sql = extract(ask(base))
        for _ in range(3):
            try:
                got = runner.run(q["db_id"], sql)
            except Exception as ex:  # noqa: BLE001
                err = f"{type(ex).__name__}: {str(ex)[:300]}"
                sql = extract(ask(base + "\n\n" + REPAIR.format(err=err, sql=sql, dialect=dialect) + FENCE))
                continue
            if empty(got):
                what = "no rows" if not got else "only NULL values"
                retry = extract(ask(base + "\n\n" + EMPTY_ASK.format(dialect=dialect, what=what, sql=sql) + FENCE))
                try:
                    if not empty(runner.run(q["db_id"], retry)):
                        return retry
                except Exception:  # noqa: BLE001
                    pass
            return sql
        return sql

    preds, lock = {}, threading.Lock()

    def one(q):
        sql = solve(q)
        with lock:
            preds[str(q["question_id"])] = " ".join(sql.split()) + SEP + q["db_id"]

    with cf.ThreadPoolExecutor(a.workers) as pool:
        list(pool.map(one, rows))
    out = {k: preds[k] for k in sorted(preds, key=int)}
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False), "utf-8")
    print(f"wrote {len(out)} predictions to {a.out}")


if __name__ == "__main__":
    main()
