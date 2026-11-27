"""SQL tool for the BIRD-CRITIC agent: run SQL on the task's own copy of its database and print the result.

    python critic_sql.py <instance_id> <<'SQL'
    <one or more statements>
    SQL

The copy (crit_<id>) was cloned from the benchmark's template database and had the task's preprocess_sql
applied. Every call runs inside a transaction that is ROLLED BACK, so each call starts from the same state:
you can try UPDATE / CREATE / ALTER freely and inspect the effect within the same call.
"""
import sys
import time

import psycopg

DSN = "host=127.0.0.1 port=5544 user=root"
SHOW = 30


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    iid = sys.argv[1]
    sql = sys.stdin.read().strip()
    with psycopg.connect(f"{DSN} dbname=crit_{iid}", autocommit=False) as con:
        con.execute("SET statement_timeout = '60s'")
        t0 = time.time()
        try:
            cur = con.execute(sql)
            shown = False
            while True:
                if cur.description:
                    cols = [d.name for d in cur.description]
                    rows = cur.fetchall()
                    print(f"columns: {cols}")
                    print(f"rows: {len(rows)}" + (f" (showing first {SHOW})" if len(rows) > SHOW else ""))
                    for r in rows[:SHOW]:
                        print(tuple(v if not isinstance(v, str) or len(v) <= 150 else v[:147] + "..." for v in r))
                    shown = True
                elif cur.statusmessage:
                    print(f"ok: {cur.statusmessage}")
                    shown = True
                if not cur.nextset():
                    break
            if not shown:
                print("ok")
            print(f"({time.time() - t0:.2f} s; rolled back)")
        except psycopg.Error as e:
            msg = str(e).strip().splitlines()[0][:600]
            if "cannot run inside a transaction block" in msg:
                msg += " (this tool always uses a transaction; such a statement is still allowed in your final answer)"
            print(f"error: {msg}")
        finally:
            con.rollback()


if __name__ == "__main__":
    main()
