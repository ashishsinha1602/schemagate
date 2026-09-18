"""Complex SQL, end to end, against the live 1,200-object schema.

Retrieval recall says the right tables were selected. It does not say the model
could write the query, and a selection that is technically correct but missing
one join table produces SQL that does not run -- which is the failure users
actually meet.

So this closes the loop: schemagate picks the tables, a model writes the SQL
from that prompt fragment alone, and the SQL is executed against the real
Oracle Autonomous Database the fixture was built on. Three outcomes are
recorded separately, because they fail for different reasons:

    generated   the model produced something that parsed as read-only SQL
    ran         Oracle accepted and executed it
    returned    it came back with at least one row

`returned` is reported but never treated as the headline. A correct query over
a sparsely seeded fixture can legitimately return nothing, and counting empty
results as failures would punish the query for the data.

Every question here needs more than one table AND more than a SELECT: joins,
aggregation, HAVING, anti-joins, window functions. A question answerable by
`SELECT * FROM one_table` would tell us nothing this harness is for.

    ANTHROPIC_API_KEY=... python benchmarks/complex_sql_1200.py
"""
from __future__ import annotations

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fixture_1200 as F                                       # noqa: E402

#: (question, what makes it hard). The second element is not used for scoring;
#: it is there so a reader can tell at a glance that the set is not a pile of
#: single-table lookups wearing long sentences.
COMPLEX_SQL = [
    ("For each contact, how many invoices are unpaid and what is the total "
     "outstanding amount, for contacts with more than one unpaid invoice",
     "3 tables, LEFT JOIN + anti-join, GROUP BY, HAVING, SUM"),

    ("Which contacts have a tag but no note recorded against them",
     "anti-join across two child tables of the same parent"),

    ("Top 5 contacts by email opens in the last 30 days, with their company",
     "join to a 176-column fact table, ORDER BY, row limiting"),

    ("Total payments per contact, ranked, showing each contact's share of "
     "the overall payment total",
     "aggregate + window function over the aggregate"),

    ("Employees whose department has more than the average number of "
     "employees per department",
     "self-referencing aggregate compared against an aggregate of aggregates"),

    ("Invoices where the refunded amount is more than half the invoice amount",
     "join with a computed comparison between two tables"),

    ("For each contact, the most recent invoice and whether it was paid",
     "per-group latest row, which needs a window or a correlated subquery"),

    ("Count of contacts by status, together with how many of each status "
     "have at least one payment",
     "conditional aggregation across a join"),
]


def _fragment(cat, question, top_k):
    """What the model is allowed to see. Nothing else is passed."""
    sel = cat.select(question, top_k=top_k)
    return sel, sel.prompt_fragment()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="claude-sonnet-4-5")
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--show-sql", action="store_true")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set -- nothing would be measured.",
              file=sys.stderr)
        return 2

    import pickle
    import pathlib
    from schemagate import Catalog
    from schemagate.ai import providers as _p
    from schemagate.answer import (UnsafeSQL, check_read_only, generate_sql,
                                   run_sql)

    F._load_env()
    cache = pathlib.Path(os.environ.get("SGBENCH_CACHE", ".sgbench_docs.pkl"))
    cat = Catalog(name="sgbench")
    if cache.exists():
        cat.add_all(pickle.loads(cache.read_bytes()))
    else:
        cat.bootstrap(F.live_engine(), schemas=[F.SCHEMA])
        cache.write_bytes(pickle.dumps(list(cat._docs.values())))
    cat.index()
    print(f"catalog: {len(cat._docs)} objects\n")

    engine = F.live_engine()
    provider = _p.AnthropicProvider(model=args.model)
    print(f"model  : {provider.name}   top_k={args.top_k}\n")

    generated = ran = returned = 0
    failures = []
    t0 = time.time()

    for question, why in COMPLEX_SQL:
        sel, fragment = _fragment(cat, question, args.top_k)
        tables = [d.name for d in sel.objects]
        print(f"Q: {question[:72]}")
        print(f"   hard because: {why}")
        print(f"   selected    : {tables[:6]}")
        try:
            sql = generate_sql(provider, question, fragment, dialect="oracle")
            sql = check_read_only(sql)
            generated += 1
        except (UnsafeSQL, Exception) as e:                     # noqa: BLE001
            print(f"   GENERATE FAILED: {type(e).__name__}: {str(e)[:110]}\n")
            failures.append((question, "generate", str(e)[:200]))
            continue
        if args.show_sql:
            print("   " + sql.replace("\n", "\n   ")[:900])
        try:
            cols, rows = run_sql(engine, sql, limit=20)
            ran += 1
            returned += bool(rows)
            print(f"   RAN, {len(rows)} row(s), columns {list(cols)[:5]}\n")
        except Exception as e:                                   # noqa: BLE001
            msg = str(e).strip().splitlines()[0][:150]
            print(f"   DID NOT RUN: {msg}\n")
            failures.append((question, "execute", msg))

    n = len(COMPLEX_SQL)
    print("-" * 64)
    print(f"generated read-only SQL : {generated}/{n}")
    print(f"executed on Oracle      : {ran}/{n}")
    print(f"returned at least a row : {returned}/{n}   (not the headline --"
          f" an empty result can be correct)")
    print(f"{time.time() - t0:.0f}s")
    if failures:
        print("\nfailures:")
        for q, stage, msg in failures:
            print(f"  [{stage}] {q[:60]}\n      {msg}")
    # The bar is execution: SQL that does not run is the failure this whole
    # library exists to prevent.
    return 0 if ran == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
