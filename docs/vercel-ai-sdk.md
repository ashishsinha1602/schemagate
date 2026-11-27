# schemagate with the Vercel AI SDK

A text-to-SQL agent needs the schema in its prompt. On a database with a few
hundred tables the full listing outgrows the context window, and nothing has
checked which of those tables the person asking may read.

schemagate is an MCP server (and Python library) that gives the agent only the
tables a question needs, from the set the caller is allowed to see. Tables a
caller may not read are left out of the result entirely, and `run_query`
refuses SQL that names them. The AI SDK uses it through its own MCP client,
`@ai-sdk/mcp`, so there is no AI SDK-specific package.

## Install

```bash
npm install ai @ai-sdk/mcp
pip install "schemagate[mcp]"
```

The second line installs the `schemagate-mcp` server command. `--url demo`
starts it on a bundled 42-object sample schema with no database and no API key.
For your own database, add its driver extra (for example
`schemagate[mcp,postgres]`) and pass the SQLAlchemy URL in the
`SCHEMAGATE_DATABASE_URL` environment variable (`env` on the transport), not
on the command line.

## Connect and pin the caller

```ts
import { createMCPClient } from '@ai-sdk/mcp';
import { StdioMCPTransport } from '@ai-sdk/mcp/mcp-stdio';

const schemagate = await createMCPClient({
  transport: new StdioMCPTransport({
    command: 'schemagate-mcp',
    args: ['--url', 'demo'],
  }),
  // schemagate's server speaks the initialize handshake; start with it.
  protocolVersionDiscovery: false,
});

// Overwrite principal/roles on every schemagate call with the real caller,
// whatever the model wrote into the tool arguments.
function pinIdentity(tools, principal: string, roles: string[]) {
  return Object.fromEntries(
    Object.entries(tools).map(([name, t]: [string, any]) => {
      const params = t.inputSchema?.jsonSchema?.properties ?? {};
      if (!('principal' in params)) return [name, t]; // health, refresh_catalog
      return [name, { ...t, execute: (input, opts) => t.execute({ ...input, principal, roles }, opts) }];
    }),
  );
}

const all = await schemagate.tools();
const tools = pinIdentity(
  { select_schema: all.select_schema, run_query: all.run_query },
  'demo:ana', // from your own session or auth layer, never from the prompt
  [],
);
```

Leave out `protocolVersionDiscovery: false` and the connection fails: the
client first tries the `2026-07-28` discovery handshake, then falls back to
`initialize`, which the server refuses on that connection with error `-32022`.

## Use it from an agent

```ts
import { generateText, isStepCount } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';

try {
  const { text } = await generateText({
    model: anthropic('claude-opus-5-5'),
    tools,
    stopWhen: isStepCount(5),
    system:
      'Answer questions about the database. Call select_schema first, write one ' +
      'SELECT using only the tables it returns, then call run_query.',
    prompt: 'How many employees are in each department?',
  });
  console.log(text);
} finally {
  await schemagate.close();
}
```

The agent calls `select_schema`, writes the SQL itself from the DDL it gets
back, and runs it with `run_query`. The server needs no model key for this:
the agent's model writes the SQL. Any AI SDK model provider works in place of
`@ai-sdk/anthropic`.

## Who is asking: `principal` and `roles`

Every schemagate tool that reads the schema or data takes a `principal` (a
namespaced id such as `"demo:ana"` or `"okta:jdoe"`) and a list of `roles`.
A caller that sends neither is treated as anonymous and sees only unrestricted
tables.

In the demo schema, `hr_compensation` is restricted to the `payroll` role.
Calling the tools directly, with no model involved, shows the difference:

```ts
const call = { toolCallId: 'probe', messages: [] };
for (const [principal, roles] of [['demo:ana', []], ['demo:paula', ['payroll']]]) {
  const r = await all.run_query.execute(
    { sql: 'SELECT COUNT(*) AS n FROM main.hr_compensation', principal, roles },
    call,
  );
  console.log(principal, r.content[0].text);
}
```

| Caller | `list_objects` | `run_query("SELECT COUNT(*) AS n FROM main.hr_compensation")` |
| --- | --- | --- |
| `demo:ana`, no roles | 41 objects, `hr_compensation` not among them | refused: `not available to this caller: hr_compensation, main.hr_compensation` |
| `demo:paula`, `["payroll"]` | 42 objects | returns `[[40]]` |

The server believes the `principal` and `roles` it is sent. When a model fills
in tool arguments, it could send `roles: ['payroll']` because a user asked it
to. `pinIdentity` above closes that gap: it replaces whatever the model wrote
with the identity your application authenticated. With it in place, a call
that asks for `principal: 'someone-else', roles: ['admin']` still runs as
`demo:ana`.

Over stdio the only caller is your own process. If you run the server over
HTTP instead (the AI SDK's recommended transport for production), either put it
behind something that authenticates users, or set
`SCHEMAGATE_MCP_OAUTH_ISSUER` and `SCHEMAGATE_MCP_OAUTH_AUDIENCE` so the server
takes `principal` and `roles` from a signed token
([OAuth guide](https://github.com/ashishsinha1602/schemagate/blob/main/docs/oauth.md)).

To restrict tables in your own database, point `SCHEMAGATE_CATALOG_CONFIG` at
a JSON file such as `{"restrict": {"hr_compensation": ["payroll"]}}`.

## Tools

The server offers twelve tools, and every one is annotated `readOnlyHint: true`.
The AI SDK exposes that on each tool's `metadata.annotations`, so a
[`toolApproval`](https://ai-sdk.dev/docs/agents/tool-approvals) policy that
auto-runs only read-only tools lets all of them through without a prompt.

| Tool | What it does |
| --- | --- |
| `select_schema` | Picks the tables and views a question needs, scoped to the caller, and returns their DDL |
| `list_objects` | Lists every object the caller may see |
| `describe_object` | Full DDL for one object, if the caller may see it |
| `run_query` | Runs one read-only `SELECT`; refuses writes, multiple statements, and tables outside the caller's scope |
| `explain_query` | The database's query plan for one `SELECT` |
| `compare_queries` | Checks whether two `SELECT`s return the same rows |
| `optimize_query` | Suggests a faster rewrite, only when it is proven to return the same rows |
| `semantic_query` | Runs a query, then has the server's model filter or extract from a text column. Off unless the server sets `SCHEMAGATE_MCP_SEMANTIC=1` and a model |
| `answer` | Question in, rows out, using a model configured on the server. Without one, it returns the selection and asks the client to write the SQL |
| `deep_answer` | Multi-step answer for questions that need exploration. Needs a server-side model and `SCHEMAGATE_MCP_DEEP=1` |
| `refresh_catalog` | Re-reads the database schema |
| `health` | Server state, for a person or a load balancer |

An AI SDK agent has its own model, so `select_schema` plus `run_query` is the
usual pair, as in the example above.

## Tested with

`ai` 7.0.183, `@ai-sdk/mcp` 2.0.106, schemagate 1.20.0 from PyPI, Node 22,
on the bundled demo schema. The connection, the tool list, the identity pin
and the `run_query` results in the table were run as shown; the
`generateText` call needs your own model provider key.

## Results

On BIRD's hidden test set, scored by the BIRD team, schemagate with Claude
Opus 5.5 scores 74.34 execution accuracy
([BIRD leaderboard](https://bird-bench.github.io/)). On Spider 2.0-lite
warehouses with 50 or more tables, the median prompt is 91% smaller than
sending the full schema. Method and raw outputs:
[BENCHMARKS.md](https://github.com/ashishsinha1602/schemagate/blob/main/BENCHMARKS.md).

## References

- [schemagate on GitHub](https://github.com/ashishsinha1602/schemagate) (Apache-2.0)
- [schemagate on PyPI](https://pypi.org/project/schemagate/)
- [AI SDK: Model Context Protocol](https://ai-sdk.dev/docs/ai-sdk-core/mcp-tools)
- Using LangChain instead? [langchain-schemagate](https://pypi.org/project/langchain-schemagate/) is a LangChain retriever over the same selection.
