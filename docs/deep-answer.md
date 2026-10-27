# deep_answer: look at the data before answering

`answer` writes one query from the schema. That fails when the schema can't
say what's in it. A question asks for "customers in Prague", but the column
holds `Praha`. A status that reads `'closed'` in the question is stored as
`'C'`. A count that should be 40 comes back 0. The model never saw a row, so
it guesses, the query runs, and the answer is wrong.

`deep_answer` (MCP) lets the model look first, the way an analyst would.

## How it works

Each model call is one step, and the model picks what it is:

- **EXPLORE**: a small read (`SELECT DISTINCT district FROM ...`). The model
  sees the first 10 rows.
- **TABLES**: ask for more of the schema. The new tables come from the same
  scoped selection as everything else, so this can never add a table the
  caller may not see.
- **FINAL**: the query that answers the question.
- **INSUFFICIENT**: the data can't answer it, and the model says why.

When the database rejects a query, the model gets the error back. An empty
FINAL, or a single row of zeros or NULLs, is sent back to the model once,
asking whether that is really the answer. When the step budget runs out
(default 6, at most 12), the server makes one last plain query, informed by
what the explores turned up.

**Every step's SQL goes through `run_query`.** That means the read-only
check, the caller's scope check and an audit line, once per step. A deep
answer can't read anything that `run_query` would refuse.

## Adaptive: deep only when needed

`mode="adaptive"` is the default. The server writes a plain query first and
repairs it up to twice if the database rejects it. It switches to the step
loop only when that query still fails, or returns nothing, or returns only
zeros. Most questions are answered in one call. `mode="deep"` always uses the
step loop.

## Turning it on

Explore rows go to the model provider, so `deep_answer` is off by default:

```bash
SCHEMAGATE_MCP_DEEP=1 schemagate-mcp --url postgresql+psycopg://... --provider <provider> --model <model-id>
```

The server refuses to start with `SCHEMAGATE_MCP_DEEP=1` if no model is
configured. `health` shows `"deep": true` when the tool is on.

| Setting | Default | What it does |
|---|---|---|
| `max_steps` (tool argument) | 6 | Model calls in the step loop, at most 12 |
| `mode` (tool argument) | `adaptive` | `adaptive` or `deep` |
| `SCHEMAGATE_DEEP_EXPLORE_SECONDS` | 10 | Time limit for each explore query (not for FINAL) |

Explore results are cached for 5 minutes. The cache key is the caller, their
roles, the catalog version and the SQL. A cache entry made for one caller is
never served to another, and a catalog refresh empties the cache. Final
queries are never cached and have no time limit beyond your database's own.

## Results

All results below use Gemini 2.5 Flash, a light model, with 20 questions per
database from the BIRD dev set. Scores are execution accuracy, and the p
values come from paired exact tests.

| Setup | Plain | Deep | Adaptive |
|---|---|---|---|
| SQLite, 11 databases (220 questions) | 36.8 | 54.1 | **54.5** (1.68 calls per question) |
| Postgres, all 11 in one 75-table schema (215) | 22.3 | **39.5** | |
| Oracle Free, 11 databases | 32.7 | **48.6** | |
| Spider 2.0-lite SQLite, 135 tasks, with rules | 45.2 (plain plus repairs) | | 42.2 (tie, p = 0.48) |

On SQLite, deep's gain over plain is significant (p < 1e-4), and about 90% of
the wins come from EXPLORE steps, where the model sees real values. BIRD also
ships an "evidence" hint for each question. Deep with no hints (54.1) comes
close to plain with those hints (58.2).

On Oracle, deep did worse than plain on 3 of the 11 databases. On the hardest
Spider 2 tasks, adaptive ties plain plus repairs: it does not beat it.
