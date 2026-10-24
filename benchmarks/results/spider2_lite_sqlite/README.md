# Spider 2.0-lite, the SQLite questions: schemagate end to end, scored by Spider 2.0's own evaluator

[Spider 2.0-lite](https://github.com/xlang-ai/Spider2) has 547 text-to-SQL tasks over real warehouses: 214 on
BigQuery, 198 on Snowflake and 135 on SQLite databases that run offline (`local000`..`local3xx`, 30 databases,
up to 48 tables each). This folder is the **SQLite 135 only**. Every number comes from Spider 2.0's own
`evaluation_suite/evaluate.py --mode sql`, run on the `.sql` files in this folder; the `*.eval.txt` files are its
output and the `*.correct_ids.csv` files are the question ids it marked correct.

## Results (execution accuracy, 135 questions)

| Setup | Correct | EX |
|---|---|---|
| **schemagate + Claude Sonnet 5.5, one query per question** | **97** | **71.9** |
| schemagate + Gemini 2.5 Flash, one query per question | 53 | 39.3 |
| control: full schema (no schemagate) + Gemini 2.5 Flash | 55 | 40.7 |
| schemagate + Claude Opus 5.5, one query per question (run 2026-10-23) | 91 | 67.4 |

Opus 5.5 scored **below** Sonnet 5.5 on these questions with the identical pipeline (gained 12, lost 18
questions against the Sonnet run). The predictions are in `claude-opus-5-5/`, the evaluator's output in
`claude-opus-5-5.eval.txt`.

For comparison, the best published number on this same 135-question subset that I know of is FlexSQL
(COLM 2026, [arXiv 2605.02815](https://arxiv.org/abs/2605.02815)): **57.78 Pass@1** and 64.44 Majority@8 with
gpt-oss-120b, an agent that plans, writes SQL or Python, and backtracks. The models differ, so this is not a
same-model comparison; it says where one query from schemagate's selection lands against a multi-sample agent.

What the runs were, per question (`benchmarks/spider2_local.py`):
1. schemagate reflects the SQLite database, sampling short distinct values so the model sees real casing;
2. it selects the tables the question needs (`top_k=12`; the median database here has 12 or more tables, and
   the selection used 4 to 19 tables);
3. the prompt gets those tables' DDL, the question's external-knowledge document when Spider 2.0 provides one,
   and the question;
4. the model writes **one** SQLite query; if SQLite raises an error the model sees the error and the query
   and tries again, at most 3 times (Claude: 3 of 135 questions needed a repair; Flash: 8);
5. if the model says three times that the selected tables cannot answer, no file is written and the question
   counts as wrong (Claude: 2; Flash: 6).

Nothing reads the gold SQL or the gold results. The evaluator's "Total examples" is the number of `.sql` files it
found (133 or 129), so its printed "Final score" is slightly higher than the numbers above, which divide by all
135; its "Real score" divides by all 547 Spider 2.0-lite tasks, which these runs did not attempt.

## What to read with care

- **This is one third of Spider 2.0-lite.** A leaderboard row needs all 547 tasks; the BigQuery and Snowflake
  thirds need credentials this run did not have. Nothing here is a leaderboard placing.
- **The light model does not get there.** Gemini 2.5 Flash scores half of Claude on these questions, and the
  full-schema control is within two questions of the schemagate run, so with Flash the table selection neither
  helps nor hurts here. The same control with Claude was started and not finished (68 of 135), so whether the
  selection adds points on Spider 2.0 with Claude is **not measured**.
- Single runs, no repeats. Treat the numbers as ±2 questions.
- Runs of 2026-10-16; scored 2026-10-23. Spider 2.0's gold results for the SQLite questions are all released,
  so this subset is fully scorable locally.

## Reproducing

```bash
# Spider 2.0 sparse clone + the local SQLite databases (see spider2-lite/evaluation_suite/README.md)
python benchmarks/spider2_local.py --spider2 <Spider2>/spider2-lite --db-dir <dir with *.sqlite> \
    --out out/claude --model claude-sonnet-5-5 --provider anthropic
python benchmarks/spider2_local.py --spider2 <Spider2>/spider2-lite --db-dir <dir with *.sqlite> \
    --out out/flash --model google.gemini-2.5-flash --provider oci
python benchmarks/spider2_local.py ... --out out/flash_full --model google.gemini-2.5-flash --provider oci --full-schema
cd <Spider2>/spider2-lite/evaluation_suite && python evaluate.py --mode sql --result_dir <out dir>
```
