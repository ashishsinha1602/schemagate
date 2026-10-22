# BIRD dev set (1,534 questions): schemagate + Claude Opus 5.5

Execution accuracy **77.12** (simple 80.97, moderate 71.34, challenging 71.03), scored with BIRD's own
`evaluation_ex.py` (`predict_dev.ex.txt`). Run of 2026-10-22 with `benchmarks/bird_minidev.py --questions dev.json`:
one query per question; a repair call when SQLite errors (1 of 1,534); if the model declines it is asked once for
its best reading (12 of 1,534); no selection across runs; the gold SQL is never read. Original dev split (dev_20240627).

`schemagate_bird_submission.zip` is the package sent to the BIRD team for test-set evaluation: the runner, its
README with the exact commands, `requirements.txt`, and these dev predictions.
