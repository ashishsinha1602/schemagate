# schemagate with Strands Agents

A text-to-SQL agent needs the schema in its prompt. On a database with a few
hundred tables the full listing outgrows the context window, and nothing has
checked which of those tables the person asking may read.

schemagate is an MCP server (and Python library) that gives the agent only the
tables a question needs, from the set the caller is allowed to see. Tables a
caller may not read are left out of the result entirely, and `run_query`
refuses SQL that names them. A Strands agent uses it through the SDK's own
`MCPClient`; there is no Strands-specific package.

## Install

```bash
pip install strands-agents
```

The server runs through `uvx`, which comes with [uv](https://docs.astral.sh/uv/),
so schemagate itself needs no separate install. To install it instead:
`pip install "schemagate[mcp]"`, then use `schemagate-mcp` as the command below.

`--url demo` starts the server on a bundled 42-object sample schema with no
database and no API key. For your own database, add its driver extra (for
example `schemagate[mcp,postgres]`) and pass the SQLAlchemy URL in the
`SCHEMAGATE_DATABASE_URL` environment variable, through `StdioServerParameters(env=...)`,
rather than on the command line.

## Use it from a Strands agent

```python
from mcp import stdio_client, StdioServerParameters
from strands import Agent
from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry
from strands.tools.mcp import MCPClient

server = StdioServerParameters(
    command="uvx",
    args=["--from", "schemagate[mcp]", "schemagate-mcp", "--url", "demo"],
)
schemagate = MCPClient(lambda: stdio_client(server))


class PinIdentity(HookProvider):
    """Overwrite principal/roles on every schemagate call with the real caller."""

    def __init__(self, principal: str, roles: list[str]):
        self.principal, self.roles = principal, roles

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self.pin)

    def pin(self, event: BeforeToolCallEvent) -> None:
        tool = event.selected_tool
        params = tool.tool_spec["inputSchema"]["json"].get("properties", {}) if tool else {}
        if "principal" in params:  # schemagate tools only; health/refresh_catalog take none
            event.tool_use["input"]["principal"] = self.principal
            event.tool_use["input"]["roles"] = self.roles


agent = Agent(
    tools=[schemagate],
    hooks=[PinIdentity("demo:ana", roles=[])],
    system_prompt=(
        "Answer questions about the database. Call select_schema first, write one "
        "SELECT using only the tables it returns, then call run_query."
    ),
)
agent("How many employees are in each department?")
```

The agent calls `select_schema`, writes the SQL itself from the DDL it gets
back, and runs it with `run_query`. The server needs no model key for this:
the agent's model writes the SQL.

## Who is asking: `principal` and `roles`

Every schemagate tool that reads the schema or data takes a `principal` (a
namespaced id such as `"demo:ana"` or `"okta:jdoe"`) and a list of `roles`.
A caller that sends neither is treated as anonymous and sees only unrestricted
tables.

In the demo schema, `hr_compensation` is restricted to the `payroll` role.
Calling the tools directly, with no model involved, shows the difference. This
uses its own client, because the one passed to `Agent` is already running:

```python
import json

probe = MCPClient(lambda: stdio_client(server))
with probe:
    for who in ({"principal": "demo:ana", "roles": []},
                {"principal": "demo:pat", "roles": ["payroll"]}):
        result = probe.call_tool_sync(
            tool_use_id="select-1",
            name="select_schema",
            arguments={"question": "salary by employee", **who},
        )
        print(who["principal"], json.loads(result["content"][0]["text"])["objects"])
```

```text
demo:ana ['main.hr_employee', 'main.v_employee_headcount', 'main.sales_order_status', ...]
demo:pat ['main.hr_compensation', 'main.hr_employee', 'main.v_employee_headcount', ...]
```

| Caller | `select_schema("salary by employee")` | `run_query("SELECT COUNT(*) FROM hr_compensation")` |
| --- | --- | --- |
| `demo:ana`, no roles | `hr_compensation` not in the result | refused: `not available to this caller: hr_compensation` |
| `demo:pat`, `["payroll"]` | `hr_compensation` included | returns the row |

The server believes the `principal` and `roles` it is sent. When a model fills
in tool arguments, it could send `roles=["payroll"]` because a user asked it
to. The `PinIdentity` hook above closes that gap: it runs before every tool
call and replaces whatever the model wrote with the identity your application
authenticated. Set it from your own session or auth layer, not from the
prompt.

Over stdio the only caller is your own process. If you run the server over
HTTP instead, either put it behind something that authenticates users, or set
`SCHEMAGATE_MCP_OAUTH_ISSUER` and `SCHEMAGATE_MCP_OAUTH_AUDIENCE` so the server
takes `principal` and `roles` from a signed token
([OAuth guide](https://github.com/ashishsinha1602/schemagate/blob/main/docs/oauth.md)).

To restrict tables in your own database, point `SCHEMAGATE_CATALOG_CONFIG` at
a JSON file such as `{"restrict": {"hr_compensation": ["payroll"]}}`.

## Tools

All nine tools are read-only.

| Tool | What it does |
| --- | --- |
| `select_schema` | Picks the tables and views a question needs, scoped to the caller, and returns their DDL with a reason for each pick |
| `list_objects` | Lists every object the caller may see |
| `describe_object` | Full DDL for one object, if the caller may see it |
| `run_query` | Runs one read-only `SELECT`; refuses writes, multiple statements, and tables outside the caller's scope |
| `semantic_query` | Runs a query, then has the server's model filter or extract from a text column. Off unless the server sets `SCHEMAGATE_MCP_SEMANTIC=1` and a model |
| `answer` | Question in, rows out, using a model configured on the server (`SCHEMAGATE_MCP_PROVIDER`, `SCHEMAGATE_MCP_MODEL`). Without one, it returns the selection and asks the client to write the SQL |
| `deep_answer` | Multi-step answer for questions that need exploration. Needs a server-side model and `SCHEMAGATE_MCP_DEEP=1` |
| `refresh_catalog` | Re-reads the database schema |
| `health` | Server state, for a person or a load balancer |

A Strands agent has its own model, so `select_schema` plus `run_query` is the
usual pair. To give the agent only those, pass
`tool_filters={"allowed": ["select_schema", "run_query"]}` to `MCPClient`.

## Results

On BIRD Mini-Dev, schemagate with Claude Opus 5.5 scores 81.0 (SQLite), 72.6
(PostgreSQL) and 72.4 (MySQL) execution accuracy, one query per question.
These are self-reported results listed on the
[BIRD Mini-Dev leaderboard](https://bird-bench.github.io/), the highest in each
dialect at the time of writing. On Spider 2.0-lite warehouses with 50 or more
tables, the median prompt is 91% smaller than sending the full schema. Method
and raw outputs:
[BENCHMARKS.md](https://github.com/ashishsinha1602/schemagate/blob/main/BENCHMARKS.md).

## References

- [schemagate on GitHub](https://github.com/ashishsinha1602/schemagate) (Apache-2.0)
- [schemagate on PyPI](https://pypi.org/project/schemagate/)
- [Strands MCP tools](https://strandsagents.com/docs/user-guide/sdk/tools/mcp-tools/)
- Using LangChain instead? [langchain-schemagate](https://pypi.org/project/langchain-schemagate/) is a LangChain retriever over the same selection.
