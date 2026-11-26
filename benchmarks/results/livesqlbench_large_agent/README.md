# LiveSQLBench-Large-v1: schemagate + a Claude Code agent (Claude Opus 5.5)

**40.21% (193 of 480 tasks)**, scored with LiveSQLBench's own evaluator (`evaluation.py`, PostgreSQL, multi-thread):

| | |
|---|---|
| Instances | 480 |
| Passed | 193 |
| Execution errors | 3 |
| Timeouts | 0 |
| **Overall accuracy** | **40.21%** |

`report.txt` is the evaluator's full output, one line per task.

## How it works

For each task:

1. **schemagate picks the context.** From the task's database (about 1,000 columns each), it selects the 24 most relevant tables and the 10 most relevant External Knowledge entries for the question, instead of sending the whole schema.
2. **A Claude Code agent writes the SQL.** Claude Code (`claude -p`, model `opus` = Claude Opus 5.5, effort `high`, at most 14 turns) gets the selected schema, the knowledge entries and the task. Its only tool is a SQL runner on the task's database: it can inspect values and test its query. Every call is rolled back, so it can also test DDL/DML without changing anything.
3. The agent's final ```postgresql block is the prediction.

The system prompt is `SYSTEM` in `code/lsb_cc.py`. The task prompt is built by `task_prompt` in `code/lsb_agent.py`, and table selection is in `code/lsb_select.py`. No gold SQL or test cases are shown to the agent. Those fields are only used by the evaluator.

## Cost

The run used a Claude Max subscription. At Anthropic list prices, Claude Code reported **$937.19 in total, $1.95 per task** (average 4.2 agent turns per task).

## Files

- `predictions.jsonl`: `instance_id`, `selected_database`, `pred_sqls` for all 480 tasks. No gold fields.
- `report.txt`: the official evaluator output.
- `code/`: the runner (`lsb_cc.py`), prompt builder (`lsb_agent.py`), table and knowledge selection (`lsb_select.py`) and the agent's SQL tool (`lsb_sql.py`). The database credentials in `lsb_sql.py` are LiveSQLBench's published defaults for its local Docker image.

## Reproduce

Set up LiveSQLBench-Large-v1 locally (the `livesqlbench_postgresql_large_v1` Docker database and the task file with External Knowledge from the BIRD team), then:

```
python code/lsb_cc.py --out <dir>          # resumable; one Claude Code session per task
python evaluation.py --jsonl_file <dir>/predictions.jsonl --db_host livesqlbench_postgresql_large_v1 --db_port 5432 --output_dir <dir>/eval
```
