# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""UniQL on Oracle, step 0: is the data there? Runs every Oracle gold query once. No model is called.

UniQL (github.com/JerryGao818/UniQL) translates BIRD dev's 1,534 questions into 16 SQL dialects. Its
Oracle data is BIRD's 11 dev databases loaded by its own migration/oracle/insert_to_oracle.py, one
Oracle user per database. This connects as each user, runs each gold query with a timeout, and
reports how many execute and how many return rows. A gold query that fails here would make any
prediction for it unscoreable.

    python benchmarks/uniql_oracle_check.py <UniQL>/data/queries/oracle.json
Environment: UNIQL_ORACLE_DSN (localhost:1521/FREEPDB1), UNIQL_ORACLE_PASSWORD (the users' password).
"""
from __future__ import annotations

import collections
import json
import os
import sys
import time


def main():
    import oracledb
    qs = json.load(open(sys.argv[1], encoding="utf-8"))
    dsn = os.environ.get("UNIQL_ORACLE_DSN", "localhost:1521/FREEPDB1")
    pw = os.environ["UNIQL_ORACLE_PASSWORD"]
    conns = {}
    stats = collections.Counter()
    per_db = collections.defaultdict(collections.Counter)
    fails = []
    t0 = time.time()
    for q in qs:
        db = q["db_id"]
        if db not in conns:
            conns[db] = oracledb.connect(user=db.upper(), password=pw, dsn=dsn)
            conns[db].call_timeout = 60_000
        cur = conns[db].cursor()
        try:
            cur.execute("ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS'")
            cur.execute(q["SQL-Oracle"])
            rows = cur.fetchmany(5)
            stats["ok"] += 1
            per_db[db]["ok"] += 1
            if rows:
                stats["rows"] += 1
        except Exception as e:                                       # noqa: BLE001
            stats["fail"] += 1
            per_db[db]["fail"] += 1
            if len(fails) < 15:
                fails.append((q["question_id"], db, str(e).splitlines()[0][:120]))
        finally:
            cur.close()
    print(f"{len(qs)} gold queries in {time.time() - t0:.0f}s: executed {stats['ok']}, "
          f"returned rows {stats['rows']}, failed {stats['fail']}")
    for db in sorted(per_db):
        print(f"  {db:26} ok {per_db[db]['ok']:4}  fail {per_db[db]['fail']}")
    for f in fails:
        print("  FAIL", *f)


if __name__ == "__main__":
    main()
