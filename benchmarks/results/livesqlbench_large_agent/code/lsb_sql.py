"""SQL tool for the Claude Code agent run (lsb_cc.py).

    python E:/livesqlbench/work/lsb_sql.py <instance_id> <<'SQL'
    SELECT ...
    SQL

Runs on the task's database inside a transaction that is always rolled back (the task's preprocess_sql first,
as the scorer does) and prints the columns, row count and up to 20 rows of the last statement, or the error.
Same behaviour as run_sql in lsb_agent.py, kept standalone so each call starts fast.
"""
import json
import sys
from pathlib import Path

import psycopg2


def run_sql(dbname, pre, sql, port=5435):
    conn = psycopg2.connect(host="localhost", port=port, user="root", password="123123", dbname=dbname)
    try:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '30s'")
        for p in pre or []:
            if p and p.strip():
                cur.execute(p)
        cur.execute(sql)
        if cur.description is None:
            return f"OK (no result set; rowcount {cur.rowcount})"
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(5001)
        n = len(rows)
        shown = [[(str(v)[:120] if v is not None else None) for v in r] for r in rows[:20]]
        return json.dumps({"columns": cols, "row_count": n if n <= 5000 else ">5000", "rows": shown}, default=str)[:6000]
    except Exception as e:                                   # noqa: BLE001
        return "ERROR: " + str(e).strip().splitlines()[0][:500]
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    iid = sys.argv[1]
    sql = sys.stdin.read()
    if iid.startswith("db="):                    # kb_build.py: a database, no task
        print(run_sql(iid[3:] + "_template", [], sql))
        sys.exit()
    for line in open(Path(__file__).parent / "full.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r["instance_id"] == iid:
            print(run_sql(r["selected_database"] + "_template", r.get("preprocess_sql") or [], sql))
            break
    else:
        print(f"ERROR: unknown task {iid}")
