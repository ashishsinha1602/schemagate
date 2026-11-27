# Effi-SQL (BIRD): a Claude Code agent that rewrites slow PostgreSQL queries

[Effi-SQL](https://bird-critic.github.io/) is BIRD's SQL efficiency benchmark. It has 300 slow PostgreSQL
queries (238 on TPC-H SF3, 62 on three BIRD-Interact databases). For each one you return a rewrite that gives
the same result and runs faster.

**This entry does not use schemagate's schema selection.** It is the schemagate team's SQL-optimizer agent:
Claude Opus 5.5 running in Claude Code, with one tool that runs SQL against the task database. It is in this
repo because it is our submission, not because schema selection is part of it.

## Result

Scored with the benchmark's own evaluator (`diff_sql/evaluation/eval_postgresql_execution.py`,
`EVAL_SQL_MODE=end2end`), on our machine. Leaderboard numbers are BIRD's to verify.

| metric | ours | #1 on the leaderboard (GPT-5.5-Xhigh) |
|---|---|---|
| R-VES | **91.58** | 82.42 |
| Coverage@2x | **78.67** | 61.00 |
| GMS (geometric mean speedup, correct answers) | **4.4104** | 3.5977 |
| correct (same result as the original) | 294/300 | |

| database | tasks | correct | R-VES |
|---|---|---|---|
| TPC-H SF3 | 238 | 232 | 91.70 |
| polar_equipment | 14 | 14 | 92.86 |
| robot_fault_prediction | 22 | 22 | 90.91 |
| solar_panel | 26 | 26 | 90.38 |

The 6 tasks scored as not correct:

- 216, 77, 27, 9: the evaluator timed out (300 s) running the benchmark's **original** query on our VM (`gt_timeout`), so these could not be scored here.
- 166: the agent returned the original query unchanged. It uses `ARRAY_AGG` without `ORDER BY`, so its output order varies between runs and it does not reliably match itself.
- 53: scored before the parenthesis fix below; the fixed answer is in `predictions.jsonl` but was not re-scored.

## How it works

`code/effi_cc.py` runs one `claude -p` agent per task (Claude Opus 5.5, Claude Code, effort high). The prompt
holds the original query and its `EXPLAIN ANALYZE` from the benchmark file. The benchmark's reference rewrite
(`optimized_sql`) and its timings are never shown to the agent.

The agent has one tool, `code/effi_sql.py`:

- `run`: run SQL (schema, indexes, statistics, value distributions)
- `explain`: `EXPLAIN (ANALYZE, BUFFERS)`
- `compare`: checks that a rewrite returns exactly the original's rows (row count plus an order-insensitive
  hash computed inside PostgreSQL) and times it with PostgreSQL's own `Execution Time`, as the evaluator does

Everything runs inside a transaction that is rolled back, so the agent cannot add indexes or change data. Only
the query text changes. If no rewrite is both identical and faster, the agent returns the original.

Two passes. After pass 1, `code/self_check.py` re-timed every answer against the **original** query with the
same tool. Tasks under 2x got a second agent, which saw its earlier rewrite and that measured speedup. A
pass-2 rewrite replaced pass 1 only if it was identical and more than 10% faster by our own measurement. Task
selection never used the evaluator's output or the reference rewrite.

Two answers began with `(` (a parenthesised `UNION ALL`). The evaluator finds the SQL starting at the first
`WITH`/`SELECT`, which drops that parenthesis, so both were wrapped as `SELECT * FROM (...) q`. Same rows.

## Setup

- Databases: the benchmark's own Docker setup (`docker/compose/tpch.yml`, `smalldb.yml`), TPC-H SF3 generated
  with DuckDB's `dbgen`, on an Oracle Cloud VM (AMD E5, 16 OCPU / 128 GB). Containers got a larger `/dev/shm`
  (16 GB / 8 GB); Docker's 64 MB default made parallel hash joins in the reference queries fail.
- Agents ran on a laptop through an SSH tunnel; 8 to 12 at a time.
- Scoring: the evaluator's default settings (3 timed runs, interleaved), split over 6 evaluator processes
  for time; the 8 tasks hit by timeouts or the parenthesis issue were then re-scored alone. Timings are from our machine, not BIRD's.

## Files

- `predictions.jsonl`: `id`, `db`, `difficulty` and `prediction` (a ```sql block) for all 300 tasks. Join
  with the benchmark file on `id` to get the evaluator's input; BIRD received the full records.
- `eval.jsonl`: the evaluator's per-task output (`is_match`, `speedup`, timings)
- `code/`: the agent runner, the SQL tool, the self-check and the metrics script
