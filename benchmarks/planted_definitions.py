# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Does a glossary make the SQL *correct*, not just the tables right? A schema with planted definitions.

Suggested in review on dev.to: BIRD's evidence is mostly one-off formulas, so it can show whether a
glossary helps pick tables but not whether it makes the answer right. Here we write the definitions,
compute every expected answer from them, and score execution.

The database is a small, seeded SQLite company: customers, orders, order lines, products, refunds,
shipments, subscriptions. Eight business terms carry a meaning that a plausible reading gets wrong:

  revenue          completed orders, net of line discounts, minus refunds, internal products excluded
  active customer  a completed order in the 90 days to the as-of date (the is_active flag is stale)
  on-time          shipped on or before the promised date (unshipped excluded)
  big account      lifetime revenue, as defined above, over 5,000
  churned          a subscription that ended with no new one starting within 30 days
  partner sales    revenue (as defined) on orders through the partner channel
  return rate      orders with any refund / completed orders
  AOV              revenue / number of completed orders

Every question has a gold SQL written from the definition, and a NAIVE SQL a reasonable reader would
write without it. A question is kept only if the two disagree on this data -- otherwise it cannot tell
a glossary from no glossary. Arms, through the shipped pipeline (select -> prompt_fragment -> generate_sql):

  A   no glossary          A2  no glossary again (the noise floor)          B   the glossary

    SG_MODEL=claude-sonnet-5 python benchmarks/planted_definitions.py          (needs ANTHROPIC_API_KEY)
    python benchmarks/planted_definitions.py --check                           (data and gold only, no model)
"""
from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import os
import pathlib
import random
import sqlite3
import sys
import tempfile
import time

AS_OF = dt.date(2026, 9, 30)
MODEL = os.environ.get("SG_MODEL", "claude-sonnet-5")
TOP_K = int(os.environ.get("SG_TOP_K", "8"))
OUT = pathlib.Path(os.environ.get("SG_OUT", str(pathlib.Path(tempfile.gettempdir()) / "planted_definitions.jsonl")))

DDL = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, region TEXT, signup_date TEXT,
                        is_active INTEGER);                       -- set at signup, never updated
CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, category TEXT, list_price REAL,
                       is_internal INTEGER);                      -- 1 = staff/test SKU, not sold
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id),
                     status TEXT, placed_at TEXT, channel TEXT);   -- completed | cancelled | pending
CREATE TABLE order_items (id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id),
                          product_id INTEGER REFERENCES products(id), qty INTEGER,
                          unit_price REAL, discount REAL);         -- discount is a fraction, 0..0.3
CREATE TABLE refunds (id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id), amount REAL,
                      refunded_at TEXT);
CREATE TABLE shipments (id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id),
                        promised_at TEXT, shipped_at TEXT, carrier TEXT);
CREATE TABLE subscriptions (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id),
                            plan TEXT, mrr REAL, started_at TEXT, ended_at TEXT);
"""


def build(path: str, seed: int = 20261012) -> None:
    rnd = random.Random(seed)
    con = sqlite3.connect(path)
    con.executescript(DDL)
    regions = ["west", "east", "north", "south"]
    for c in range(1, 121):
        signup = AS_OF - dt.timedelta(days=rnd.randint(100, 900))
        con.execute("INSERT INTO customers VALUES (?,?,?,?,?)",
                    (c, f"Customer {c:03d}", rnd.choice(regions), signup.isoformat(), 1 if rnd.random() < 0.8 else 0))
    cats = ["hardware", "software", "services"]
    for p in range(1, 31):
        internal = 1 if p in (7, 19, 28) else 0
        con.execute("INSERT INTO products VALUES (?,?,?,?,?)",
                    (p, f"Product {p:02d}", rnd.choice(cats), round(rnd.uniform(20, 400), 2), internal))
    oid = iid = rid = sid = 0
    for c in range(1, 121):
        for _ in range(rnd.randint(0, 9)):
            oid += 1
            placed = AS_OF - dt.timedelta(days=rnd.randint(0, 400))
            status = rnd.choices(["completed", "cancelled", "pending"], [0.78, 0.12, 0.10])[0]
            channel = rnd.choices(["web", "store", "partner"], [0.5, 0.3, 0.2])[0]
            con.execute("INSERT INTO orders VALUES (?,?,?,?,?)", (oid, c, status, placed.isoformat(), channel))
            total = 0.0
            for line in range(rnd.randint(1, 4)):
                iid += 1
                p = rnd.randint(1, 30)
                while line == 0 and p in (7, 19, 28):        # an order always has a sold product
                    p = rnd.randint(1, 30)
                qty = rnd.randint(1, 5)
                price = round(rnd.uniform(20, 400), 2)
                disc = rnd.choice([0, 0, 0.05, 0.1, 0.2, 0.3])
                con.execute("INSERT INTO order_items VALUES (?,?,?,?,?,?)", (iid, oid, p, qty, price, disc))
                total += qty * price * (1 - disc)
            if status == "completed" and rnd.random() < 0.15:
                rid += 1
                con.execute("INSERT INTO refunds VALUES (?,?,?,?)",
                            (rid, oid, round(total * rnd.choice([0.2, 0.5, 1.0]), 2),
                             (placed + dt.timedelta(days=rnd.randint(3, 30))).isoformat()))
            if status == "completed":
                sid += 1
                promised = placed + dt.timedelta(days=5)
                shipped = None if rnd.random() < 0.05 else (placed + dt.timedelta(days=rnd.randint(1, 9))).isoformat()
                con.execute("INSERT INTO shipments VALUES (?,?,?,?,?)",
                            (sid, oid, promised.isoformat(), shipped, rnd.choice(["UPS", "FedEx", "DHL"])))
    subid = 0
    for c in range(1, 121):
        if rnd.random() < 0.6:
            start = AS_OF - dt.timedelta(days=rnd.randint(200, 800))
            for _ in range(rnd.randint(1, 3)):
                subid += 1
                ended = None if rnd.random() < 0.4 else start + dt.timedelta(days=rnd.randint(60, 300))
                con.execute("INSERT INTO subscriptions VALUES (?,?,?,?,?,?)",
                            (subid, c, rnd.choice(["basic", "pro", "enterprise"]), rnd.choice([49, 99, 299]),
                             start.isoformat(), ended.isoformat() if ended else None))
                if ended is None:
                    break
                start = ended + dt.timedelta(days=rnd.choice([0, 5, 20, 45, 90]))
    con.commit()
    con.close()


# --- the definitions, as the glossary states them (arm B) and as the gold SQL implements them -----------
REV_EXPR = ("SUM(oi.qty * oi.unit_price * (1 - oi.discount))")
REV_DEF = ("revenue means completed orders only (orders.status = 'completed'), each line valued at "
           "qty * unit_price * (1 - discount), excluding internal products (products.is_internal = 1), "
           "minus the refunds on those orders (refunds.amount)")
GLOSSARY = [
    dict(name="revenue", synonyms=["sales", "net revenue"], maps=["order_items", "orders", "products", "refunds"],
         filter="orders.status = 'completed' AND products.is_internal = 0", definition=REV_DEF),
    dict(name="active customer", synonyms=["active customers"], maps=["customers", "orders"],
         filter="orders.status = 'completed' AND orders.placed_at > date('2026-09-30', '-90 days')",
         definition="an active customer has at least one completed order placed in the 90 days up to "
                    "2026-09-30; customers.is_active is set at signup and must not be used"),
    dict(name="on-time", synonyms=["on time", "on-time shipment"], maps=["shipments"],
         filter="shipments.shipped_at IS NOT NULL AND shipments.shipped_at <= shipments.promised_at",
         definition="a shipment is on time when shipped_at <= promised_at; unshipped shipments "
                    "(shipped_at IS NULL) are excluded from both the count and the total"),
    dict(name="big account", synonyms=["big accounts"], maps=["customers", "orders", "order_items"],
         definition="a big account is a customer whose lifetime revenue (as revenue is defined) exceeds 5000"),
    dict(name="churned", synonyms=["churned customer", "churned customers", "churn"], maps=["subscriptions"],
         definition="a customer churned when one of their subscriptions ended (ended_at not null) and no other "
                    "subscription of theirs started on that end date or within the 30 days after it"),
    dict(name="partner sales", synonyms=["partner revenue"], maps=["orders"],
         filter="orders.channel = 'partner'",
         definition="partner sales is revenue (as revenue is defined) on orders with channel = 'partner'"),
    dict(name="return rate", synonyms=["refund rate"], maps=["refunds", "orders"],
         definition="return rate = number of completed orders with at least one refund / number of "
                    "completed orders, as a fraction between 0 and 1"),
    dict(name="AOV", synonyms=["average order value"], maps=["orders", "order_items"],
         definition="AOV = revenue (as revenue is defined) / number of completed orders"),
]

# Revenue per order, as defined: net line value excluding internal products, minus that order's refunds.
REV_CTE = f"""rev AS (
  SELECT o.id AS order_id, o.customer_id, o.placed_at, o.channel,
         COALESCE((SELECT {REV_EXPR} FROM order_items oi JOIN products p ON p.id = oi.product_id
                   WHERE oi.order_id = o.id AND p.is_internal = 0), 0)
         - COALESCE((SELECT SUM(r.amount) FROM refunds r WHERE r.order_id = o.id), 0) AS revenue
  FROM orders o WHERE o.status = 'completed')"""
NAIVE_REV = """SELECT ROUND(SUM(oi.qty * oi.unit_price), 2) FROM order_items oi JOIN orders o ON o.id = oi.order_id"""

QUESTIONS = [
    # (question, gold SQL, naive SQL)
    ("What was total revenue?",
     f"WITH {REV_CTE} SELECT ROUND(SUM(revenue), 2) FROM rev", NAIVE_REV),
    ("What was revenue in the west region?",
     f"WITH {REV_CTE} SELECT ROUND(SUM(rev.revenue), 2) FROM rev JOIN customers c ON c.id = rev.customer_id WHERE c.region = 'west'",
     NAIVE_REV + " JOIN customers c ON c.id = o.customer_id WHERE c.region = 'west'"),
    ("What was revenue from orders placed in 2026?",
     f"WITH {REV_CTE} SELECT ROUND(SUM(revenue), 2) FROM rev WHERE placed_at >= '2026-01-01'",
     NAIVE_REV + " WHERE o.placed_at >= '2026-01-01'"),
    ("Which region had the highest revenue?",
     f"WITH {REV_CTE} SELECT c.region FROM rev JOIN customers c ON c.id = rev.customer_id GROUP BY c.region ORDER BY SUM(rev.revenue) DESC LIMIT 1",
     "SELECT c.region FROM order_items oi JOIN orders o ON o.id = oi.order_id JOIN customers c ON c.id = o.customer_id GROUP BY c.region ORDER BY SUM(oi.qty * oi.unit_price) DESC LIMIT 1"),
    ("How many active customers are there?",
     "SELECT COUNT(DISTINCT customer_id) FROM orders WHERE status = 'completed' AND placed_at > date('2026-09-30', '-90 days')",
     "SELECT COUNT(*) FROM customers WHERE is_active = 1"),
    ("How many active customers are in the east region?",
     "SELECT COUNT(DISTINCT o.customer_id) FROM orders o JOIN customers c ON c.id = o.customer_id WHERE c.region = 'east' AND o.status = 'completed' AND o.placed_at > date('2026-09-30', '-90 days')",
     "SELECT COUNT(*) FROM customers WHERE is_active = 1 AND region = 'east'"),
    ("What share of customers are active customers?",
     "SELECT ROUND(1.0 * (SELECT COUNT(DISTINCT customer_id) FROM orders WHERE status = 'completed' AND placed_at > date('2026-09-30', '-90 days')) / (SELECT COUNT(*) FROM customers), 4)",
     "SELECT ROUND(AVG(is_active), 4) FROM customers"),
    ("What fraction of shipments were on-time?",
     "SELECT ROUND(1.0 * SUM(shipped_at <= promised_at) / COUNT(*), 4) FROM shipments WHERE shipped_at IS NOT NULL",
     "SELECT ROUND(1.0 * SUM(shipped_at <= promised_at) / COUNT(*), 4) FROM shipments"),
    ("How many on-time shipments did UPS make?",
     "SELECT COUNT(*) FROM shipments WHERE carrier = 'UPS' AND shipped_at IS NOT NULL AND shipped_at <= promised_at",
     "SELECT COUNT(*) FROM shipments WHERE carrier = 'UPS' AND shipped_at < promised_at"),
    ("Which carrier has the best on-time rate?",
     "SELECT carrier FROM shipments WHERE shipped_at IS NOT NULL GROUP BY carrier ORDER BY 1.0 * SUM(shipped_at <= promised_at) / COUNT(*) DESC LIMIT 1",
     "SELECT carrier FROM shipments GROUP BY carrier ORDER BY 1.0 * SUM(shipped_at < promised_at) / COUNT(*) DESC LIMIT 1"),
    ("How many big accounts are there?",
     f"WITH {REV_CTE} SELECT COUNT(*) FROM (SELECT customer_id FROM rev GROUP BY customer_id HAVING SUM(revenue) > 5000)",
     "SELECT COUNT(*) FROM (SELECT o.customer_id FROM orders o JOIN order_items oi ON oi.order_id = o.id GROUP BY o.customer_id HAVING SUM(oi.qty * oi.unit_price) > 5000)"),
    ("List the big accounts in the north region by name.",
     f"WITH {REV_CTE} SELECT c.name FROM rev JOIN customers c ON c.id = rev.customer_id WHERE c.region = 'north' GROUP BY c.id HAVING SUM(rev.revenue) > 5000 ORDER BY c.name",
     "SELECT c.name FROM orders o JOIN order_items oi ON oi.order_id = o.id JOIN customers c ON c.id = o.customer_id WHERE c.region = 'north' GROUP BY c.id HAVING SUM(oi.qty * oi.unit_price) > 5000 ORDER BY c.name"),
    ("How many churned customers are there?",
     "SELECT COUNT(DISTINCT s.customer_id) FROM subscriptions s WHERE s.ended_at IS NOT NULL AND NOT EXISTS (SELECT 1 FROM subscriptions n WHERE n.customer_id = s.customer_id AND n.started_at > s.started_at AND n.started_at <= date(s.ended_at, '+30 days'))",
     "SELECT COUNT(DISTINCT customer_id) FROM subscriptions WHERE ended_at IS NOT NULL"),
    ("How many churned customers were on the enterprise plan when they churned?",
     "SELECT COUNT(DISTINCT s.customer_id) FROM subscriptions s WHERE s.plan = 'enterprise' AND s.ended_at IS NOT NULL AND NOT EXISTS (SELECT 1 FROM subscriptions n WHERE n.customer_id = s.customer_id AND n.started_at > s.started_at AND n.started_at <= date(s.ended_at, '+30 days'))",
     "SELECT COUNT(DISTINCT customer_id) FROM subscriptions WHERE plan = 'enterprise' AND ended_at IS NOT NULL"),
    ("What were partner sales?",
     f"WITH {REV_CTE} SELECT ROUND(SUM(revenue), 2) FROM rev WHERE channel = 'partner'",
     NAIVE_REV + " WHERE o.channel = 'partner'"),
    ("What were partner sales in the south region?",
     f"WITH {REV_CTE} SELECT ROUND(SUM(rev.revenue), 2) FROM rev JOIN customers c ON c.id = rev.customer_id WHERE rev.channel = 'partner' AND c.region = 'south'",
     NAIVE_REV + " JOIN customers c ON c.id = o.customer_id WHERE o.channel = 'partner' AND c.region = 'south'"),
    ("What is the return rate?",
     "SELECT ROUND(1.0 * (SELECT COUNT(DISTINCT r.order_id) FROM refunds r JOIN orders o ON o.id = r.order_id WHERE o.status = 'completed') / (SELECT COUNT(*) FROM orders WHERE status = 'completed'), 4)",
     "SELECT ROUND(1.0 * (SELECT COUNT(*) FROM refunds) / (SELECT COUNT(*) FROM orders), 4)"),
    ("What is the return rate for web orders?",
     "SELECT ROUND(1.0 * (SELECT COUNT(DISTINCT r.order_id) FROM refunds r JOIN orders o ON o.id = r.order_id WHERE o.status = 'completed' AND o.channel = 'web') / (SELECT COUNT(*) FROM orders WHERE status = 'completed' AND channel = 'web'), 4)",
     "SELECT ROUND(1.0 * (SELECT COUNT(*) FROM refunds r JOIN orders o ON o.id = r.order_id WHERE o.channel = 'web') / (SELECT COUNT(*) FROM orders WHERE channel = 'web'), 4)"),
    ("What is the AOV?",
     f"WITH {REV_CTE} SELECT ROUND(SUM(revenue) / COUNT(*), 2) FROM rev",
     "SELECT ROUND(AVG(t), 2) FROM (SELECT SUM(oi.qty * oi.unit_price) AS t FROM order_items oi GROUP BY oi.order_id)"),
    ("What is the average order value for store orders?",
     f"WITH {REV_CTE} SELECT ROUND(SUM(revenue) / COUNT(*), 2) FROM rev WHERE channel = 'store'",
     "SELECT ROUND(AVG(t), 2) FROM (SELECT SUM(oi.qty * oi.unit_price) AS t FROM order_items oi JOIN orders o ON o.id = oi.order_id WHERE o.channel = 'store' GROUP BY oi.order_id)"),
    ("Which customer generated the most revenue?",
     f"WITH {REV_CTE} SELECT c.name FROM rev JOIN customers c ON c.id = rev.customer_id GROUP BY c.id ORDER BY SUM(rev.revenue) DESC LIMIT 1",
     "SELECT c.name FROM orders o JOIN order_items oi ON oi.order_id = o.id JOIN customers c ON c.id = o.customer_id GROUP BY c.id ORDER BY SUM(oi.qty * oi.unit_price) DESC LIMIT 1"),
    ("How many customers have revenue but are not active customers?",
     f"WITH {REV_CTE} SELECT COUNT(*) FROM (SELECT customer_id FROM rev GROUP BY customer_id HAVING SUM(revenue) > 0) WHERE customer_id NOT IN (SELECT customer_id FROM orders WHERE status = 'completed' AND placed_at > date('2026-09-30', '-90 days'))",
     "SELECT COUNT(DISTINCT o.customer_id) FROM orders o JOIN customers c ON c.id = o.customer_id WHERE c.is_active = 0"),
    ("What was revenue in the 90 days up to 2026-09-30?",
     f"WITH {REV_CTE} SELECT ROUND(SUM(revenue), 2) FROM rev WHERE placed_at > date('2026-09-30', '-90 days')",
     NAIVE_REV + " WHERE o.placed_at > date('2026-09-30', '-90 days')"),
]


def rows(db, sql):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def norm(result):
    """Set of rows, numbers rounded to 2 places, so 0.4231 and 0.42 from ROUND(.,2) vs ROUND(.,4) compare by value."""
    if result is None:
        return None
    out = set()
    for r in result:
        out.add(tuple(round(v, 2) if isinstance(v, float) else v for v in r))
    return out


def matches(pred, gold):
    """Execution match: same row count, and some choice of the prediction's columns equals the gold rows
    (a model may add a helper column such as the rate it ranked by), money within a cent, fractions within 0.006."""
    if pred is None or len(pred) != len(gold):
        return False
    if not gold:
        return True

    def close(a, b):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(a - b) <= (0.011 if abs(b) >= 1 else 0.006)    # money to the cent; a fraction to 2 places
        return a == b

    def same(a, b):
        return all(close(x, y) for x, y in zip(a, b))
    for cols in itertools.permutations(range(len(pred[0])), len(gold[0])):
        rows_p = [tuple(r[i] for i in cols) for r in pred]
        if all(any(same(a, b) for a in rows_p) for b in gold) and all(any(same(a, b) for b in gold) for a in rows_p):
            return True
    return False


def mcnemar_p(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def check(db):
    """Every gold query runs and every naive query gives a different answer on this data."""
    kept, dropped = [], []
    for q, gold, naive in QUESTIONS:
        g = rows(db, gold)
        if not g or g == [(None,)]:
            raise SystemExit(f"gold returned nothing: {q}")
        (dropped if matches(rows(db, naive), g) else kept).append((q, gold, naive))
    return kept, dropped


def catalog(db, with_glossary):
    from schemagate import Catalog
    cat = Catalog(name="planted").bootstrap(f"sqlite:///{db}")
    if with_glossary:
        for g in GLOSSARY:
            cat.concept(g["name"], synonyms=g.get("synonyms", ()), maps=g["maps"], filter=g.get("filter"),
                        definition=g["definition"], source="planted")
    return cat


def main():
    db = os.path.join(tempfile.mkdtemp(prefix="planted-"), "company.db")
    build(db)
    kept, dropped = check(db)
    print(f"questions: {len(QUESTIONS)}, kept {len(kept)} (naive answer differs), dropped {len(dropped)}")
    for q, *_ in dropped:
        print(f"  dropped (naive matches gold on this data): {q}")
    if "--check" in sys.argv:
        for q, gold, _ in kept:
            print(f"  {q}  ->  {sorted(norm(rows(db, gold)))[:3]}")
        return

    from schemagate.answer import UnsafeSQL, generate_sql
    from schemagate.ai.providers import AnthropicProvider
    prov = AnthropicProvider(model=MODEL)
    plain, rich = catalog(db, False), catalog(db, True)
    done = {}
    if OUT.exists():
        for line in OUT.read_text("utf-8").splitlines():
            e = json.loads(line)
            done[(e["q"], e["arm"])] = e
    fh = OUT.open("a", encoding="utf-8")

    def ask(q, gold, arm):
        if (q, arm) in done:
            return done[(q, arm)]["ok"]
        cat = rich if arm == "B" else plain
        sel = cat.select(q, top_k=TOP_K)
        e = {"q": q, "arm": arm, "ok": False, "meanings": len(sel.meanings), "model": MODEL}
        try:
            sql = generate_sql(prov, q, sel.prompt_fragment(), dialect="SQLite")
            e["sql"] = sql
            e["ok"] = matches(rows(db, sql), rows(db, gold))
        except UnsafeSQL:
            e["err"] = "refused"
        except Exception as ex:                                   # noqa: BLE001
            e["err"] = f"{type(ex).__name__}: {str(ex)[:160]}"
        fh.write(json.dumps(e) + "\n")
        fh.flush()
        done[(q, arm)] = e
        return e["ok"]

    t0 = time.time()
    res = {a: [] for a in ("A", "A2", "B")}
    for q, gold, _ in kept:
        for arm in res:
            res[arm].append(ask(q, gold, arm))
    n = len(kept)
    print(f"\nplanted definitions, n={n}, {MODEL}, top_k {TOP_K}  ({time.time()-t0:.0f}s)")
    for arm, label in (("A", "no glossary"), ("A2", "no glossary, repeat"), ("B", "glossary")):
        print(f"  {arm:2} {label:20} {sum(res[arm])}/{n}  ({100*sum(res[arm])/n:.1f}%)")

    def flips(x, y):
        return sum(1 for a, b in zip(x, y) if b and not a), sum(1 for a, b in zip(x, y) if a and not b)
    nb, nc = flips(res["A"], res["A2"])
    print(f"  noise floor A -> A2: +{nb} / -{nc}  p={mcnemar_p(nb, nc):.3f}")
    fb, fc = flips(res["A"], res["B"])
    print(f"  A -> B (glossary):   +{fb} / -{fc}  p={mcnemar_p(fb, fc):.4f}")
    print(f"  per-call log: {OUT}")


if __name__ == "__main__":
    main()
