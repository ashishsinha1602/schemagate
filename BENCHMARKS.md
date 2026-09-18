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
that is the p=0.001 cell above -- which, as that paragraph says, does not
carry the claim either. There is no cap worth setting, so none is set.

For comparison, prose in the other two benchmarks:

```
Spider 1.0      0 of 876 tables have a description
BIRD            0 of  75
```

Both are bare names and columns, which is why the ablation could only be run
on Spider 2.0.

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
