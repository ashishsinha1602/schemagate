# Why text-to-SQL gets business questions wrong, and what fixes it

Ask a text-to-SQL model "what was revenue last quarter?" and it will usually
return a number, run without error, and be wrong. The SQL is fine. The meaning
is not: to the model, revenue is `SUM(quantity * price)`. To the finance team,
it is completed orders only, net of discounts, minus refunds, with internal test
SKUs left out. Nothing in the schema says so, and no amount of SQL skill makes
up for it.

This page measures how big that gap is, and how much of it a business glossary
(a semantic layer, an ontology: the name matters less than what it holds)
closes.

## The test: definitions we wrote, answers computed from them

Public benchmarks can't measure this cleanly. Their "evidence" is a one-off
hint per question, and their expected answers come from someone else's reading
of the data. So we built a database where we wrote the definitions first
(`benchmarks/planted_definitions.py`):

- A seeded SQLite company: customers, products, orders, order lines, refunds,
  shipments, subscriptions.
- Eight business terms whose obvious reading is wrong:

| term | what it means here | what a reasonable reader writes |
|---|---|---|
| revenue | completed orders, lines net of discount, minus refunds, internal SKUs excluded | `SUM(qty * unit_price)` over all orders |
| active customer | a completed order in the last 90 days | `WHERE is_active = 1` (a flag set at signup, never updated) |
| on-time | shipped on or before the promised date; unshipped excluded | unshipped rows counted as late |
| big account | lifetime revenue, as defined above, over 5,000 | gross order value over 5,000 |
| churned | a subscription ended and no new one started within 30 days | any ended subscription |
| partner sales | revenue, as defined, on partner-channel orders | gross value of partner orders |
| return rate | completed orders with a refund / completed orders | refunds / all orders |
| AOV | revenue, as defined / completed orders | average gross order value |

- 21 questions, each with an expected answer computed from the definition and
  cross-checked against a plain-Python computation. A question is kept only if
  the naive SQL gets a different answer on this data, so every question can
  tell a glossary from no glossary.

## Results

Claude Sonnet 5, the shipped pipeline (select tables, write the prompt,
generate SQL), scored on whether the query returns the right answer:

| | correct |
|---|---|
| no glossary | 1 / 21 (4.8%) |
| no glossary, run again | 1 / 21 (no answer changed) |
| with the glossary | 15 / 21 (71.4%) |
| **with the glossary, cited definitions followed** | **21 / 21 (100%)** |

Fourteen questions went from wrong to right, none from right to wrong
(McNemar p = 0.0001).

Without the glossary the model did the sensible thing every time: gross
revenue, the `is_active` flag, every ended subscription counted as churn. For
"big accounts" and "partner sales" it declined to guess at all. That is the
real failure mode of text-to-SQL on business questions: not syntax errors, but
confident answers to a question nobody asked.

On a public benchmark the effect holds too: on BIRD, 201 held-out questions
asked without their hints, a complete glossary took execution accuracy from
44.8% to 54.7% (p = 0.001; `benchmarks/bird_ontology.py`).

## The six it first got wrong, and the fix

All six misses of the first glossary run were one pattern. A term defined
through another term ("partner sales is revenue on partner orders", "AOV is
revenue per completed order") retrieved its own definition but not the one it
leans on. The model got the channel filter right, then guessed what revenue
means -- and four of those were questions it had declined without a glossary,
so the half-delivered definition turned caution into a confident wrong answer:

| | correct | declined | confidently wrong |
|---|---|---|---|
| no glossary | 1 | 4 | 16 |
| glossary | 15 | 0 | 6 |
| glossary, cited definitions followed | **21** | 0 | **0** |

schemagate now follows those references: a matched concept brings every concept
its definition or filter cites, up to three steps, with the same visibility
rules, so a cited definition never names a table the caller may not see. As a
check on whether the model was re-deriving revenue rather than missing it,
revenue was also compiled into a view the dependent terms point at, with the
gross columns still queryable: 19/21, and neither miss involved revenue.

## Writing a definition

In the same `catalog.json` as the access rules:

```json
{"ontology": {"concepts": {
  "revenue": {"synonyms": ["sales", "net revenue"],
              "maps": ["order_items", "orders", "products", "refunds"],
              "filter": "orders.status = 'completed' AND products.is_internal = 0",
              "definition": "Completed orders only, each line qty * unit_price * (1 - discount), internal products excluded, minus refunds on those orders."}}}}
```

When a question uses the term or a synonym, its tables come into the prompt and
its meaning is written above the DDL. A caller who may not read a table the
definition names gets neither, so a glossary never leaks a withheld table.

Definitions can also be imported from a dbt semantic manifest, a Snowflake
semantic model or a CSV glossary, or suggested from the questions and SQL your
users already ran:

```bash
pip install schemagate
schemagate ontology import semantic_manifest.json --from dbt --url ... --config catalog.json --save
schemagate ontology suggest history.jsonl --url ... --config catalog.json
```

Reproduce the numbers:

```bash
python benchmarks/planted_definitions.py --check     # data and expected answers, no model
SG_MODEL=claude-sonnet-5 python benchmarks/planted_definitions.py
```
