# schemagate on BIRD, UniQL, Spider and Spider 2.0

Every other number in this repo is measured on schemas I invented. That is
fine for catching regressions and worth very little to anyone else: a schema
whose questions happen to share vocabulary with its own table names will
flatter any retriever, and you have no way to check that I did not do exactly
that.

So here are the same measurements on the public text-to-SQL benchmarks.
The data is downloaded from the original sources, the scripts are in
[`benchmarks/`](benchmarks/), and the retrieval part reruns in about three
minutes.

## Execution accuracy, scored by each benchmark's own evaluator

These are end-to-end numbers: schemagate picks the tables, the model writes
one query against only those tables, the query runs, and the benchmark's own
evaluator compares the rows with its reference answer. Nothing reads the gold
SQL. Every prediction file and evaluator output is in
[`benchmarks/results/`](benchmarks/results/).

| Benchmark | Model | Execution accuracy | Best published, on 2026-10-19 |
|---|---|---|---|
| **BIRD dev**, all 1,534 questions (SQLite) | Claude Opus 5.5 | **77.12** (simple 80.97 / moderate 71.34 / challenging 71.03) | main board, hidden test set: 82.95; a test-set submission was sent on 2026-10-22 |
| **BIRD Mini-Dev**, 500 questions, SQLite | Claude Opus 5.5 | **81.00** | 75.60 (Jitto Build, the same model) |
| BIRD Mini-Dev, PostgreSQL | Claude Opus 5.5 | **72.60** | 65.80 (Ontology2SQL, deepseek-v4-flash as a 12-step agent) |
| BIRD Mini-Dev, MySQL | Claude Opus 5.5 | **72.40** | 49.20 (TA + GPT-4) |
| BIRD Mini-Dev, SQLite / PostgreSQL / MySQL | Gemini 2.5 Flash, a light model, one query per question (the row on BIRD's board) | 63.60 / 55.60 / 54.80 | above the MySQL leader; below the other two |
| **UniQL, Oracle dialect**, 1,534 questions, first try only | Gemini 2.5 Flash | **64.47** (67.60 with one execution repair) | 49.61 (Claude Sonnet 4.5, UniQL's own baseline) |
| **Spider 2.0-lite, the 135 SQLite questions** (one third of the set; not a leaderboard row) | Claude Sonnet 5.5 | **71.9** (97 of 135) | 57.78 Pass@1 / 64.44 Majority@8 (FlexSQL, gpt-oss-120b, an agent) |
| Spider 2.0-lite SQLite, same 135 | Gemini 2.5 Flash | 39.3 (full schema, no schemagate: 40.7) | the light model is not competitive here |
| Spider 2.0-lite SQLite, same 135 | Claude Opus 5.5 | 67.4 (91 of 135) | below Sonnet 5.5 with the same pipeline |
| **Spider 2.0-lite, the 205 BigQuery questions** | Claude Sonnet 5.5 | **45.9** (94 of 205) | no BigQuery-only row on the board; Snowflake third not yet run |

What is the same in every row: one model call per question, about 2,100
prompt tokens, no candidate generation, no voting, no agent loop. The only
extra call is a repair when the database raises an error (1 of 1,534 on BIRD
dev). The BIRD numbers come from BIRD's `evaluation_ex.py`, the Oracle number
from UniQL's `evaluate.py --dialect oracle`, each run on the files in the
results folder.

What to read with care. Opus is not deterministic: a re-run of the Mini-Dev
SQLite setting gave 80.20 against 81.00, so treat single-run numbers as about
±1. Mini-Dev and dev rows on BIRD's site are self-reported; ours are in
[bird-bench PR #251](https://github.com/bird-bench/bird-bench.github.io/pull/251)
awaiting the maintainers, and the hidden test set, which only the BIRD team
runs, is the one number that is not self-reported. BIRD's `evidence` string is
passed through with the question, as the benchmark intends and as published
systems do. The Spider 2.0 row is one third of that benchmark: the BigQuery and
Snowflake tasks need credentials these runs did not have, so it is a measurement,
not a placing, and the FlexSQL comparison is not same-model. Details, difficulty
splits, and what the Oracle rules changed:
[Mini-Dev](benchmarks/results/bird_minidev/README.md),
[dev](benchmarks/results/bird_dev/README.md),
[UniQL Oracle](benchmarks/results/uniql_oracle/README.md),
[Spider 2.0-lite SQLite](benchmarks/results/spider2_lite_sqlite/README.md),
[Spider 2.0-lite BigQuery](benchmarks/results/spider2_lite_bigquery/README.md).

Access control is scored separately, by two benchmarks whose evaluators I did
not write: AC-F1 90.1 on the RBAC Text-to-SQL benchmark and refusal F1 0.984
on Spider-ACL, with zero queries that read ungranted data in either. Those
sections are [further down](#access-control-scored-by-someone-else-the-rbac-text-to-sql-benchmark).

## What is being measured in the retrieval sections

Everything from here to the access-control sections scores the part that is
schemagate's own job: picking the tables. What is scored is **table recall**:
given a question, does the selected set contain every table the benchmark's
own reference SQL reads.

Two numbers per row:

- **all gold tables present** — the strict one. Every table the answer needs
  was selected. A query missing one table does not run.
- **per-table recall** — the fraction of gold tables found, averaged over
  questions. Kinder, and useful for seeing how near a miss was.

## Spider (dev): 1,034 questions, 20 databases

```
PER-DATABASE                    all gold present     per-table recall
  top_k=3                            98.5%                99.3%
  top_k=5                           100.0%               100.0%
```

Every Spider and BIRD table in this section was re-measured on 2026-10-16
against 1.5.2 with the default (hashed) embedder, `python benchmarks/spider.py`
and `python benchmarks/bird.py`. The figures they replace were measured on an
earlier release and were mostly lower; which change moved them has not been
isolated, so none is claimed.

**This row is a floor, not a result.** Spider databases have a median of
three tables and a maximum of eleven. Picking five out of three is not
retrieval, and any method that returns the whole schema scores 100% here. It
is reported so you can see nothing is broken, and for no other reason.

The interesting setting is the one Spider does not ship: put every database
in one catalog and stop telling it which one to look in.

```
POOLED — all 166 Spider databases, 876 tables, no database hint

                      all gold present     per-table recall
  top_k=5                  76.7%                81.2%
  top_k=10                 86.1%                89.5%
  top_k=20                 94.2%                95.6%

  was, before the re-run:  71.4% / 82.6% / 92.9%
```

That is 876 tables from 166 unrelated domains, with heavy name collision —
dozens of `name`, `id`, `student`, `country` columns that mean different
things — and no hint about where to look. It is closer to a real warehouse
than anything in Spider itself.

## BIRD (dev): 1,534 questions, 11 databases, 75 tables

BIRD is the harder benchmark: the questions are phrased the way people ask
rather than the way the schema is named, and the databases carry real naming
instead of tidy benchmark naming.

```
PER-DATABASE, question only     all gold present     per-table recall
  top_k=3                            90.2%                95.6%
  top_k=5                            96.7%                98.6%

POOLED (75 tables, no hint)
  top_k=5                            83.8%                91.2%
  top_k=10                           91.3%                95.2%
```

BIRD ships an `evidence` string per question — a human hint like *"eligible
free rate = Free Meal Count / Enrollment"*. Retrieval is measured without it
above, because the honest question is what the user's words alone can find.
With it, which is what a real caller would pass through:

```
PER-DATABASE, question + evidence
  top_k=3                            92.4%                96.9%
  top_k=5                            98.0%                99.2%

POOLED, question + evidence
  top_k=5                            86.6%                93.4%
  top_k=10                           93.7%                97.0%
```

BIRD moved less than Spider: up about a point in most cells, and pooled with
evidence at k=10 is 0.2 points *lower* than before (93.9% then).

## Spider 2.0-lite: the one built for real schemas

Spider 1.0 databases have a median of three tables, which is why the pooled
setting had to be invented to say anything at all. Spider 2.0 needs no such
invention: 162 databases and 8,255 tables taken from real BigQuery,
Snowflake and SQLite warehouses (5,497 / 2,326 / 432), a median of 16 tables
per database and a maximum of 785. (The 103 databases the usable questions
actually touch run slightly larger, median 17.) Retrieval is the acknowledged
bottleneck there rather than a formality.

Counted on a complete checkout: `resource/databases` rooted at 43 characters,
`core.longpaths` set, all 8,255 files present. An earlier count in this file
said 7,892 -- 363 fewer -- and was taken on a different checkout; the figures
below were all re-measured against the complete one.

Only the questions whose gold SQL is public are usable -- the rest is held
out -- which leaves 247 across 103 databases.

Of those 247, the gold SQL names at least one table this loader can resolve
for **233**. The other 14 name nothing resolvable, and they are where the
ablation below is measured *from* rather than *on*: a paired comparison needs
both arms scored over the same questions, so it uses the 212, while any figure
meant to be read as recall uses 247 and counts an unresolved question as a
miss. Both denominators are printed against every number here, because the
first is a comparison set and the second is the result.

It was 203 before two fixes. Spider 2.0's `description` key is a per-column
list aligned to `nested_column_names`, not a table description, and columns
were being built from the top-level list alone -- so a table with nested
fields arrived without the columns its gold SQL reads. That took it to 212.
Then the harness started calling `collapse_partitions()`, as `bootstrap()`
does for every user, and the wildcard form the gold SQL itself uses began to
exist as an object: 233.

The 14 that remain break down as a BigQuery function read as a table --
`FROM UNNEST(...)` matches the FROM/JOIN regex -- a handful genuinely absent
from the schema directory, and two whose every reference is a CTE defined
inside the query. They are counted as misses in the 247 figure, not
excluded.

```
247 questions, none excluded        MiniLM      hashed
  top_k=5                           69.6%       66.8%
  top_k=10                          79.8%       80.6%
  top_k=20                          84.2%       85.0%

for comparison, scoring only the 233 whose gold tables resolve:
  top_k=5     73.8% / 70.8%    top_k=10  84.5% / 85.4%    top_k=20  89.3% / 90.1%
                                         (MiniLM / hashed)

per-table recall at k=10: 90.9% MiniLM, 91.3% hashed
```

**Report the first block.** The second is the same run with 44 questions
removed, and those 44 are not a random 44: they are the ones whose gold SQL
reads a wildcard partition -- `events_*`, `ga_sessions_*` -- which schemagate
cannot select because it holds each day as a separate object. Dropping the
questions a method fails is how a benchmark number gets inflated, and this
file did it for two releases before the difference was measured.

The history is worth keeping, because both errors moved the number the same
way:

```
  v0.1.48  86.1% @20   schema files silently unreadable (long paths)
  later    83.3% @20   files fixed, but 44 unresolved questions still dropped
  then     67.2% @20   166/247, every usable question counted
  then     71.3% @20   176/247, loader reading per-column descriptions correctly
  then     76.9% @20   190/247, column comments no longer indexed three times
  now      84.2% @20   208/247, harness calling collapse_partitions() as
                       bootstrap() does -- a measurement fix, not a retrieval one
```

The last line is the only one that moved the number *up*, and it is worth
being precise about why, because "our number went up" is the claim most worth
distrusting. The loader fix did not make retrieval better at anything it was
already doing: it made nine more questions resolvable and answered six of
them. On the 212-question comparison set the k=10 figure actually **fell**,
77.8% to 77.4% with MiniLM, because the nine questions that joined the set
are harder than the average of the 203. The recall figure over 247 rises
because the numerator grew and the denominator did not.

The "39%" in the first line has been removed rather than corrected, because it
is not a property of the benchmark. Windows refuses a path over 260 characters,
and the limit applies to the whole absolute path, so how many files are lost
depends on where the repository sits on disk. This re-run was done with
`resource/databases` at a **182-character root**, where 2,868 of 7,892 paths
exceed 260. One character deeper is 3,056. The durable numbers are relative:
the longest path is 154 characters below `databases/`, so any checkout rooted
deeper than 105 characters loses at least one file.
`python benchmarks/longpath.py` prints all of this for whatever checkout you
have.

Nineteen points of the original figure were measurement error, all of it
flattering. The fix for the first is `benchmarks/longpath.py`; the fix for
the second is counting.

## Prompt tokens on public schemas: the saving grows with the schema

`benchmarks/token_savings/measure.py` counts, for every question, the tokens of the schema
a text-to-SQL prompt carries: every column of every table in the database (no selection),
against what `Catalog.select` returns. No model is called. cl100k_base tokens; the hashed
embedder `pip install schemagate` gives you; top_k 6 on BIRD, 12 on Spider 2.0. Results
are in `benchmarks/token_savings/results.json`.

| Schemas | Questions | Databases | Median tables | Full schema, mean tokens | Selected, mean | Mean saving | Median saving per database |
|---|---|---|---|---|---|---|---|
| BIRD dev | 1,534 | 11 | 7 | 579 | 462 | 20.1% | 8.8% |
| Spider 2.0-lite, local SQLite | 135 | 30 | 13 | 924 | 642 | 30.6% | 6.3% |
| Spider 2.0-lite, BigQuery and Snowflake | 412 | 128 | 11 | 44,571 | 1,450 | 96.7% | 44.3% |
| the same, databases with 50+ tables | | 24 | | | | | **91.1%** |

Small schemas leave little to cut: on BIRD's seven-table databases the whole schema is
already a few hundred tokens. The saving is where schemas are big. The mean on the
warehouses is pulled up by a few very large databases, so the per-database median is
the fairer single number.

The cost of cutting: on BIRD, every table the gold SQL reads was in the selection for
98.4% of questions. On the warehouses (questions with public gold SQL) it was 86.7%. A
question whose table was cut can't be answered from the prompt. That is what the
retrieval sections above measure in detail.

**This table was revised after 1.14.0.** It first said 79.6% for the warehouses, with a
median of 16 tables, 46,560 full-schema tokens and a median saving of 92.9% over 33
databases with 50+ tables. Two things changed, and both are in the numbers above:

- *Scoring.* The script compared bare table names, so a gold `storms_2014` counted as
  missed even when the selection held the `storms_*` entry it had been folded into, and
  a gold wildcard such as `2000_*` never matched anything. It now counts a gold table as
  selected when the family it belongs to was selected (`covers()` in `measure.py`).
  That alone takes 79.6% to 83.6%: the same selections, scored correctly.
- *The library.* Tables split per year or quarter (`storms_2014` .. `storms_2024`,
  `gsod2014` ..) are now folded like the daily and monthly ones. Eleven NOAA, IRS and
  Citi Bike questions needed more of those tables than top_k could hold; folded, all
  eleven have every gold table selected, and no question lost one (83.6% to 86.7% here;
  the paired run on the 225 questions with gold tables was 11 wins, 0 losses).

Folding also shrinks the full schema the saving is measured against: eleven `storms_`
tables now count as one. That is why the median table count fell from 16 to 11, nine
databases dropped below 50 tables, and the 50+ median moved from 92.9% to 91.1%. The
tokens actually sent went down, from 1,469 to 1,450 per question.

## Head-to-head: schemagate against the retrievers other tools use

`benchmarks/token_savings/compare.py` picks tables four ways, on the same questions and the
same catalog, with no model calls: **full schema** (no selection); **BM25** keyword search over
each table's definition; **embeddings**, `all-MiniLM-L6-v2` similarity, the default way
LangChain, LlamaIndex and Vanna pick tables from a vector store; and **schemagate**, with
sentence-transformers installed so it uses the same MiniLM model -- the difference is ranking
and join expansion, not the embedder. Every method gets the same number of tables (12 on
Spider 2.0, 6 on BIRD), and the baselines get schemagate's partition folding for free, which
flatters them. Results are in `benchmarks/token_savings/compare_results.json`.

| | Spider 2.0-lite warehouses, 225 questions | | BIRD dev, 1,534 questions | |
|---|---|---|---|---|
| | every gold table selected | mean tokens | every gold table selected | mean tokens |
| full schema | 93.8% | 56,237 | 100% | 579 |
| BM25 | 78.7% | 1,513 | 81.0% | 407 |
| embeddings (MiniLM) | 78.2% | 1,555 | 89.4% | 438 |
| **schemagate** | **85.3%** | 1,677 | **98.7%** | 468 |

Paired, on the same question: schemagate had every gold table where embeddings did not on 17
warehouse questions, and the reverse happened on 1; against BM25, 18 to 3. On BIRD, 151 to 9
against embeddings and 277 to 6 against BM25.

What it costs: schemagate sends 8-11% more tokens than plain retrieval, mostly the tables
needed to join the ones it picked. What it does not show: selectors that ask a model to pick
tables (LangChain's table-selection chain, research systems such as CHESS) were not run, since
they need a model call per question. The full schema stays below 100% on the warehouses
because some gold SQL reads tables that are not in the benchmark's catalog files. With the
default hashed embedder (`pip install schemagate`, no extras) schemagate's warehouse figure is
86.7%, as in the table above this one.
## What the dropped questions say about the tool

They are not noise. Spider 2.0's `ga4` database is 92 tables named
`events_20201101` through `events_20210131`, and `ga360` is 366 of the same
shape. They differ by a date, which no embedder can reason about, so a
question about January selected twelve tables from November -- measured -- and
the model correctly refused a question it had been handed the wrong month for.

**The library has folded these since `9c68ec6`, and this benchmark was not
using it.** `Catalog.collapse_partitions()` turns a family of date-suffixed
siblings into one entry named with a wildcard -- `events_*` -- which is also
what the SQL should say, because BigQuery reads a wildcard table directly and
the gold SQL for these questions does exactly that. `Catalog.bootstrap()`
calls it, so every user reflecting a real database already gets it.

`benchmarks/spider2.py` did not call it. It builds its catalog with `add()`
and `index()` rather than `bootstrap()`, so the one thing that makes a
partitioned warehouse tractable was switched off for the whole benchmark.
Every Spider 2.0 figure this file has ever published was measured against a
schemagate nobody runs.

Turning it on -- one line, plus passing the catalog's own names through the
same `bare()` normalisation the gold references already go through, so a
collapsed `events_*` can match a gold `events_*` at all:

```
                          k=5      k=10     k=20
  without collapsing     57.9%    72.1%    76.9%     (what this file reported)
  with collapsing        66.8%    80.6%    85.0%     (what the library does)
```

and the gold SQL resolves for 233 of 247 questions instead of 212, because
the wildcard form the benchmark's own SQL uses now exists as an object.

That is a measurement fix, not a retrieval improvement, and it is worth being
blunt about the difference: nothing about the product got better here. The
harness was told to measure a configuration the product does not ship. The
normalisation half is measured separately and is worth exactly one question
on its own, so the movement is the collapsing.

An earlier version of this paragraph said the collapsing was "implemented in
`benchmarks/spider2_e2e.py` and **not yet in the library**". Both halves were
wrong: that file has no such code, and the library has had it since
`9c68ec6`. Recorded rather than deleted, because a file that keeps its own
corrections should keep this one.

## The embedder, on data I did not write

`pip install schemagate` uses a hashed n-gram vectoriser; installing
`schemagate[huggingface]` switches it to a sentence model automatically. On my
own schemas that was worth +3 questions out of 98, which is thin evidence.
On Spider pooled:

```
876 tables, no hint        hashed      MiniLM      (re-measured 2026-10-16, 1.5.2)
  top_k=5                   76.7%   →   80.3%
  top_k=10                  86.1%   →   90.7%
  top_k=20                  94.2%   →   97.0%
```

(The MiniLM top_k=5 figure, 80.3%, is the same 830/1034 that the reranker
section below starts from as its "maths order".)

Consistent, and larger than my own benchmarks suggested. Then Spider 2.0 said
something different:

```
233-question comparison set     hashed      MiniLM
  top_k=5                     70.8%   →   73.8%
  top_k=10                    85.4%   →   84.5%
  top_k=20                    90.1%   →   89.3%

over all 247 usable questions   hashed      MiniLM
  top_k=5                     66.8%   →   69.6%
  top_k=10                    80.6%   →   79.8%
  top_k=20                    85.0%   →   84.2%
```

Nothing, and fractionally worse at the wider cuts. So "install the extra and
retrieval improves" is not a claim this evidence supports.

I guessed at why: Spider 2.0 tables carry descriptions from the warehouse's
own data dictionary and Spider 1.0 tables carry none, so where there is prose,
BM25 over it already does what the sentence vectors were compensating for.
That was a hypothesis fitted to two benchmarks that differ in everything, so
here it is tested inside one of them -- same questions, same databases, same
columns and types, with only the `description` field suppressed.

```
Spider 2.0-lite, n=212, BEFORE the fix this table led to (see below)
(percentages over all 247 usable questions in brackets)
McNemar exact on the discordant pairs: b = removing prose fixed the question,
c = removing prose broke it

  k    embedder   with prose            prose removed          b   c     p
  5    hashed    136/212 64.2% (55.1%)  143/212 67.5% (57.9%)  16   9  0.2295
  5    MiniLM    140/212 66.0% (56.7%)  154/212 72.6% (62.3%)  19   5  0.0066
  10   hashed    165/212 77.8% (66.8%)  177/212 83.5% (71.7%)  15   3  0.0075
  10   MiniLM    164/212 77.4% (66.4%)  176/212 83.0% (71.3%)  13   1  0.0018
  20   hashed    178/212 84.0% (72.1%)  187/212 88.2% (75.7%)  12   3  0.0352
  20   MiniLM    176/212 83.0% (71.3%)  189/212 89.2% (76.5%)  15   2  0.0023
```

Both arms are built from one read of each schema, one database at a time, so
the only difference between them is whether the per-column descriptions are
present. One embedder instance is shared across every catalog: constructing
one per database loads the sentence model 206 times and the process dies with
SIGSEGV, which is how the first attempt at this table failed.

**The hypothesis is wrong.** MiniLM's advantage over the hashed embedder,
counted in questions, goes from +1/-1/-1 with prose to +2/+2/-1 without it.
The largest shift is three questions, and at one cut it is zero. Spider 1.0's
gap was about nine questions. Removing prose does not bring it back, so prose
is not what separates the two benchmarks. What does, I do not know: it could
be the dialect, the phrasing of the questions, the size of the tables, or
pooled-versus-per-database. I am not going to guess a second time.

**And the column does not hold up either.** Deleting every description looked
like it made retrieval better -- four to seven more questions answered, for
both embedders, at every cut. That is a net margin on a paired design, and a
net margin cannot tell you whether seven questions flipped one way or
twenty-one flipped both. McNemar's exact test on the discordant pairs, both
embedders, n=203 (b = fixed by the cap, c = broken by it, d = discordant):

```
hashed                                      MiniLM
  cap=0     k=5   b=12 c=11  d=23  p=1.000    b=14 c=8   d=22  p=0.286
  cap=0     k=10  b=10 c=4   d=14  p=0.180    b=7  c=2   d=9   p=0.180
  cap=0     k=20  b=11 c=6   d=17  p=0.332    b=15 c=1   d=16  p=0.001
  cap=40    k=5   b=8  c=6   d=14  p=0.791    b=8  c=6   d=14  p=0.791
  cap=40    k=10  b=2  c=2   d=4   p=1.000    b=5  c=2   d=7   p=0.453
  cap=40    k=20  b=2  c=2   d=4   p=1.000    b=6  c=1   d=7   p=0.125
  cap=200   k=5   b=3  c=5   d=8   p=0.727    b=3  c=6   d=9   p=0.508
  cap=200   k=10  b=1  c=1   d=2   p=1.000    b=3  c=2   d=5   p=1.000
  cap=200   k=20  b=1  c=1   d=2   p=1.000    b=3  c=0   d=3   p=0.250
  cap=1000  k=5   b=2  c=1   d=3   p=1.000    b=3  c=1   d=4   p=0.625
  cap=1000  k=10  b=1  c=1   d=2   p=1.000    b=3  c=1   d=4   p=0.625
  cap=1000  k=20  b=0  c=1   d=1   p=1.000    b=4  c=0   d=4   p=0.125
```

**One cell of twenty-four clears significance**, and it is the interesting one:
MiniLM, prose deleted, k=20 -- fifteen questions fixed against one broken,
p=0.001. At n=158 the nearest equivalent was p=0.065, so the larger question
set did move it.

It still does not carry the claim, for a reason worth being explicit about.
Swap the embedder and it evaporates: the same cap, the same cut, the same 203
questions, scored with the hashed vectoriser instead, is **b=11 c=6, p=0.332**.
A result that survives one embedder and not the other has measured the
embedder. It is also one cell of twenty-four, where a Bonferroni threshold is
0.002 -- p=0.001 squeaks under, which is not the kind of margin that should
change anybody's mind on its own.

**That table was a bug report, and the bug is fixed.** Read on its own it
says "delete your descriptions": removing them won at every cut on both
embedders, five of six cells significant, thirteen questions fixed against
one broken at k=10 with MiniLM. A design whose whole premise is that prose
helps should not lose to deleting the prose, so the question was not whether
to believe the table but what it was pointing at.

It was pointing at the same text being counted three times. A column comment
went into `_prose_text` for the prose channel, and into `embed_text()` --
which feeds the body channel *and* the vectors. A Spider 2.0 table carrying a
description per column therefore looked like a match on three of four
channels for any question sharing a word with any one of its columns, and the
widest tables became magnets. Decomposed on the same 212 questions: removing
the comments from the prose channel alone recovered 4 questions at k=10 and
from the body channel alone recovered 11, which is where the damage was.

Naming the channel matters. `embed_text()` has two consumers: the vectors,
and `_body_text` (`catalog.py`), which builds the body channel's BM25
document from it. `_body_text` is what changed -- it now drops the per-column
comments -- and `embed_text()` itself is unchanged and still carries them
(`models.py`). An earlier version of this paragraph attributed the 11 to
"`embed_text()` alone", which contradicted the next sentence: a fix that
leaves the vectors byte-identical could not have produced a recovery that
came from the vectors.

The two arms are not additive: 4 and 11 sum to 15 against a whole of 13,
because each arm is measured against the same unmodified baseline, and some
questions are recovered by either change on its own.

The fix takes column comments out of the body channel and the prose channel
and leaves `embed_text()` alone, so the vectors -- a published, pinned
guarantee -- are byte-identical and no stored index is invalidated. Re-run
paired on the same 212 questions with the fix in place, hashed embedder:

```
  k    with prose        without prose      b   c     p
  5    143/212 67.5%     143/212 67.5%      6   6   1.0000
  10   177/212 83.5%     177/212 83.5%      2   2   1.0000
  20   188/212 88.7%     187/212 88.2%      2   3   1.0000
```

One check that the table is the artifact it claims to be, and the check is
*across the fix*, not across embedders: the prose-removed arm is 143, 177,
187 both before and after, hashed throughout, because deleting every
description cannot care which channel would have carried them. Only the
with-prose arm was ever going to move, and it is the arm that moved.

Read the b and c columns, not the p column. With d = b + c discordant pairs
of 12, 4 and 5, the smallest two-sided exact p attainable is 2^(1-d): 0.125
at k=10 and 0.0625 at k=20, so those two cells could not have reached
p < 0.05 at any split of b and c. What the rows support is that b and c
converged -- the penalty is gone -- not anything about significance.

**The penalty is gone.** Same embedder on both sides, hashed, before and
after the fix:

```
  k    b/c before   b/c after    d
  5    16/9         6/6          25 -> 12
  10   15/3         2/2          18 ->  4
  20   12/3         2/3          15 ->  5
```

The stronger statement is in the levels, not the discordance: hashed with
prose goes 136 -> 143 at k=5, 165 -> 177 at k=10 and 178 -> 188 at k=20. At
k=5 and k=10 the with-prose arm lands exactly on the prose-removed arm; at
k=20 it passes it. Descriptions no longer cost anything on this benchmark --
they neither help nor hurt it, which is the floor the fielded design was
supposed to guarantee and did not. The shipped numbers above are the
with-prose column, because that is what a described catalogue now costs:
nothing.

An earlier version of this paragraph said "thirteen-to-one became
two-to-two". That paired the MiniLM cell of the before-table at k=10 (13/1)
with the hashed after-table (2/2), crossing the embedder axis -- the exact
error the paragraph above warns against. The hashed before-cell at k=10 is
15/3. Caught by howcani on dev.to.

Two things this does not say. It does not say descriptions are useless --
see the live measurement below, where a generated catalogue takes end-to-end
SQL from 6/8 to 8/8. And it does not vindicate the withdrawn claim: "long
descriptions hurt retrieval" was true of this implementation, not of prose,
and the right response to a true measurement was to fix the thing it
measured rather than publish it.

The cap sweep below was measured with the old loader and has **not** been
re-run. Truncating descriptions at 200 or 1,000 words was indistinguishable
from leaving them alone -- one to four discordant pairs, p=1.000 -- and only
deleting them entirely moved anything. That conclusion is consistent with the
re-run, but the cap cells themselves are stale and are kept only as the record
of what was done.

For comparison, prose in the other two benchmarks:

```
Spider 1.0      0 of 876 tables have a description
BIRD            0 of  75
```

Both are bare names and columns, which is why the ablation could only be run
on Spider 2.0.

**What the ablation was removing, and the re-run that fixed it.** Until
recently every number in this section was measured with a loader that read
`description` as a table description -- joined into one paragraph and indexed
as prose. Sampling the raw files for the long-path report showed the key is
nothing of the kind: it is a per-column list, aligned by index to
`nested_column_names` when the table has nested fields (31 of 31 sampled) and
to `column_names` otherwise (9 of 9), entries sometimes null, never a string
(150 of 150). The loader also built columns from `column_names` alone, so a
nested table -- gnomAD's `v3_genomes__chr7`, 61 top-level and 181 flattened --
was missing the very columns its gold SQL reads. `benchmarks/spider2.py` now
attaches each entry to its column and uses the flattened list;
`tests/test_spider2_loader.py` holds it there.

**That re-run is what the numbers above are.** It was done against a complete
checkout of the benchmark -- `resource/databases` at a 43-character root with
`core.longpaths` set, all 8,255 files readable -- with the shipped 0.1.56
library, and the paired arms were scored by a script written twice
independently, in-memory and streaming, agreeing cell for cell before either
was believed. The numbers this replaced are in the history block above rather
than deleted.

Indexing 876 tables takes 0.8s hashed and 9.3s with the sentence model.

## The reranker, measured for the first time

`select(..., reranker=provider, rerank_candidates=20)` has existed since the
reranker landed and had never been measured. `tests/test_rerank.py` proves it
is *safe* -- a model that fails, or replies with nonsense, leaves the maths
order untouched, and a restricted object cannot be promoted into an answer --
but safety is not usefulness, and no recall number for it existed.

`benchmarks/rerank_eval.py` scores every business-language question twice
against the same catalog, the same embedder and the same `top_k`: once with
`reranker=None`, once with a model reordering the shortlist. Paired, so the
report is discordant pairs and McNemar's exact test rather than a net margin.

anthropic:claude-sonnet-4-5, all-MiniLM-L6-v2, top_k=6, candidates=20:

```
schema      set          base   rerank    b    c        p
commerce    TUNE        75.0%    91.7%    2    0    0.500
health      TUNE        90.0%   100.0%    1    0    1.000
warehouse   HELDOUT     80.0%   100.0%    2    0    0.500
finance     HELDOUT     80.0%   100.0%    2    0    0.500
telemetry   HELDOUT     80.0%   100.0%    2    0    0.500
complex     HELDOUT    100.0%   100.0%    0    0    1.000
---------------------------------------------------------
TUNE                    81.8%    95.5%    3    0    0.250
HELD OUT                83.3%   100.0%    6    0    0.031
OVERALL                 82.8%    98.3%    9    0    0.004
```

**Nine questions fixed, none broken.** That the count of broken questions is
zero is the more interesting half: the model only reorders a shortlist of 20
and the maths still decides eligibility, so it can lift a gold table from
position 7-20 into the top 6 but cannot invent one, and every question the
ranking already answered it left alone.

**What this is not.** Fifty-eight questions on the six schemas in this
repository, which are invented, not public benchmarks -- the Spider and BIRD
numbers above are untouched by this and no reranked figure has been measured
on either. One model. And the held-out p=0.031 rests on **six discordant
pairs**: it clears 0.05, and a Bonferroni threshold across the six schemas is
0.008, which it does not clear. The overall p=0.004 does.

**The second-model control, which this one passes.** The prose ablation below
evaporated when the embedder was swapped, so the same question had to be put
here. Re-run end to end with `claude-haiku-4-5` -- a smaller and cheaper model
-- the result is not merely similar, it is identical:

```
                        base   rerank    b    c        p
TUNE                    81.8%    95.5%    3    0    0.250
HELD OUT                83.3%   100.0%    6    0    0.031
OVERALL                 82.8%    98.3%    9    0    0.004
```

Same nine questions fixed, same none broken, the same b and c in every schema.
Two models of different sizes agreeing to the question is evidence that what
was measured is the *shortlist* -- gold sitting at rank 7-20 that any
competent reader can lift into the top 6 -- and not one model's taste.

Both are still Anthropic models. A model from another vendor is the remaining
control and has not been run, because no other provider key was available on
the machine that ran this.

Cost, since it is not free: one API call and roughly two seconds per question
(58 selections in 115s).

## Access control, scored by someone else: the RBAC Text-to-SQL benchmark

Everything above scores retrieval. This scores the thing schemagate exists for, on a benchmark
it did not write: *Benchmarking Text-to-SQL under Role-Based Access Control* (Fei, Jiang, Yang,
Xiao; SIGMOD'27, arXiv 2607.22115, github.com/2020dfff/RBAC-Text2SQL-Benchmark). Each row is a
question, a role and a column-level policy. The system must answer, or refuse when the role cannot
read what the answer needs. Scoring is the authors' own evaluator, unchanged
(`evaluate_protocol_v2.py --fair_comparison --num_trials 5 --execute_sql`): five passes, each
pairing every question with one random role.

`benchmarks/rbac_text2sql.py` turns each policy into schemagate visibility and runs the shipped
pipeline: select (top_k 6, hashed embedder, no reranker), `prompt_fragment`, `generate_sql`, then
`run_query`'s scope check. INSUFFICIENT, or SQL the scope check refuses, becomes the benchmark's
refusal. claude-sonnet-4-5, the model behind the paper's best results; mean ± std over 5 trials:

```
BIRD dev (10,175 rows)            AC-F1          SafeEX        violation      over-refusal   SQL read forbidden data
  schemagate                      90.14 ± 0.32   68.38 ± 1.07   5.44 ± 0.19    1.98          0.00
  schemagate, no scope check      84.69 ± 0.69   69.14 ± 0.85  11.25 ± 0.44    1.23          3.78
  paper: policy in the prompt     88.12 ± 0.90   65.02 ± 0.89   7.37 ± 0.49    1.81           --
  paper: role-schema, best model  72.46 (GPT-5-mini)             26.72          0.33           --

Spider dev (6,926 rows)
  schemagate                      93.02 ± 0.37   78.87 ± 1.05   5.05 ± 0.49    2.59          0.00
  schemagate, no scope check      90.68 ± 0.31   79.56 ± 1.05   8.67 ± 0.57    1.91          2.01
  paper: policy in the prompt     93.03 ± 0.48   80.99 ± 0.86   4.55 ± 0.22    3.01           --
  paper's best Spider model       95.94 ± 0.37   75.73 ± 1.19   1.97 ± 0.25    2.36           --
    (DeepSeek V3.2-Reasoning)
```

The "paper" rows are the paper's Claude Sonnet 4.5, the model used here. On BIRD that is also the
best of its thirteen models; on Spider the best is DeepSeek V3.2-Reasoning, shown separately.

"Violation" is the benchmark's: any answer to a question the role may not ask, even one that reads
only permitted columns. "SQL read forbidden data" is the stricter thing a database cares about,
the SQL touching a table or column outside the policy, and it is zero by construction: that is
what the scope check refuses.

**What it shows.** On BIRD schemagate beats the paper's best configuration on AC-F1, SafeEX and
violations, without showing the model the restricted part of the schema at all; the paper's
prompt shows the full schema and the policy beside it. On Spider it ties the same model on AC-F1 and
is slightly behind it on violations and SafeEX; the paper's best Spider model, DeepSeek
V3.2-Reasoning, is ahead of it on AC-F1 (95.9) and violations (2.0%), behind on SafeEX. The paper's own schema-restriction baseline -- the model sees only
what the role may read -- fails because models "rarely refuse" and approximate from the columns that
are left. Two things fix that here. The scope check turns a reach for anything outside the policy
into a refusal; the table isolates it (with vs without, both with the notice). And
`Catalog.restriction_notice` (on by default from 1.6.0) adds one line saying the view is partial,
never naming what is withheld. The notice was isolated only on the 100-question BIRD pilot, with
the scope check on: violations 16% without it, 5% with it, AC-F1 0.82 to 0.92. The full runs were
not repeated without it.

**What it does not show, and the caveats.**
- The notice's wording was chosen on a 100-question pilot drawn from the start of the BIRD
  evaluation set, so it was tuned on 100 of BIRD's 1,534 questions. Spider was not used for any
  choice and is the cleaner of the two.
- Same model name as the paper, not necessarily the same API snapshot. The prompts differ by
  design: the paper's is theirs, this is schemagate's.
- BIRD databases are the 2024-06-27 dev release; the paper used 2025-11-06. Gold SQL comes from the
  benchmark's own file, unchanged.
- Loading BIRD's column descriptions as comments made it **worse** on the pilot (violations 16% to
  26% without the notice): richer notes on the visible columns helped the model find workarounds
  for questions it should have declined. The runs above use the schema as reflected.
- One model; the paper reports thirteen. About $195 of API calls for both datasets.

## Access control, a second benchmark: Spider-ACL

*Role-Conditioned Refusals: Evaluating Access Control Reasoning in Large Language Models* (Klisura,
Khoury, Kundu, Krishnan, Rios; Findings of EACL 2026; github.com/klisura-code/LLM-Access-Control-Datasets)
gives every Spider question four roles, from full read access to almost none, as PostgreSQL GRANT
statements. The label is what PostgreSQL itself said when the reference SQL ran as that role:
PERMIT, or DENY ("permission denied"). 19,624 records: 8,095 PERMIT, 11,529 DENY. Scored as the
paper does: refusal precision, recall and F1, with refusal as the positive class.

`benchmarks/acl_text2sql.py` turns each record's GRANTs into schemagate visibility and runs the shipped
pipeline -- select (top 6, default embedder), `prompt_fragment` with the restriction notice,
`generate_sql`, then `run_query`'s scope check. INSUFFICIENT, or SQL the scope check refuses, is a
refusal. One model, claude-sonnet-5-5, all 19,624 records, none failed:

```
                                         refusal P   refusal R   refusal F1   false permits
  schemagate, all 19,624                 0.985       0.982       0.984        1.8%  (206 / 11,529)
  schemagate, 600 never used for tuning  0.989       0.983       0.986        1.7%
  paper's best, Spider                   --          --          0.933        --     (LoRA-tuned Mistral-7B)
  paper's best without fine-tuning       0.898       0.868       0.883        --     (DeepSeek-R1 + verifier)
```

**No answered query read anything the role was not granted.** Checked independently of the scope
check that enforces it: every one of the 8,128 answered queries was parsed with sqlglot and its
tables and columns compared with the record's GRANTs -- none outside them. (Two queries the parser
could not read, because the model wrote a sentence after the SQL, were checked by hand; every
column they name is granted.)

**False permits are not leaks.** A false permit is a DENY question the system answered anyway, from
columns the role may read. Some are the label's doing -- "list the customer ids" is DENY because the
reference SQL also selects a name the question never asked for -- and some are a model answering a
near-miss of the question from the columns that remain. None of them read withheld data.

**What changed to get here.** A 200-question pilot first scored F1 0.83, with 32 of its 33 wrong
refusals from one bug: the scope check read `FROM students AS T1` -- upper-case `AS` -- as two tables
and refused valid queries. Fixed in 1.6.1 (`tests/test_scope_check_uppercase_as.py`). The pilot's 200
records were then set aside, and the 600-record figure above comes from records it never touched.

**Limits.** The paper's systems are 2024-25 models (GPT-4o-mini, DeepSeek-R1, Llama 3.1, Mistral-7B);
this is a 2026 model, and the gap is partly the model. Execution accuracy is not measured here (it
needs the PostgreSQL databases), only the answer-or-refuse decision. BIRD-ACL, the paper's second
dataset, was not run. Every per-record decision and query is in
`benchmarks/results/acl/spider_acl_claude-sonnet-5-5_decisions.jsonl.gz`.

## The reranker on Spider and BIRD

The numbers above are the reranker on this repository's own invented schemas. This measures it on the
public benchmarks, in the setting where the order inside the shortlist decides the answer: POOLED,
every database in one catalogue and no hint which one a question belongs to
(`benchmarks/rerank_public.py`). Each question is scored twice on the same catalogue, embedder and
`top_k`: the maths order (RRF of the lexical, vector, name and prose rankings), and a model reordering
the top 20. Metric: every table the gold SQL reads is in the top 5. Paired, McNemar's exact test.

claude-haiku-5-5, default embedder, top_k=5, candidates=20, all of Spider dev and BIRD dev:

```
set     tables   n      maths order       reranked          b     c    p
spider  876      1034   830  (80.3%)      998  (96.5%)      169   1    2.3e-49
bird    75       1534   1359 (88.6%)      1483 (96.7%)      125   1    3.0e-36
```

The model answered every one of the 2,568 calls -- this is counted, not assumed, because until the
fix below a reasoning model answered none of them and the result would have read as "no effect".

**What this is and is not.** It is table retrieval, not execution accuracy: the right tables in the
prompt, not the right answer. One model; Spider and BIRD questions are public and may be in its
training data, which would flatter a reranker that reads them -- though it only reorders candidates
the maths already shortlisted and sees table names and summaries, not the gold SQL. About one call
and a few hundred tokens per question.

**The fix that made this measurable.** `rerank()` asked for `max_tokens=120`. Claude 5 models spend
that on reasoning before writing, so every call raised, the reranker fell back to the maths order as
designed, and `--rerank` silently did nothing. It is now 1024, and `tests/test_rerank.py` holds a model
that fails below 512 tokens. A fallback that is safe by design also hides total failure: the
benchmark logs whether the model answered for exactly that reason.

The reranker stays opt-in -- picking tables needs no API key, and that is the default -- but with a
key available it is the largest single gain measured in this file. The MCP server takes it with
`SCHEMAGATE_MCP_RERANK=1`.

## Column ranking, and why this file reports no gain for it

`render_ddl` kept `visible[:max_columns]` -- the first 40 columns in
declaration order, whatever was asked. That is truncation, not selection: on a
200-column fact table the column the question needs can be number 147 and is
cut, while the prompt pays for 40 nobody asked about. Columns over the budget
are now chosen by overlap with the question, with keys kept unconditionally
because dropping a foreign key costs a join rather than a column.

**On the six schemas in this repository it changes nothing at all.** Measured
rather than assumed -- all 58 business-language questions, prompt rendered with
and without the question passed down:

```
prompts identical with and without column ranking : 58
prompts changed by column ranking                 :  0
```

The reason is in the schemas, not the code. Exactly one object across all six
is wider than the budget:

```
schema       objects  maxcols  over40  p95cols
commerce          42       11       0        8
health            27       10       0        7
warehouse         51       22       0       12
finance           39       14       0       10
telemetry         40        8       0        7
complex          260      321       1       15
```

That one is `wide_measurement_matrix`, whose 321 columns are named
`attribute_000` through `attribute_319`. It exists to test that a wide table
does not break rendering, and no question can prefer one of its columns to
another, so even there ranking has nothing to work with.

So the honest statement is narrow. The mechanism is covered by
`tests/test_column_ranking.py`, including the property that ranking runs after
`visible_columns` and so cannot surface a column the caller may not see -- both
of those tests were checked by reverting the change and confirming they fail.
What is **not** demonstrated is a retrieval or token gain, because these
fixtures cannot demonstrate one. A realistic wide table -- a claims or
telemetry fact table with meaningful column names -- is what would measure it,
and this repository does not have one yet.

The change is therefore recorded here as safe and unmeasured. It cannot
regress the numbers above for the concrete reason that it does not alter a
single prompt that produces them.

## A stemming bug, and what it had been propping up

`_stem` exists to let a plural meet its singular, and for the commonest
plural in English it did not. The "-es" rule stripped both letters
unconditionally -- right for `boxes -> box`, wrong for every noun whose
singular already ends in "e":

```
employees -> employe     employee -> employee     never met
invoices  -> invoic      invoice  -> invoice      never met
notes     -> not         note     -> note         never met
prices, packages, services                        never met
```

Six of eleven common plurals did not reach their singular. Both sides of the
lexical index go through this function, so a question about "invoices" did
not match the `invoice` table lexically at all; it was rescued, when it was
rescued, by the vector channel. A second bug compounded it: the coverage
pass looked up `idf.get(t)` with the raw token against an index that stores
stems, so coverage silently never fired for `contacts`, `payments` or
`invoices` -- the ordinary way anyone phrases a question.

Both fixed. "-es" is stripped only after a sibilant, where English actually
adds one; otherwise the "s" alone. Twelve of fourteen plurals now match; the
two that do not (`addresses`, `statuses`) are the pre-existing "-ses" case,
which no suffix rule separates from `houses -> house` without a dictionary,
and were left alone rather than guessed at.

**What it changed on the shipped schemas:** recall unchanged on all six;
average prompt tokens 742 -> 764 (+3%), because coverage now fires for
plurals and adds the table it should have added all along. The README cell
was updated to match.

**What it changed on the 1,200-object fixture is the part worth reading.**
Correct stemming lifted the flat bag from 9/16 to 12/16 at k=6 and left
fielded scoring at 12/16 -- so the fielded-versus-flat comparison recorded in
PR #41 no longer reproduces at the operating point at all. A meaningful share
of the advantage attributed to fielded scoring was an artifact of the flat
bag being unable to match plurals. Foreign-key expansion on the same fixture
went from worth 3 of 8 complex questions to 0 of 8, for the same reason:
with plurals matching, ranking reaches those tables on its own.

That is reported rather than absorbed. The claim that fielded scoring beats a
flat bag on a saturated corpus is now narrower than this file has stated. On
that fixture after the fix it wins at k=1, 3 and 5, ties at 6, loses at 10 and
wins again at 20 -- a sign that flips with the budget is measuring the budget,
and it is not stated as a result here.

## The AI catalogue, measured where it is actually used

`use_desc` in `tests/run_paraphrase_eval.py` was a parameter that existed and
did nothing: it was accepted and never applied, so anyone measuring the
catalogue through that harness got a catalog with no descriptions and would
have concluded descriptions were worth nothing. Wired. With it wired, the
same fixtures `test_business_language.py` uses give:

```
schema       identifiers  +AI catalogue
commerce           50.0%       100.0%
health             50.0%        90.0%
warehouse          50.0%        80.0%
finance            70.0%       100.0%
telemetry          60.0%       100.0%
OVERALL            55.8%        94.2%   n=52
```

**And on the metric that matters -- SQL that runs -- against the live Oracle
1,200-object schema.** Eighteen objects described by a model, then the eight
complex questions asked end to end (selection, model writes SQL from the
fragment alone, Oracle executes it):

```
no catalogue                          6/8 executed
shipped prompt, AI catalogue          7/8 executed
a "better" prompt, AI catalogue       5/8 executed   (two runs, same failures)
```

The third row is a prompt this session wrote to remove framing words from
descriptions, on the strength of a measurement that "answering" appeared in
about half of every checked-in catalogue. It described the same eighteen
objects and produced fewer runnable queries, twice, with identical failures
both times. It was reverted. The shipped prompt is the better one, and the
only reason that is known is that it was measured against the thing users
actually get -- a query that runs -- rather than against the intermediate
statistic the change was designed to improve.

## Column evidence gets one slot

Rank fusion rewards breadth over depth. An object that is first on two
channels can lose to twenty objects that are tenth on three, because RRF
turns every rank into 1/(60+rank) and adds -- so three mediocre ranks beat
two excellent ones and an absence.

Measured on the 1,200-object fixture, with the AI catalogue applied: "Top 5
contacts by email opens in the last 30 days, with their company" ranked
`crm_engagement_fact` **first of 1,199 on the body channel and first on
prose** -- its columns are `email_open_7d`, `email_open_30d` and so on -- and
fused it to **30th**, behind twenty-nine `crm_contact_*` and `crm_company_*`
siblings that merely share a word with the question in their name. The
coverage pass could not help: it guarantees a slot for informative words
that appear in NAMES, and "email" and "open" appear only in columns.

The body channel is the only one that sees columns, so its single best hit
is the one piece of evidence nothing else guarantees. It now gets one slot,
under exactly the rules coverage uses: budget-neutral, displacing the weakest
ranked pick, never a pinned or covering one, abandoned rather than break the
budget. The rule names no schema and no word.

**Where it is a no-op, which is everywhere it should be.** On the six
shipped schemas the benchmark gate is byte-identical -- every recall cell
and the token cell unchanged -- because on a small schema the best lexical
match already made the cut. The 52-question business-language measurement
is unchanged at 55.8% / 94.2%. Parity between the Python and JS ports holds
on all 1,789 cases.

**Where it bites.** On the 1,200-object fixture, fielded recall at k=6 went
from 12/16 to 14/16 (fixes 3, breaks 1), and column ranking now changes 2 of
16 prompts as retrieved, up from 0 -- which is to say the wide fact table is
finally being retrieved rather than pinned. The apparatus sweep on (b) is
still apparatus-dependent (fielded wins at 4 of 7 values of K) and is
reported as such.

**On the metric that matters.** Eight complex questions, end to end against
the live Oracle schema -- selection, a model writes SQL from the fragment
alone, Oracle executes it -- run twice with identical results both times:

```
                          before      after
no catalogue               6/8         7/8
shipped-prompt catalogue   7/8         8/8
```

The one question still failing without a catalogue ("contacts with a tag
but no note") is an anti-join across two children of the same parent, and
with the catalogue applied it runs.

## The same fixture on PostgreSQL

A finding that holds on one database is a finding about that database. So
`benchmarks/fixture_1200.py --target postgres` builds the identical spec --
same 1,201 objects, same 1,144 foreign keys, same 3,579 rows, same one-voice
descriptions -- on PostgreSQL 16 (a local container; 1,200 tables is not
something to put on a shared database unasked), and every number is
re-measured there.

The generator is what is checked in. The two databases differ only in
dialect: `NUMBER -> NUMERIC`, `VARCHAR2 -> VARCHAR`, `DATE -> TIMESTAMP`, the
date literal, and identifier case. Reflection takes 8 s on PostgreSQL against
160 s on the Autonomous Database.

**Every acceptance check reproduces number for number:**

```
                                   Oracle 26ai    PostgreSQL 16
(a) idf('contact') name / flat     4.288 / 0.147  4.288 / 0.148
(b) flat vs fielded @k=6           12 / 14 of 16  12 / 14 of 16
(c) column ranking, as retrieved   2 of 16        2 of 16
(d) probes reaching the guard      2 of 3         2 of 3
(e) complex, all gold present      4 of 8         4 of 8
    (b) sweep: fielded wins at     4 of 7 K       4 of 7 K
```

**And on the metric that matters -- SQL that executes on the live
database.** Eight complex questions, a model writing SQL from the fragment
alone, each run twice with identical results:

```
                          Oracle    PostgreSQL
no catalogue               7/8        6/8
real AI catalogue          8/8        8/8
```

The one extra miss on PostgreSQL without a catalogue is the refund question,
which fails at generation -- the model declines the tables it was shown. With
a catalogue it runs on both. The AI catalogue is generated separately for
each database, because the qualified names differ (`SGBENCH.crm_contact`
against `sgbench.crm_contact`); it is 18 objects and takes 18 s.

One thing the harness had wrong and now says correctly: its summary line read
"executed on Oracle" whatever the target was.

## The real catalogue, always

The AI catalogue was the largest accuracy lever in the library and the step
everyone skipped, because using it meant knowing `schemagate describe` exists,
running it, and carrying a `--config` file around. Every path that answers a
question -- `select`, `--answer`, the MCP server, the Studio's connect -- now
describes the catalogue first, whenever a key is present, and caches the
result per connection. `SCHEMAGATE_AUTO_DESCRIBE=0` turns it off; with no key
nothing is called.

**The first version did nothing on the fixture, and that was correct.** It
described only objects with no description and no hint. Every object on the
1,200-object schema carries a database comment, so it wrote 0 descriptions
and PostgreSQL stayed at 6 of 8 complex questions -- the no-catalogue number.
A comment is a comment.

But those comments are one voice repeated 1,036 times, and the 8 of 8 measured
earlier had come only from overwriting them by hand. So a second rule: a
comment whose best word, in the prose index, is less informative than
`BOILERPLATE_MAX_IDF = 0.5` is boilerplate -- it says something every object
also says -- and is replaced. A hint is never boilerplate; a missing comment is
missing, not boilerplate; a call that fails puts the original comment back.

The rule needed one refinement, found by running it: the object's own name
and column words do not count. A generated comment nearly always restates
them ("holds crm contact note records"), and with the name counted, 2 of
1,036 one-voice comments read as boilerplate -- each carried exactly one
rare word, its own. The digits in `crm_thing_005` were the last of it: not
"own" under an alphabetic tokenizer, and a token that appears once in the
corpus scores 3.7. Own words are now taken through the same tokenizer as the
description, and a run of digits is never prose.

**Through the product path, no flags, no hand-fed file, PostgreSQL 16:**

```
                                    before       after
boilerplate comments replaced        0 / 1,201    1,035 / 1,201
comments kept (the other voice)      --           165
complex SQL executed                 6 / 8        8 / 8   (twice)
second run, warm cache               --           30 s, zero describe calls
```

1,035 is the number the fixture specified for the saturated voice, to the
object; the 165 written in a different voice carry words the rest of the
schema does not, and were kept. That is the rule discriminating, not clearing
everything it sees.

**Oracle, same path, same rule: 7 of 8.** Three runs through the product
path scored 6, 6 and 7 -- the middle one lost a query to a dialect slip by
the model that did not recur -- and the consistent miss is the email-opens
question, which PostgreSQL answers. The cause is deterministic and worth
recording exactly, because it is not the dialect and not the rule. The fact
table's indexed text is byte-identical on both databases. What differs is a
*neighbour*: `crm_channel_type` was described independently on each
database, and the Oracle description happens to read "ways customers can
reach or interact with the **company**, such as phone, **email**, web" -- two
of the question's words -- scoring 17.23 on the body channel against the fact
table's 17.14, and taking the single body slot by 0.09. The PostgreSQL
description of the same table, "defines the different kinds of communication
or sales channels", carries neither word, and there the fact table is first.

So: the catalogue is nondeterministic across generations, and a one-slot rule
is sensitive to that at the margin. Widening the slot would fix this question
and be tuning to it, so the slot stays at one and the 7 stays in this table.

One object on each database kept its boilerplate comment: the fact table's
own, whose synthetic text reads "holds engagement **measures** per contact",
and "measures" appears in no other description. By the rule's definition that
is a word the schema does not otherwise carry, and the rule is not bent for
one fixture artifact. 1,035 of 1,036 is the honest count.

The suite is guarded: `tests/conftest.py` sets the kill switch by default, so a
key in a developer's shell cannot turn a test run into billed calls, and
`tests/test_auto_describe.py` asserts "no call was made" with a provider that
counts its own calls rather than assuming it.

## FK closure: what a selection carries beyond the budget

A question from the dev.to thread: when you ask for `top_k=K`, how much do you
actually get? Reported as requested-versus-delivered that is a pair of numbers
with no error bars. Reported as a quantity it is

```
closure(K) = returned(K) - min(K, supply)
```

where `supply` is the number of objects in the schema. It counts what arrived
that ranking alone could not have put there. In this library that is
foreign-key expansion: a ranked pick drags in the table it references.

**FK closure, not closure.** The coverage pass also appends, but over the 2,074
selections below it returns a `covers` pick **three times** -- 0 commerce,
0 health, 0 warehouse, 1 finance, 2 telemetry -- and it is budget-neutral in
both branches: inside the budget it displaces a ranked pick, and when nothing
is droppable it abandons the pick rather than widening the answer. It cannot
enter closure. That split is identical under both embedders, which is why it
is stated as a fact rather than a reading.

One curve, in full, for health's `which claims were turned down and why`,
supply 27, K = 1..27:

```
2 2 3 3 4 5 5 6 7 7 8 7 6 5 5 5 5 6 5 4 4 3 2 2 1 1 0
                    ^ peak 8 at K=11
```

`python benchmarks/closure.py` prints one of these per question, with the
supply and the K grid beside it, for 52 questions across five schemas.

### Why there is no min/max pair here

Both endpoints are artifacts of the apparatus, and publishing them as bounds
would be publishing the grid.

**The floor is arithmetic.** Once K reaches supply, the ranked set is
everything, `min(K, supply)` is supply, and closure is 0 because there is
nothing left to add. That is a clamp firing, not a measurement, and on a
coarse grid most of the zeros are clamp-forced that way.

**The ceiling moves with the grid.** On a six-value grid health's reference
question peaks at 7; swept over every K it peaks at 8. How many of the 52
questions peak higher on the dense sweep than on a coarse grid depends
entirely on which coarse grid:

```
  compared against          questions peaking higher on the dense sweep
  [1, 3, 6, 10, 20, 50]                 24
  [1, 5, 10, 20, 40]                    23
  [1, 2, 4, 8, 16, 32]                  27
  [3, 6, 12]                            28
  [6]                                   43
```

Twenty-three to forty-three, for the same 52 questions and the same system.
The number measures the grid. The curve does not, so the curve is what is
printed.

And the ceiling is embedder-dependent too: health's reference question peaks
at **8 with the hashed embedder and 5 with MiniLM**. `closure.py` names the
embedder in its output for the same reason the paraphrase harness does.

## The gate these numbers had to pass

Before any figure above was written down it was re-measured with one part of
the apparatus changed -- the K grid, the embedder, the hit predicate, the
denominator. If it moved, it was a fact about the apparatus and is reported as
one. If it held, it is reported as a result.

What moved, and is therefore labelled rather than claimed:

- the dense-grid question count (23 to 43, by grid)
- health's closure ceiling (8 hashed, 5 MiniLM)
- the one significant McNemar cell (p=0.001 MiniLM, p=0.332 hashed, same 203
  questions, same cap, same cut)
- every recall percentage on Spider 2.0-lite, which is 203 or 247 depending on
  whether unresolved gold counts as a miss -- so both are printed
- the paraphrase recall in the README, which is 58.6% or 82.8% by embedder and
  changes again under a looser hit predicate

What held:

- `covers` returns three picks in 2,074 selections, split 0/0/0/1/2 across the
  five schemas, under both embedders
- the shape of every closure curve: rises, peaks well inside supply, decays to
  the clamp
- 67.2% @20 on Spider 2.0-lite, 166 of 247, unchanged by the long-path fix

## End to end: execution accuracy on BIRD

Everything above scores retrieval -- did the right tables get selected. This
scores what the benchmark scores: run the SQL, run BIRD's reference SQL,
compare the rows. That is execution accuracy, the number published systems
report, and it is the only figure here directly comparable to work outside
this project.

The pipeline is the shipped one. `select()` picks the tables, `generate_sql()`
writes the query against only those tables, `run_sql()` executes it. The model
never sees a table selection did not return.

```
BIRD dev, all 1,534 questions, claude-opus-5-5, scored by BIRD's evaluation_ex.py (2026-10-22)

  EXECUTION ACCURACY        77.12%
    simple       (925)      80.97%
    moderate     (464)      71.34%
    challenging  (145)      71.03%
  repair calls (SQLite raised an error)       1 of 1,534
  asked again after the model declined       12 of 1,534
```

An earlier version of this section reported 68.0% on a seeded 150-question
sample with claude-opus-5. The full set with the current model is above, and
the sample runner (`benchmarks/bird_e2e.py`) is still in the repo.

Rows are compared as sets, which is how BIRD's own evaluator scores them:
order is not graded.

Three things this is not. It is **not yet a leaderboard placing** -- that needs
the held-out test set, which only the BIRD team can run; the submission package
in [`benchmarks/results/bird_dev/`](benchmarks/results/bird_dev/) was sent to
them on 2026-10-22 and this page will carry whatever number they report. It is
**one model call per question**, so it is not comparable in cost with the
multi-candidate systems at the top of the main board. And BIRD's own
`evidence` string is passed through with the question, which is what the
benchmark intends and what published systems do, but it is a hint a real user
would have to write.

Run it yourself with `python benchmarks/bird_minidev.py --questions dev.json
--db-root <dev_databases> --provider anthropic --model claude-opus-5-5`; the
Mini-Dev and UniQL Oracle runs are in the same folder, with their exact commands
in their READMEs.

## Reproducing this

```bash
pip install schemagate pandas pyarrow

# Spider dev questions and the schema dump (two public files)
curl -L -o spider_dev.parquet \
  https://huggingface.co/datasets/xlangai/spider/resolve/main/spider/validation-00000-of-00001.parquet
curl -L -o spider_schema.json \
  https://huggingface.co/datasets/richardr1126/spider-schema/resolve/main/spider_schema_rows_v2.json
python benchmarks/spider.py

# BIRD dev (346 MB from the official mirror)
curl -L -o bird_dev.zip https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip
python -c "import zipfile; z=zipfile.ZipFile('bird_dev.zip'); z.extract('dev_20240627/dev.json'); z.extract('dev_20240627/dev_tables.json')"
python benchmarks/bird.py

# Spider 2.0-lite: questions, plus a sparse clone for schemas and gold SQL
curl -L -o spider2_lite.jsonl   https://raw.githubusercontent.com/xlang-ai/Spider2/main/spider2-lite/spider2-lite.jsonl
git clone --depth 1 --filter=blob:none --sparse https://github.com/xlang-ai/Spider2.git
git -C Spider2 config core.longpaths true          # Windows: paths exceed 260 chars
git -C Spider2 sparse-checkout set   spider2-lite/resource/databases spider2-lite/evaluation_suite/gold
python benchmarks/spider2.py
```

`SCHEMAGATE_AUTO_EMBEDDER=0` forces the hashed embedder if you have the
sentence model installed and want the base-install numbers.
`SPIDER2_NO_DESC=1` reruns the Spider 2.0 script with descriptions
suppressed, which is the ablation above.

## What these numbers are not

The retrieval numbers are not a leaderboard placing: the boards score
generated SQL, and table recall is one step before it. They are not end-to-end
accuracy either — a perfect table selection still leaves the model to write a
correct query, which is why the execution-accuracy section at the top exists.
And the execution-accuracy numbers are not yet a verified placing: the Mini-Dev
rows are self-reported until BIRD merges them, and the test-set result is
BIRD's to report.

What they are is a claim you can check without trusting me, on data neither
of us controls.
