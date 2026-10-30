# schemagate plugin for GitHub Copilot

A local, read-only MCP server that gives the model only the tables and columns
the caller may read, plus a skill for the select-schema, write-SQL, run-query
workflow.

```bash
copilot plugin install ashishsinha1602/schemagate:copilot-plugin
```

It runs `uvx --from "schemagate[mcp]==1.15.1" schemagate-mcp` (needs
[uv](https://docs.astral.sh/uv/)) against `demo`, a bundled 42-object sample
schema, so it works before you point it at anything. Try: "which tables hold
salary data?" as an anonymous caller, then with the `payroll` role.

## Your own database

The plugin's server is pinned to the demo schema. To use a real database, add
schemagate to your own MCP configuration with the URL in `env`, not in the
command arguments:

```json
{"mcpServers": {"schemagate": {
  "type": "stdio",
  "command": "uvx", "args": ["--from", "schemagate[mcp,postgres]==1.15.1", "schemagate-mcp"],
  "env": {"SCHEMAGATE_DATABASE_URL": "postgresql+psycopg://user:password@localhost/app"}}}}
```

Driver extras: `postgres`, `mysql`, `mssql`, `oracle` (SQLite needs none).
Restrictions and hints come from `SCHEMAGATE_CATALOG_CONFIG`, a JSON file; see
the [main README](https://github.com/ashishsinha1602/schemagate#readme).

## Tools

All nine are read-only: `select_schema`, `list_objects`, `describe_object`,
`run_query`, `semantic_query`, `answer`, `deep_answer`, `refresh_catalog`,
`health`. `run_query` refuses writes, more than one statement, and any object
the caller may not read. Every tool takes `principal` and `roles`; a caller
that omits them is anonymous and sees only unrestricted objects.

## Trust boundary

Over stdio the server believes the `principal` and `roles` the client sends. It
limits what the model is shown; it is not authentication. For a shared HTTP
deployment, use the OAuth mode described in the main README.

Apache-2.0.
