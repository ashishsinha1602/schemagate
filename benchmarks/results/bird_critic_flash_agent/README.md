# BIRD-CRITIC 1.0 Flash: 63.00% with a Claude Code agent

[BIRD-CRITIC 1.0 Flash](https://huggingface.co/datasets/birdsql/bird-critic-1.0-flash-exp) has 200 real
PostgreSQL user issues. Each gives a database, the user's problem and their broken SQL, and the system
returns corrected SQL. A task counts as solved only if the prediction passes the task's test cases.

| | result |
|---|---|
| **This run (Claude Code agent, Claude Opus 5.5)** | **63.00% (126/200)** |
| Leaderboard #1 on 2026-11-27 (AlphaData+GLM-4.7) | 61.0 |
| Leaderboard #2 (Button) | 58.5 |
| SQL-ACT + Claude-Opus-4-6 (BIRD's agent baseline) | 52 |
| BIRD's gold SQL on our local databases (setup check) | 98.00% (196/200) |

By category: Management 84.0% (42/50), Personalization 59.4% (38/64), Query 54.7% (35/64),
Efficiency 50.0% (11/22).

This run does not use schemagate's table selection. The agent gets the full schema, as in BIRD's
baseline prompt. It sits in this repo as part of the same benchmark work.

## How it works

One `claude -p` call per task (`--model opus --effort high`, at most 20 tool calls). The agent sees what
BIRD's baseline prompt contains: the schema with sample rows, the user's issue and the broken SQL. It has
one tool, `critic_sql.py`, which runs SQL on the task's own copy of the database (cloned from BIRD's
template, with the task's `preprocess_sql` applied) inside a transaction that is always rolled back. The
agent ends with its corrected SQL in ```` ```sql ```` blocks, and BIRD's own extractor
(`baseline/src/util.py: sql_response_extract`) turns the reply into `pred_sqls`. The agent never sees
`sol_sql` or the test cases. Median 3 turns and 32 seconds per task.

## How it was scored

- **Scorer:** BIRD's official evaluator (`evaluation/src/wrapper_evaluation_postgresql.py --mode pred`), using the solution SQL and test cases BIRD sends on request.
- **Databases:** a local PostgreSQL loaded the way BIRD's `init-databases_postgresql.sh` loads its Docker image.
- **Setup check:** BIRD's own gold SQL scored 98.00% on that setup.
- **Windows changes to the evaluator:** in `code/evaluator_windows.patch`, and none of them affects how a task is judged.
  - The host and port point at the local database.
  - Each result file is now deleted only after it is closed. On Windows the original deleted it while it was still open, which threw away every result.
  - The evaluator runs its own Python interpreter.

## Files

- `predictions.jsonl`: one row per task, with `instance_id` and `pred_sqls`.
- `agent_responses.jsonl`: the full agent reply per task (`prompt_flow`).
- `eval_status.jsonl`: pass or fail per task.
- `eval_report.txt`: the evaluator's report for this run.
- `gold_check_report.txt`: the evaluator's report for BIRD's gold SQL on the same setup.
- `code/`: the agent runner, its SQL tool, the database loader and the evaluator patch.

The solution SQL and test cases are BIRD's and are not included.
