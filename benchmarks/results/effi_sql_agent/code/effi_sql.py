"""The agent's only tool for Effi-SQL: run SQL on the task's database, inside a transaction that is rolled back.

  python effi_sql.py <task_id> run      <<'SQL' ... SQL   -> columns, row count, first rows (use LIMIT for big results)
  python effi_sql.py <task_id> explain  <<'SQL' ... SQL   -> EXPLAIN (ANALYZE, BUFFERS) of the SQL
  python effi_sql.py <task_id> compare  <<'SQL' ... SQL   -> is the result identical to the ORIGINAL query's, and the
                                                              speedup, timed like the official Effi-SQL evaluator

Timing matches Diff-SQL's evaluator: PostgreSQL's own "Execution Time" from EXPLAIN (ANALYZE, FORMAT JSON), runs
interleaved so both queries are equally warm. The original query's timing and result fingerprint are measured once
per task and cached (cache/<task>.json). Identity is checked inside the database: row count plus an order-insensitive
sum of row hashes, so huge results are never shipped to Python. Nothing persists; a 600 s statement timeout applies.
"""
import json
import sys
from pathlib import Path

import psycopg2

BENCH = Path(r"E:\effisql\Diff-SQL\data\benchmark\effi-sql\effi-sql-pg.jsonl")
CACHE = Path(r"E:\effisql\work\cache_vm")
TPCH = dict(host="localhost", port=15438, user="postgres", password="123456", dbname="tpch_3g")
SMALL = dict(host="localhost", port=17001, user="root", password="123456")
TIMEOUT_MS = 600_000
RUNS = 2                      # timed runs per query after one warm-up, interleaved (evaluator default is 3)


def task(tid):
    for line in open(BENCH, encoding="utf-8"):
        r = json.loads(line)
        if str(r["id"]) == str(tid):
            return r
    sys.exit(f"unknown task {tid}")


class DB:
    def __init__(self, db):
        self.conn = psycopg2.connect(**(TPCH if db == "tpch" else dict(SMALL, dbname=db)))
        self.cur = self.conn.cursor()

    def q(self, sql, fetch="all"):
        try:
            self.cur.execute(f"SET statement_timeout = {TIMEOUT_MS}")
            self.cur.execute(sql)
            return self.cur.fetchall() if fetch == "all" else self.cur.fetchone()
        finally:
            self.conn.rollback()

    def exec_ms(self, sql):
        row = self.q(f"EXPLAIN (ANALYZE, FORMAT JSON) {sql}", fetch="one")
        return float(row[0][0]["Execution Time"])

    def fingerprint(self, sql):
        n, h = self.q(f"SELECT count(*), coalesce(sum(hashtextextended(t::text, 0)), 0) FROM ({sql}) t", fetch="one")
        return int(n), str(h)


def base_info(t, db):
    CACHE.mkdir(exist_ok=True)
    p = CACHE / f"{t['id']}.json"
    if p.exists():
        return json.loads(p.read_text())
    base = t["base_sql"].strip().rstrip(";")
    db.exec_ms(base)                                   # warm-up
    times = [db.exec_ms(base) for _ in range(RUNS)]
    n, h = db.fingerprint(base)
    info = {"ms": min(times), "rows": n, "hash": h}
    p.write_text(json.dumps(info))
    return info


def main():
    tid, mode = sys.argv[1], sys.argv[2]
    sql = sys.stdin.read().lstrip("\ufeff").strip().rstrip(";")
    t = task(tid)
    db = DB(t["db"])
    try:
        if mode == "run":
            rows = db.q(sql)
            cols = [d[0] for d in db.cur.description] if db.cur.description else []
            print(json.dumps({"columns": cols, "row_count": len(rows),
                              "rows": [[str(v)[:80] for v in r] for r in rows[:10]]}, default=str))
        elif mode == "explain":
            rows = db.q("EXPLAIN (ANALYZE, BUFFERS) " + sql)
            print("\n".join(r[0] for r in rows)[:12000])
        elif mode == "compare":
            b = base_info(t, db)
            n, h = db.fingerprint(sql)
            same = (n == b["rows"] and h == b["hash"])
            if not same:
                print(json.dumps({"identical_results": False, "original_rows": b["rows"], "candidate_rows": n,
                                  "note": "different result: not acceptable"}))
                return
            first = db.exec_ms(sql)                    # warm-up; a rewrite already 10x faster needs no second run
            c = first if first * 10 < b["ms"] else min(first, db.exec_ms(sql))
            o = b["ms"]                                # original timed once per task (warm, cached)
            print(json.dumps({"identical_results": True, "rows": n, "original_ms": round(o, 1),
                              "candidate_ms": round(c, 1), "speedup": round(o / max(c, 0.001), 2)}))
        else:
            sys.exit("mode must be run, explain or compare")
    except Exception as e:  # noqa: BLE001
        print("ERROR: " + str(e).strip().splitlines()[0][:600])


if __name__ == "__main__":
    main()
