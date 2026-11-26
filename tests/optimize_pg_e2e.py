"""schemagate.optimize against a real PostgreSQL (CI: mcp-e2e.yml, postgres job).

Run: SGE_URL=postgresql+psycopg://postgres:...@127.0.0.1:5432/postgres python tests/optimize_pg_e2e.py

Checks the PostgreSQL paths the SQLite unit tests cannot: rows compared inside
the server (hash sum, ordered md5), timing from EXPLAIN ANALYZE, the READ ONLY
transaction, the statement timeout, and one real end-to-end speedup.
"""
import os
import sys

from sqlalchemy import create_engine, text

from schemagate import optimize as opt
from schemagate.ai.providers import CallableProvider
from schemagate.answer import UnsafeSQL

URL = os.environ["SGE_URL"]
eng = create_engine(URL)

with eng.begin() as c:
    c.execute(text("DROP TABLE IF EXISTS opt_orders"))
    c.execute(text("CREATE TABLE opt_orders (id int PRIMARY KEY, customer int, amount int, note text)"))
    c.execute(text("INSERT INTO opt_orders SELECT g, g % 500, (g * 7919) % 1009, 'n' || g "
                   "FROM generate_series(1, 60000) g"))
    c.execute(text("ANALYZE opt_orders"))

SLOW = ("SELECT o.id, o.customer, o.amount FROM opt_orders o "
        "WHERE o.amount = (SELECT MAX(o2.amount) FROM opt_orders o2 WHERE o2.customer = o.customer)")
FAST = ("SELECT o.id, o.customer, o.amount FROM opt_orders o JOIN "
        "(SELECT customer, MAX(amount) AS m FROM opt_orders GROUP BY customer) x "
        "ON x.customer = o.customer AND o.amount = x.m")
failures = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    if not cond:
        failures.append(name)


# rows compared in the server
c = opt.compare(eng, SLOW, FAST, runs=1)
check("equivalent rewrite is identical", c.identical, c.reason)
check("timing comes from the server", c.timing == "database")
check("the join is faster than the correlated subquery", (c.speedup or 0) > 1.5, f"{c.speedup}x")

w = opt.compare(eng, SLOW, "SELECT o.id, o.customer, o.amount FROM opt_orders o WHERE o.amount > 1000")
check("different rows are caught", not w.identical, w.reason)

asc = "SELECT id, amount FROM opt_orders WHERE id <= 200 ORDER BY id"
desc = "SELECT id, amount FROM opt_orders WHERE id <= 200 ORDER BY id DESC"
check("ORDER BY order is checked", not opt.compare(eng, asc, desc).identical)
check("unordered original ignores order",
      opt.compare(eng, "SELECT id, amount FROM opt_orders WHERE id <= 200", desc).identical)

fp = opt.fingerprint(eng, "SELECT * FROM opt_orders")
check("fingerprint counts every row in the server", fp.rows == 60000, str(fp.rows))

check("explain shows real timings", "Execution Time" in opt.explain(eng, FAST))

# safety
try:
    opt.compare(eng, SLOW, "DELETE FROM opt_orders")
    check("a write is refused", False)
except UnsafeSQL:
    check("a write is refused", True)

with opt._read_session(eng, 10) as conn:                 # past the text check: the transaction itself refuses
    try:
        conn.exec_driver_sql("CREATE TEMP TABLE sneaky (x int)")
        conn.exec_driver_sql("INSERT INTO opt_orders VALUES (-1, 0, 0, 'x')")
        check("the session is READ ONLY", False)
    except Exception as e:                                # noqa: BLE001
        check("the session is READ ONLY", "read-only" in str(e).lower(), str(e).splitlines()[0][:80])
with eng.connect() as conn:
    check("nothing was written", conn.execute(text("SELECT count(*) FROM opt_orders")).scalar() == 60000)

try:
    opt.measure_ms(eng, "SELECT pg_sleep(5)", runs=1, timeout=1)
    check("the statement timeout holds", False)
except Exception as e:                                    # noqa: BLE001
    check("the statement timeout holds", "timeout" in str(e).lower() or "cancel" in str(e).lower(),
          str(e).splitlines()[0][:80])

# the whole loop, with a model that proposes the join
r = opt.optimize(eng, SLOW, CallableProvider(lambda s, p: f"```sql\n{FAST}\n```"), rounds=1, runs=1)
check("optimize picks the measured-faster identical rewrite", r.improved and r.sql == FAST,
      f"{r.original_ms} ms -> {r.optimized_ms} ms, {r.speedup}x")

with eng.begin() as c:
    c.execute(text("DROP TABLE opt_orders"))
print("FAILED: " + ", ".join(failures) if failures else "all optimize checks passed")
sys.exit(1 if failures else 0)
