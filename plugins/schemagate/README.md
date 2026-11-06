# schemagate plugin for Claude Code

Ask Claude questions about a SQL database without pasting the schema. The
[schemagate](https://github.com/ashishsinha1602/schemagate) MCP server picks
only the tables each question needs (a median of 91.1% fewer schema tokens on
databases with 50+ tables), and only from the tables the caller may read.
#1 on the BIRD Mini-Dev text-to-SQL leaderboard (SQLite 81.0 / PostgreSQL 72.6
/ MySQL 72.4).

## Install

```
/plugin marketplace add ashishsinha1602/schemagate
/plugin install schemagate@schemagate
```

Needs [uv](https://docs.astral.sh/uv/) on your PATH (the server runs with `uvx`).

## Try it

With no database configured it opens `demo`, a bundled 42-table sample
schema. Ask: "which customers owe us money?"

## Your database

Set `SCHEMAGATE_DATABASE_URL` in your shell before starting Claude Code:

```
export SCHEMAGATE_DATABASE_URL="postgresql+psycopg://readonly@db.internal/app"
```

MySQL (`mysql+pymysql://`), Oracle (`oracle+oracledb://`), SQL Server
(`mssql+pyodbc://`) and SQLite (`sqlite:///path.db`) drivers are included.
Use a read-only database user.

## What's inside

- `.mcp.json`: the schemagate MCP server (`select_schema`, `run_query`,
  `describe_object`, `list_objects`, and more).
- `skills/schemagate-sql`: tells Claude to select the schema first, write one
  SELECT against that DDL only, run it through the read-only `run_query`, and
  report refusals as refusals.

## Privacy

The server runs on your machine and talks only to the database you point it
at. On first start `uvx` downloads the pinned packages from PyPI. After that,
with this plugin's settings, it makes no network calls of its own: no
telemetry and no model calls (table selection uses a built-in embedder that
downloads nothing). Identity-provider and group lookups exist but run only if
you configure them. It reads table structure and, through `run_query`, the rows of the
read-only SELECTs Claude runs; those rows go to Claude as tool results. It
stores nothing: its audit log and query memory stay in memory and are gone
when it exits, unless you name a file with `SCHEMAGATE_AUDIT_LOG` or
`SCHEMAGATE_MEMORY`. The optional `semantic_query` and `deep_answer` tools,
which send row text to a model provider you configure, stay off unless you
start the server with `SCHEMAGATE_MCP_SEMANTIC=1` or `SCHEMAGATE_MCP_DEEP=1`;
this plugin sets neither. The plugin's author runs no service and receives no
data.

Apache-2.0.
