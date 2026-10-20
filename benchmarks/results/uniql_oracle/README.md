# UniQL, Oracle dialect: schemagate end to end, scored by UniQL's own evaluator

[UniQL](https://github.com/JerryGao818/UniQL) translates BIRD dev's 1,534 questions into 16 SQL dialects.
Its Oracle data is BIRD's 11 dev databases, loaded by its own `migration/oracle/insert_to_oracle.py`. The
score is execution accuracy from its `evaluation/evaluate.py --dialect oracle`.

The run is the `uniql-oracle` GitHub Actions workflow (run 39340551822, 2026-10-19). It uses Oracle Free
23ai in a container, UniQL at e69c6b3, and Gemini 2.5 Flash on OCI Generative AI.

## Result

| | Oracle EX (1,534 questions) |
|---|---|
| **schemagate + Gemini 2.5 Flash, with execution repair** | **69.88** (1,072) |
| schemagate + Gemini 2.5 Flash, first try only | 35.01 (537) |
| UniQL's best published Oracle baseline (Claude Sonnet 4.5) | 49.61 |
| UniQL baseline, DeepSeek-v4-flash | 43.22 |
| UniQL baseline, Gemini 2.5 Pro | 26.14 |

By difficulty (repair run): simple 74.16, moderate 64.01, challenging 61.38.

**These rows were measured differently, so read them with that in mind.** UniQL's published baselines are
models answering once, with no execution feedback. schemagate is a system: it runs the query, and if Oracle
raises an error, the model sees the error and fixes the query, up to 3 times.
- On Oracle, 694 of 1,534 first attempts raised an error, mostly from quoted upper-case identifiers and
  Oracle-specific syntax.
- 535 of those were fixed into correct answers.
- The "first try only" row is exact, not estimated. It counts the questions answered correctly with no
  repair, because a query that errors scores zero.

So:
- **With repair,** schemagate on a light model is 20 points above the best published model.
- **On a first try,** it is below the bare models.

The repair loop is the difference. Teaching schemagate's prompt Oracle's quoting and syntax should raise the
first-try number.

## What runs, per question

`benchmarks/uniql_oracle.py`:
1. schemagate reflects that database's Oracle user, with sampled values for short text columns.
2. It selects the tables the question needs (top 8).
3. The prompt gets their DDL plus BIRD's column descriptions for those tables, and the question with its
   evidence hint.
4. The model writes one Oracle query.
5. A database error goes back to the model, up to 3 times.
6. If the model declines (22 times), it is asked once for its best reading.

The gold SQL is never shown to the model. The runner copies it into the output file only because UniQL's
evaluator reads it from there.

## Checks before the paid run

All of these ran free on GitHub Actions:
- Every gold query was executed: 1,530 of 1,534 run. Four fail with `ORA-01791` (questions 514, 1123, 1125,
  1263). That is UniQL's data, and it affects every entry equally.
- A dry run put the gold SQL through the runner and the evaluator as the prediction, and scored 100.00.

## Notes

- **UniQL's users look like Oracle's own.** UniQL's loader creates each user with `_ORACLE_SCRIPT=true`,
  which marks it Oracle-maintained. schemagate skips Oracle-maintained schemas by default, so the runner
  names the user's own schema explicitly.
- **The evaluator upper-cases the whole SQL,** string literals included, for the gold and the prediction
  alike, before running both.
- **The evaluator needs one worker.** Run with 4 workers, Oracle Free refused connections and most queries
  failed. With 1 worker the dry run scores 100.
- `gemini-2.5-flash_oracle.json` has each prediction with `repaired`, `declined` and `correct`.
  `*.evaluator.txt` is UniQL's summary output.
