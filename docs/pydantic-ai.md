# schemagate for Pydantic AI

A [Pydantic AI](https://pydantic.dev/docs/ai/) capability that gives a text-to-SQL agent only the tables a question needs, from the ones the caller may read.

Most text-to-SQL prompts carry the whole schema, on every question. schemagate picks the tables offline, with no model call: a median **91.1% fewer schema tokens** on databases with 50+ tables. It is #1 on the [BIRD Mini-Dev leaderboard](https://bird-bench.github.io/) in all three dialects (SQLite 81.0, PostgreSQL 72.6, MySQL 72.4) and has retrievers for LangChain, LangGraph and LlamaIndex.

## Install

```bash
pip install 'schemagate[pydantic-ai]'
```

## Use it

```python
from pydantic_ai import Agent
from schemagate import Catalog, Principal
from schemagate.demo_schema import demo_catalog

from schemagate.integrations.pydantic_ai import SchemagateCapability

catalog = demo_catalog()  # or Catalog().bootstrap("postgresql://...") for your own database

agent = Agent(
    "anthropic:claude-haiku-4-5",
    capabilities=[SchemagateCapability(catalog, principal=Principal("okta:analyst", roles={"finance"}))],
)
result = agent.run_sync("Which customers owe us money, and how much?")
print(result.output)
```

The agent gets one tool, `select_schema(question)`, and instructions to call it before writing SQL. It returns the DDL for the top six tables plus the tables they join to.

## Who is asking

The tool takes a question and nothing else, so neither the model nor a prompt can choose who it is asking as. The caller comes from your application. For an agent that serves many users, pass a function of the run:

```
SchemagateCapability(catalog, principal=lambda ctx: ctx.deps.user)
```

A table the caller may not read is left out of the prompt entirely, not ranked low. With no caller, only tables with no role restriction are visible. If the function raises or returns something that isn't a `Principal`, the run stops.

This limits what the model sees. It doesn't run SQL, and it doesn't replace permissions in your database.

## Agent specs

```yaml
model: anthropic:claude-haiku-4-5
capabilities:
  - SchemagateCapability:
      roles: [finance]
      restrict:
        hr_compensation: [payroll]
```

```
from schemagate.integrations.pydantic_ai import SchemagateCapability

agent = Agent.from_file("agent.yaml", custom_capability_types=[SchemagateCapability])
```

Set `SCHEMAGATE_DATABASE_URL` in the environment to keep credentials out of the spec file, or pass `database_url` in the spec. `demo` loads the bundled schema.

## When it doesn't help

On a seven-table database there is little to cut (a median 8.8% on BIRD). And a selection can leave out a table the question needs: on the Spider 2.0 warehouses, every needed table was selected for 86.7% of questions. Measure recall on your own questions before relying on it, and raise `top_k` if you need to. The method and numbers are in [BENCHMARKS.md](../BENCHMARKS.md).
