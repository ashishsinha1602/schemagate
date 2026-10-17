# schemagate on the RBAC Text-to-SQL benchmark

On BIRD, schemagate scores **AC-F1 90.1** against **88.1**, the best result of the thirteen models
in *Benchmarking Text-to-SQL under Role-Based Access Control* (Fei, Jiang, Yang, Xiao; SIGMOD
2027), with the same model and scored by the authors' own evaluator. The model never sees the
restricted part of the schema, and **no query it produced read data outside the role's policy**. On
Spider it ties the same model (93.0) and is behind the paper's best Spider result (95.9, DeepSeek
V3.2-Reasoning).

| | schemagate (Claude Sonnet 4.5) | paper, same model | paper's best model |
|---|---|---|---|
| BIRD AC-F1 (higher is better) | **90.1** | 88.1 | 88.1 (the same model) |
| BIRD: answered a question the role may not ask | **5.4%** | 7.4% | 7.4% |
| Spider AC-F1 | 93.0 | 93.0 | **95.9** (DeepSeek V3.2-Reasoning) |
| Queries that read a forbidden table or column | **0** | not reported | not reported |

## The benchmark

Each question comes with a role and the columns that role may read. If the answer needs a column the
role cannot see, the right reply is "Sorry, I cannot answer." The paper's evaluator,
`evaluate_protocol_v2.py --fair_comparison --num_trials 5 --execute_sql`, scores five passes, each
pairing every question with one random role. It was run unmodified.

The paper finds that hiding the restricted schema is not enough on its own: models rarely refuse,
and patch an answer together from the columns that are left. Its best schema-only setup on BIRD still
answered 26.7% of the questions it should have refused.

## Every metric

Claude Sonnet 4.5 for schemagate and for the paper's best run. Percentages, mean ± standard
deviation over the five trials.

| BIRD dev, 10,175 rows | AC-F1 | SafeEX | Violation | Over-refusal | Forbidden-data SQL |
|---|---|---|---|---|---|
| **schemagate** | **90.14 ± 0.32** | **68.38 ± 1.07** | **5.44 ± 0.19** | 1.98 | **0.00** |
| schemagate without the scope check | 84.69 ± 0.69 | 69.14 ± 0.85 | 11.25 ± 0.44 | 1.23 | 3.78 |
| Paper's best: policy in the prompt | 88.12 ± 0.90 | 65.02 ± 0.89 | 7.37 ± 0.49 | 1.81 | not reported |
| Paper's best schema-only baseline (GPT-5-mini) | 72.46 | not reported | 26.72 | 0.33 | not reported |

| Spider dev, 6,926 rows | AC-F1 | SafeEX | Violation | Over-refusal | Forbidden-data SQL |
|---|---|---|---|---|---|
| **schemagate** | **93.02 ± 0.37** | 78.87 ± 1.05 | 5.05 ± 0.49 | **2.59** | **0.00** |
| schemagate without the scope check | 90.68 ± 0.31 | 79.56 ± 1.05 | 8.67 ± 0.57 | 1.91 | 2.01 |
| Paper, same model: policy in the prompt | 93.03 ± 0.48 | 80.99 ± 0.86 | 4.55 ± 0.22 | 3.01 | not reported |
| Paper's best on Spider: DeepSeek V3.2-Reasoning | **95.94 ± 0.37** | 75.73 ± 1.19 | **1.97 ± 0.25** | 2.36 | not reported |

**Violation** is the benchmark's own measure: any answer to a question the role may not ask, even one
that reads only permitted columns. **Forbidden-data SQL** is stricter: a query that touches a table or
column outside the policy. schemagate refuses those before they run, so it is zero by construction.

## Re-scored without the questions used for tuning

The wording of one prompt line was chosen on the first 100 BIRD questions, which are part of the test
set. With them removed from every trial (1,433 questions per trial), scored with the evaluator's own
`score_cases()` on its per-case output:

| BIRD, 1,433 questions per trial | AC-F1 | SafeEX | Violation | Over-refusal | Forbidden-data SQL |
|---|---|---|---|---|---|
| **schemagate** | **90.08 ± 0.25** | 69.31 ± 1.37 | **5.42 ± 0.20** | 2.05 | **0.00** |
| schemagate without the scope check | 84.54 ± 0.85 | 70.13 ± 1.08 | 11.36 ± 0.49 | 1.24 | 3.84 |

Spider was not used for any choice.

## What schemagate does with each question

1. **The role's policy becomes visibility.** A table or column the role may not read is absent from
   the prompt; the model never sees its name.
2. **One line says the view is partial**, without naming what is withheld, so a question that needs
   hidden data is declined instead of approximated (`Catalog.restriction_notice`, on by default
   from 1.6.0).
3. **Every query passes a scope check before it runs.** SQL that names anything outside the policy
   is refused. Removing this step doubles the violation rate on BIRD.

The paper's best configuration instead shows the model the full schema with the policy beside it.

## Limits of this result

- One model, Claude Sonnet 4.5; the paper reports thirteen. Same model name, not necessarily the
  same API snapshot.
- BIRD databases are the 2024-06-27 dev release; the paper used 2025-11-06. Gold SQL comes from the
  benchmark file, unchanged.
- The prompts differ by design: the paper's is its own, this is schemagate's shipped pipeline (top 6
  tables, default embedder, no reranker).
- Adding BIRD's column descriptions made the result worse on a 100-question pilot, so these runs use
  the schema as the database reflects it.
- Not yet reproduced by the benchmark's authors; the result has been
  [sent to them for verification](https://github.com/2020dfff/RBAC-Text2SQL-Benchmark/issues/2).

## A second benchmark: Spider-ACL

*Role-Conditioned Refusals* (Klisura et al., Findings of EACL 2026) gives each Spider question four
roles as PostgreSQL GRANTs and labels it with what PostgreSQL allowed: 19,624 records, 11,529 of them
DENY. Scored as that paper does (refusal as the positive class), claude-sonnet-5-5, all 19,624:

| | refusal F1 | false permits | queries reading data the role was not granted |
|---|---|---|---|
| **schemagate** | **0.984** (P 0.985, R 0.982) | **1.8%** | **0 of 8,128 answered** |
| schemagate, 600 records never used for tuning | 0.986 | 1.7% | 0 |
| paper's best (LoRA-tuned Mistral-7B) | 0.933 | not reported | not reported |

The zero was checked independently of the scope check that enforces it: every answered query was
parsed with sqlglot and compared with the role's GRANTs. A false permit is a forbidden question
answered from columns the role may read, never a read of withheld data. The paper's systems are
2024-25 models; execution accuracy and BIRD-ACL were not run. Full write-up in
[BENCHMARKS.md](https://github.com/ashishsinha1602/schemagate/blob/main/BENCHMARKS.md#access-control-a-second-benchmark-spider-acl);
every decision and query in
[`benchmarks/results/acl/`](https://github.com/ashishsinha1602/schemagate/tree/main/benchmarks/results/acl).

## Reproduce it

```
pip install "schemagate[ai]==1.6.0"
git clone https://github.com/ashishsinha1602/schemagate && cd schemagate
python benchmarks/rbac_text2sql.py --dataset bird --notice --trials 5 \
  --rbac-json <benchmark>/data/selected/bird/column_level_rbac_dataset_bird_v3_no_sm.json \
  --db-dir <bird>/dev_databases --out out/bird --model claude-sonnet-4-5
cd <benchmark>/rbac-exp && python evaluation/evaluate_protocol_v2.py \
  --role_json <...bird json> --prediction_path out/bird_sg_notice.sql \
  --db_dir <bird>/dev_databases --fair_comparison --num_trials 5 --execute_sql
```

About $195 of API calls for both datasets. The evaluator's reports for all four runs are in
[`benchmarks/results/rbac/`](https://github.com/ashishsinha1602/schemagate/tree/main/benchmarks/results/rbac).
Paper: [arXiv 2607.22115](https://arxiv.org/abs/2607.22115) ·
benchmark and evaluator: [2020dfff/RBAC-Text2SQL-Benchmark](https://github.com/2020dfff/RBAC-Text2SQL-Benchmark).
