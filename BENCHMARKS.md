# schemagate on Spider, BIRD and Spider 2.0

Every other number in this repo is measured on schemas I invented. That is
fine for catching regressions and worth very little to anyone else: a schema
whose questions happen to share vocabulary with its own table names will
flatter any retriever, and you have no way to check that I did not do exactly
that.

So here are the same measurements on the public text-to-SQL benchmarks.
The data is downloaded from the original sources, the scripts are in
[`benchmarks/`](benchmarks/), and the whole thing reruns in about three
minutes.

## What is being measured

schemagate does not write SQL, so it cannot appear on either leaderboard —
those score execution accuracy of generated queries. What it does is pick the
tables, so what is scored here is **table recall**: given a question, does the
selected set contain every table the benchmark's own reference SQL reads.

Two numbers per row:

- **all gold tables present** — the strict one. Every table the answer needs
  was selected. A query missing one table does not run.
- **per-table recall** — the fraction of gold tables found, averaged over
  questions. Kinder, and useful for seeing how near a miss was.

## Spider (dev): 1,034 questions, 20 databases

```
PER-DATABASE                    all gold present     per-table recall
  top_k=3                            98.3%                99.1%
  top_k=5                           100.0%               100.0%
```

**This row is a floor, not a result.** Spider databases have a median of
three tables and a maximum of eleven. Picking five out of three is not
retrieval, and any method that returns the whole schema scores 100% here. It
is reported so you can see nothing is broken, and for no other reason.

The interesting setting is the one Spider does not ship: put every database
in one catalog and stop telling it which one to look in.

```
POOLED — all 166 Spider databases, 876 tables, no database hint

                      all gold present     per-table recall
  top_k=5                  71.4%                76.3%
  top_k=10                 82.6%                86.5%
  top_k=20                 92.9%                94.7%
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
  top_k=3                            88.3%                94.7%
  top_k=5                            96.5%                98.5%

POOLED (75 tables, no hint)
  top_k=5                            83.0%                90.6%
  top_k=10                           91.1%                95.1%
```

BIRD ships an `evidence` string per question — a human hint like *"eligible
free rate = Free Meal Count / Enrollment"*. Retrieval is measured without it
above, because the honest question is what the user's words alone can find.
With it, which is what a real caller would pass through:

```
PER-DATABASE, question + evidence
  top_k=3                            90.7%                96.0%
  top_k=5                            97.9%                99.1%

POOLED, question + evidence
  top_k=5                            85.7%                92.8%
  top_k=10                           93.9%                97.0%
```

## Spider 2.0-lite: the one built for real schemas

Spider 1.0 databases have a median of three tables, which is why the pooled
setting had to be invented to say anything at all. Spider 2.0 needs no such
invention: 162 databases and 7,892 tables taken from real BigQuery and
Snowflake warehouses, a median of 14 tables per database and a maximum of
785. (The 103 databases the usable questions actually touch run slightly
larger, median 15 -- which is where the other figure in this file came from.) Retrieval is the acknowledged bottleneck there rather than a formality.

Only the questions whose gold SQL is public are usable -- the rest is held
out -- which leaves 247 across 103 databases.

Of those 247, the gold SQL names at least one table this loader can resolve
for 203, across 95 databases. The other 44 name nothing resolvable, and they
are where the ablation below is measured *from* rather than *on*: a paired
comparison needs both arms scored over the same questions, so it uses the 203,
while any figure meant to be read as recall uses 247 and counts an unresolved
question as a miss. Both denominators are printed against every number here,
because the first is a comparison set and the second is the result.

```
247 questions, none excluded     all gold present     per-table recall
  top_k=5                             53.0%
  top_k=10                            64.0%
  top_k=20                            67.2%

for comparison, scoring only the 203 whose gold tables resolve:
  top_k=5    64.5%      top_k=10   77.8%      top_k=20   81.8%
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
  now      67.2% @20   166/247, every usable question counted
```

Re-measured after the long-path fix reached `benchmarks/cap_sweep.py` and
`benchmarks/prose_coverage.py`: **67.2% is unchanged**, 166 of 247 at k=20 with
the MiniLM embedder and descriptions left alone. All 7,892 schema files are
readable now; none are skipped.

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

## What the dropped questions say about the tool

They are not noise. Spider 2.0's `ga4` database is 92 tables named
`events_20201101` through `events_20210131`, and `ga360` is 366 of the same
shape. They differ by a date, which no embedder can reason about, so a
question about January selected twelve tables from November -- measured -- and
the model correctly refused a question it had been handed the wrong month for.

Collapsing a family of date-suffixed siblings into one entry named with a
wildcard took the end-to-end run from 0 of 3 questions producing SQL to 3 of
3 executing. That is implemented in `benchmarks/spider2_e2e.py` and **not yet
in the library**, which is where it belongs: warehouses are full of dated
partitions and schemagate currently treats every day as its own table.

## The embedder, on data I did not write

`pip install schemagate` uses a hashed n-gram vectoriser; installing
`schemagate[huggingface]` switches it to a sentence model automatically. On my
own schemas that was worth +3 questions out of 98, which is thin evidence.
On Spider pooled:

```
876 tables, no hint        hashed      MiniLM
  top_k=5                   71.4%   →   75.3%
  top_k=10                  82.6%   →   88.1%
  top_k=20                  92.9%   →   95.8%
```

Consistent, and larger than my own benchmarks suggested. Then Spider 2.0 said
something different:

```
203-question comparison set     hashed      MiniLM
  top_k=5                     64.0%   →   64.5%
  top_k=10                    78.3%   →   77.8%
  top_k=20                    83.3%   →   81.8%

over all 247 usable questions   hashed      MiniLM
  top_k=5                     52.6%   →   53.0%
  top_k=10                    64.4%   →   64.0%
  top_k=20                    68.4%   →   67.2%
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
Spider 2.0-lite, n=203 in every cell, all gold tables resolvable
(percentages over all 247 usable questions in brackets)

  k    embedder      with prose            prose removed          delta
  5    hashed       130/203 64.0% (52.6%)  131/203 64.5% (53.0%)   +1 q
  5    MiniLM       131/203 64.5% (53.0%)  137/203 67.5% (55.5%)   +6 q
  10   hashed       159/203 78.3% (64.4%)  165/203 81.3% (66.8%)   +6 q
  10   MiniLM       158/203 77.8% (64.0%)  163/203 80.3% (66.0%)   +5 q
  20   hashed       169/203 83.3% (68.4%)  174/203 85.7% (70.4%)   +5 q
  20   MiniLM       166/203 81.8% (67.2%)  180/203 88.7% (72.9%)  +14 q
```

Run one cap per process (`benchmarks/cap_sweep.py` holds five sets of 95
catalogues otherwise, and died partway through twice on this machine, silently,
with the shell reporting success because the exit code came from the pipe).

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

So **"long descriptions hurt retrieval" remains a signal worth chasing, not a
result.** What the re-run adds is a sharper version of the thing to chase:
whatever prose is doing, it interacts with the vectoriser, and it shows up at
the widest cut. It is recorded here because the earlier draft of this file
asserted it, and a claim withdrawn should be visible rather than deleted.

The sweep also removes the obvious fix. Truncating descriptions at 200 or
1,000 words is indistinguishable from leaving them alone -- one to four
discordant pairs, p=1.000. Only deleting them entirely moves anything, and
that is the cell at p=0.065. There is no cap worth setting, so none is set.

For comparison, prose in the other two benchmarks:

```
Spider 1.0      0 of 876 tables have a description
BIRD            0 of  75
```

Both are bare names and columns, which is why the ablation could only be run
on Spider 2.0.

Indexing 876 tables takes 0.8s hashed and 9.3s with the sentence model.

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
BIRD dev, n=150 (seeded, stratified by database), claude-opus-5, top_k=10

  SQL written               146/150   97.3%
  executed without error    146/150   97.3%
  EXECUTION ACCURACY        102/150   68.0%
```

Rows are compared as sets, which is how BIRD's own evaluator scores them:
order is not graded.

Three things this is not. It is **not a leaderboard placing** -- that needs the
held-out test set and a formal submission, and nothing here has been submitted.
It is a **sample, not the full 1,534**, because every question is a
frontier-model call; the sample is seeded, so it is the same 150 every run, and
the per-database counts are proportional. And BIRD's own `evidence` string is
passed through with the question, which is what the benchmark intends and what
published systems do, but it is a hint a real user would have to write.

Run it yourself with `python benchmarks/bird_e2e.py`; `BIRD_SAMPLE=1534` does
the lot.

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

They are not a leaderboard placing, and schemagate is not eligible for one:
both boards score generated SQL, and this writes none. They are not
end-to-end accuracy either — a perfect table selection still leaves the model
to write a correct query.

What they are is a claim you can check without trusting me, on data neither
of us controls.
