# BIRD-CRITIC 1.0 PostgreSQL: 58.11% with a Claude Code agent

[BIRD-CRITIC 1.0 PostgreSQL](https://huggingface.co/datasets/birdsql/bird-critic-1.0-postgresql) has 530 real
PostgreSQL user issues. Each gives a database, the user's problem and their broken SQL, and the system
returns corrected SQL. A task counts as solved only if the prediction passes the task's test cases.

| | result |
|---|---|
| **This run (Claude Code agent, Claude Opus 5.5)** | **58.11% (308/530)** |
| Leaderboard #1 on 2026-11-27 (AlphaData+GLM-4.7) | 56.79 |
| Leaderboard #2 (DivSkill-SQL) | 54.53 |
| Leaderboard #3 (TRACE) | 53.40 |
| SQL-ACT + Claude-Opus-4-6 (BIRD's agent baseline) | 45.47 |
| BIRD's gold SQL on our local databases (setup check) | 98.49% (522/530) |

By category: Management 79.5% (70/88), Personalization 55.0% (83/151), Query 53.3% (155/291).

This run does not use schemagate's table selection. The agent gets the full schema, as in BIRD's
baseline prompt.

## How it works and how it was scored

It's the same agent, tool and scoring as the [Flash run](../bird_critic_flash_agent/README.md), run on the
530-task set with BIRD's `post_schema.jsonl` schemas:
- **The agent:** one `claude -p` call per task, with one SQL tool on a rolled-back copy of the task's database. It never sees `sol_sql` or the test cases. Median 3 turns and 32 seconds per task.
- **Scorer:** BIRD's official evaluator in `--mode pred`, with the solution SQL and test cases BIRD sends on request. The code and the Windows evaluator patch are in `../bird_critic_flash_agent/code/`.

## Files

- `predictions.jsonl`: `instance_id` and `pred_sqls` per task.
- `agent_responses.jsonl`: the agent's final reply per task.
- `eval_status.jsonl`: pass or fail per task.
- `eval_report.txt`: the evaluator's report for this run.
- `gold_check_report.txt`: the evaluator's report for BIRD's gold SQL on the same setup.

The solution SQL and test cases are BIRD's and are not included.
