# BIRD Mini-Dev (2026 update): execution-guided repair + Claude Opus 5.5

BIRD [updated Mini-Dev on 2026-10-28](https://huggingface.co/datasets/birdsql/bird_mini_dev): 500 aligned
questions in SQLite, MySQL and PostgreSQL, revised annotations, 460 of them "challenging". Results from
the previous version are now in BIRD's "Mini Dev Legacy" table (our earlier run is in
[`../bird_minidev/`](../bird_minidev/)).

Every number here comes from Mini-Dev's own `evaluation/evaluation_ex.py` (strict EX), run on the
prediction files in this folder. The `*.ex.txt` files are its output.

## Results (EX, all 500 questions per dialect)

| Setup | SQLite | MySQL | PostgreSQL | Overall |
|---|---|---|---|---|
| **Execution-guided repair + Claude Opus 5.5** | **93.40** | **86.20** | 87.80 | **89.13** |
| GPT-6.1 Sol (BIRD's board, 2026-10-28) | 88.00 | 84.80 | **89.00** | 87.27 |
| Claude Opus 5.5 (BIRD's board, 2026-10-28) | 90.00 | 84.40 | 87.00 | 87.13 |

By difficulty (simple / moderate / challenging; 8 / 32 / 460 questions): SQLite 75.00 / 90.62 / 93.91,
MySQL 75.00 / 87.50 / 86.30, PostgreSQL 75.00 / 84.38 / 88.26.

SQLite scored 93.40 or 93.60 on repeated evaluator runs over the same predictions file (the evaluator's
per-query timeouts); the table uses the lower number, and the `.ex.txt` here is the last run.

## What was run

[`../../bird_minidev_2026.py`](../../bird_minidev_2026.py):

1. BIRD's **fixed baseline prompt**, unchanged (`baseline_inference/mini_dev_<dialect>.jsonl`, field
   `prompt`: full schema, BIRD's instructions), to Claude Opus 5.5 at the default effort (medium).
2. The returned SQL is run read-only. On an error, the error goes back to the model for a corrected
   query (up to 3 tries).
3. If the query runs but returns no rows or only NULLs, the model is asked once to re-check filter values
   and joins; the new query is kept only if it returns data.

Gold SQL is never shown to the model. One model, no voting, no fine-tuning, no training examples.

## What this is not

**It does not use schemagate's table selection.** We measured it first: on these small databases,
selecting tables lost to showing the whole schema in BIRD's prompt (44 SQLite questions: schemagate
selection 36 correct, plain Opus with BIRD's prompt 40). schemagate's job is large schemas, where it
cuts prompt tokens; Mini-Dev's databases are small enough to send whole.

The gain over BIRD's own Opus 5.5 row comes from the execution loop and from run-to-run variation of
the model; on a 44-question pilot the loop alone did not beat a plain run (38 vs 40), so read the
+2.0 overall as "this loop at least matches the plain model, and this run came out ahead", not as a
measured effect of the loop.

## Cost

$43.95 of Claude API usage for the 1,500 questions (about $0.03 per question), from the API's reported
token usage.

## Reproduce

- Data: `birdsql/bird_mini_dev` on Hugging Face (`data/` and `baseline_inference/`), databases from
  Mini-Dev's `dev_databases` (byte-identical to the previous release); MySQL 8.4 and PostgreSQL 16
  loaded with Mini-Dev's dumps.
- Score: `evaluation_ex.py --sql_dialect SQLite|MySQL|PostgreSQL` with the gold SQL from `data/`,
  one line per question in `question_id` order (`<SQL>\t<db_id>`), `--meta_time_out 60`.
