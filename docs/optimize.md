# Make a slow query faster, with proof it returns the same rows

`schemagate.optimize` takes a slow read and returns a faster one, but only a
rewrite it has checked against the database: same rows, and measurably faster.
If nothing passes, you get your original query back.

```python
from sqlalchemy import create_engine
from schemagate.ai import AnthropicProvider
from schemagate.optimize import optimize

engine = create_engine("postgresql+psycopg://reader@replica/app")
r = optimize(engine, slow_sql, AnthropicProvider(model="claude-sonnet-4-5"))

print(r.speedup, r.original_ms, r.optimized_ms)   # 6.4  1830.2  285.9
print(r.sql)                                       # the rewrite (or the original)
for a in r.attempts:                               # every candidate and why it won or lost
    print(a.identical, a.speedup, a.new_literals, a.error)
```

## What "same rows" means

`compare(engine, original, candidate)` runs both and compares the results:

- **PostgreSQL:** inside the server. A row count plus an order-insensitive sum of
  row hashes, so a million-row result never leaves the database. When the
  original has a top-level `ORDER BY`, the order is compared as well.
- **Other databases:** in Python, up to 200,000 rows. Past that it refuses to
  call the results identical rather than guess.

The rows are never returned, only whether they match.

## How it is timed

On PostgreSQL, the server's own `Execution Time` from `EXPLAIN (ANALYZE, FORMAT
JSON)`: one warm-up run, then the best of two. That is the measure BIRD's
Effi-SQL benchmark uses. Other databases are timed on the wall clock, fetch
included. A rewrite must be at least 10% faster (`min_speedup=1.1`) to count;
smaller differences are noise.

## Safety

- Every statement, the original and each candidate, must be a single read
  (`check_read_only`): writes, DDL and stacked statements are refused.
- Everything runs inside a transaction that is always rolled back, declared
  `READ ONLY` on PostgreSQL, under a statement timeout. Only the query text
  changes: no index, no data, no setting survives the call.
- Pass `check=` to add your own gate. The MCP server passes its caller-scope
  check, so a rewrite can never read a table the caller may not see.

## Two things to know before you use the answer

**"Same rows" is about the data as it is now.** A rewrite can match today and
be wrong after the next insert. The usual way is a constant taken from the
data, such as splitting a scan at `WHERE id < 6000033`. The model is told never
to do that. Any constant a rewrite adds that the original did not have (other
than 0 and 1) is listed in `new_literals`, and such a rewrite is never chosen.
Review a rewrite before it replaces production SQL.

**Every check runs the slow query again.** `optimize` stops after `rounds`
model calls (default 3), at `target_speedup` (10x), or after `time_budget`
seconds (600). Point it at a replica if the original is expensive.

## In the MCP server

Three tools, all read-only and all scoped to the caller like `run_query`:

| tool | needs a server model | what it does |
|---|---|---|
| `explain_query` | no | the plan, with real timings on PostgreSQL |
| `compare_queries` | no | same rows? which is faster? which constants were added? |
| `optimize_query` | yes (`SCHEMAGATE_MCP_PROVIDER`, `SCHEMAGATE_MCP_MODEL`) | the whole loop on the server |

With no model on the server, your assistant does the loop itself: it reads the
plan from `explain_query`, writes a rewrite, and checks it with
`compare_queries`.

Settings: `SCHEMAGATE_OPTIMIZE_TIMEOUT` (seconds per statement, default 60) and
`SCHEMAGATE_OPTIMIZE_BUDGET` (seconds per `optimize_query` call, default 300).

## Databases

PostgreSQL has full support: in-server comparison and server-side timing.
SQLite, MySQL, SQL Server and Oracle work with wall-clock timing and in-Python
comparison (up to 200,000 rows).
