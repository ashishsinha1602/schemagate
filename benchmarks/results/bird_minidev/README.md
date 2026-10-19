# BIRD Mini-Dev: schemagate end to end, scored by BIRD's own evaluator

[BIRD Mini-Dev](https://github.com/bird-bench/mini_dev) is 500 text-to-SQL questions over 11 databases.
They come in SQLite, PostgreSQL and MySQL versions, and are scored by execution accuracy (EX): the
predicted query's result must equal the gold query's result. Every number here comes from Mini-Dev's own
`evaluation/evaluation_ex.py`, run on the prediction files in this folder. The `*.ex.txt` files are its
output.

## Results (EX, all 500 questions)

The headline model is **Gemini 2.5 Flash**, a light model (OCI Generative AI, on demand).

| Setup | SQLite | PostgreSQL | MySQL |
|---|---|---|---|
| **schemagate + Gemini 2.5 Flash, one query per question** | **63.60** | 55.60 | 54.80 |
| **schemagate + Gemini 2.5 Flash, step-by-step reasoning + value lookup** | 62.20 | **56.20** | **55.60** |
| Mini-Dev leaderboard #1 on 2026-10-19 | 75.60 (Jitto Build) | 65.80 (Ontology2SQL) | 49.20 (TA + GPT-4) |

By difficulty (simple / moderate / challenging; 148 / 250 / 102 questions):

| Setup | SQLite | PostgreSQL | MySQL |
|---|---|---|---|
| Flash, one query | 74.3 / 60.0 / 56.9 | 66.9 / 54.0 / 43.1 | 69.6 / 52.4 / 39.2 |
| Flash, reasoning + values | 75.0 / 59.2 / 51.0 | 68.2 / 54.8 / 42.2 | 68.9 / 56.0 / 35.3 |

So, with a light model, schemagate is above the best published MySQL result (TA + GPT-4, 49.20). It is
not first on SQLite or PostgreSQL.

### With the model the current leaders use

| Setup | SQLite | PostgreSQL | MySQL |
|---|---|---|---|
| **schemagate + Claude Opus 5.5, one query per question** | **81.00** | **72.60** | **72.40** |
| schemagate + Claude Haiku 5.5, one query per question | 61.80 | 55.00 | 54.40 |

The #1 entries on 2026-10-19, and the model each used:

| Dialect | #1 | EX | Model |
|---|---|---|---|
| SQLite | Jitto Build (JamLabs) | 75.60 | listed as "UNK" on BIRD. JamLabs lists the same product as "Jitto Build (Claude Opus 5.5, high)" on [LiveSQLBench](https://livesqlbench.ai/) |
| PostgreSQL | Ontology2SQL (DeepLethe) | 65.80 | `deepseek-v4-flash`, as an agent with up to 12 steps per question ([RESULTS.md](https://github.com/deeplethe/ontology2sql/blob/main/RESULTS.md)) |
| MySQL | TA + GPT-4 (HKU) | 49.20 | GPT-4 |

What that means:
- **SQLite:** schemagate with the same model as the leader scores 81.00 against 75.60.
- **MySQL:** schemagate beats the leader even with a lighter model (Flash 54.80–55.60, against GPT-4 at 49.20).
- **PostgreSQL:** the leader's 65.80 is a light model running as an agent. schemagate's single query beats it with Opus (72.60), but not with a light model (Flash 56.20, Haiku 55.00).

Reproduction: the script as merged on `main` was re-run with Claude Opus 5.5 on SQLite, and scored
**80.20** (simple 89.86, moderate 77.60, challenging 72.55) against the 81.00 above. Opus does not
answer identically run to run. One question in the re-run had no SQL because of a single API error.
The predictions and evaluator output are `claude-opus-5-5_plain_sqlite_rerun.*`.

Evaluator variance: `evaluation_ex.py` gives a query 30 s. Scored while other evaluators were running,
Haiku on PostgreSQL came out 54.60. Scored alone, it came out 55.00, which is what the `.ex.txt` file
shows. Every number in this page is from a run scored alone.

## What runs, per question

`benchmarks/bird_minidev.py`. Nothing in it reads the gold SQL.

1. schemagate reflects the question's database, including a few sampled values for short text columns.
   For PostgreSQL and MySQL, Mini-Dev's dumps are loaded into one database, and the catalogue holds only
   that question's tables (from `dev_tables.json`).
2. `Catalog.select` picks the tables the question needs (top 8). The prompt gets their DDL plus BIRD's own
   column descriptions (`database_description/*.csv`) for those tables only.
3. The question goes in with its BIRD "evidence" hint. That is BIRD's standard setting, the one its
   leaderboards report.
4. The model writes one query. If it says the tables cannot answer, it is asked once for its best reading,
   since every question here has an answer. If the database raises an error, the model sees the error and
   tries again, up to 3 times.
5. *Reasoning + values only:*
   - The question's words and phrases are looked up, as exact case-insensitive matches, in the text columns
     of that database's tables. Matches are shown to the model with their stored spelling.
   - The model reasons through tables, joins, filters and output columns before writing the query.

Rate-limited calls (HTTP 429) were retried until answered. No question is scored blank because of the
provider.

## Reproduce

```
python benchmarks/bird_minidev.py --data <minidev>/MINIDEV --provider oci --model google.gemini-2.5-flash \
    --out flash_sqlite.json
python benchmarks/bird_minidev.py --data <minidev>/MINIDEV --dialect postgresql \
    --url postgresql+psycopg://postgres:<pw>@127.0.0.1:5432/bird --provider oci --model google.gemini-2.5-flash \
    --reason --values --max-tokens 8000 --out flash_reasoning_pg.json
cd <mini_dev>/evaluation && python evaluation_ex.py --predicted_sql_path <file> \
    --ground_truth_path ../.../mini_dev_<dialect>_gold.sql --db_root_path <minidev>/MINIDEV/dev_databases/ \
    --diff_json_path <jsonl with each question's difficulty> --sql_dialect SQLite|PostgreSQL|MySQL
```

## Read these numbers with this in mind

- **Self-reported.** Mini-Dev's leaderboard lists results submitted by PR. Nobody else has re-run these.
- **Two setups are shown, not the best of each.** The reasoning setup is slightly worse on SQLite and
  slightly better on PostgreSQL and MySQL. Picking the better one per dialect after seeing the scores would
  be choosing on the test set, so both rows stay.
- **A fourth setup was tried and stopped.** It voted over four differently prompted queries, plus value
  lookup. On the first ~140 questions per dialect it was within about 3 points of the plain setup either
  way, so it was not run to the end.
- **MySQL scoring needed one change to the evaluator, not to the scoring.** Its `connect_mysql()` uses a
  unix socket, which Windows lacks; ours connects over TCP (`port=3306`). PostgreSQL and SQLite used the
  evaluator unchanged.
- **Training-data overlap.** BIRD has been public since 2023, and any LLM may have seen parts of it. That
  holds for every LLM entry on the leaderboard.
- **Jitto Build's model is inferred,** from JamLabs' own LiveSQLBench listing for the same product.
  BIRD's page lists it as "UNK".
