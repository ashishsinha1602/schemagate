# Vanna is archived. What to use instead

Vanna's repository was archived on 29 March 2026
(https://github.com/vanna-ai/vanna) and is read-only. It had 23.8k stars
and an MIT licence when it stopped.

This page is written by the author of one of the tools mentioned on it, so
here is the conflict of interest up front: **schemagate is not a Vanna
replacement, and if you are looking for one, two of the three projects
below are a better place to start than this one.** Vanna was end to end —
train, ask, generate SQL, run it, draw a chart. schemagate is one step of
that pipeline. What follows is the honest version of where each thing fits.

## First: do you actually need to migrate?

Archived does not mean broken. The licence is MIT and the code is still
there, so the options that cost nothing are real ones:

- **Keep running it.** Pin the version you have. Nothing stops working
  because a repository went read-only. What you lose is security patches
  and new model support, which matters on the LLM-client side and hardly
  at all in the schema-handling code.
- **Fork it.** MIT lets you. If you have local patches already, this is
  less work than a migration.

Migrate when you need something Vanna did not do, not because the badge on
the repo changed.

## The actual replacements

Stars and status as of September 2026, from each project's own repository:

| | what it is | stars | licence |
|---|---|---|---|
| [WrenAI](https://github.com/Canner/WrenAI) | Closest to end-to-end Vanna: a GenBI platform with a semantic layer over your warehouse. The heaviest of the three, and the one with a modelling layer. | 17.7k | see repo |
| [DB-GPT](https://github.com/eosphoros-ai/DB-GPT) | Agentic data assistant — connects to databases and files, writes and runs SQL, builds reports. Broader than text-to-SQL. | 20.0k | MIT |
| [DataLine](https://github.com/RamiAwar/dataline) | Self-hosted chat-with-your-data with charts. Much smaller and much simpler; the quickest to stand up. | 1.6k | GPL-3.0 |

If you want one recommendation: **WrenAI** if you have a warehouse and want
a semantic layer, **DB-GPT** if you want an agent, **DataLine** if you want
the short path to something running.

## Where schemagate fits, and where it does not

schemagate does not generate SQL, does not run it, does not chat, and is
not an agent. It decides *which tables go in the prompt*, per caller. You
add it to whichever of the above you pick — or to a forked Vanna, or to a
hand-rolled loop — and keep everything else.

The reason to bother is one thing none of them do, including Vanna.

## What Vanna did with identity, and what it didn't

Vanna 2.0 resolves a `User` with `group_memberships`, gates *tools* on those
groups, and applies row-level security *when the SQL runs*:

```
Execute SQL tool (user-aware) → Apply row-level security → Filtered results
```

That protects the data. It does not protect the answer. The model still sees
the whole schema, still writes valid SQL against a table this user can't
read, RLS strips every row, and the user is told "no records found" — a
wrong answer delivered with confidence. Nothing in that chain can tell the
difference between "there is no data" and "you are not allowed to see it."

schemagate works one step earlier. It decides which tables the model is shown,
per caller, before any SQL exists. A restricted table is not de-ranked; it is
absent from the prompt.

## If you are keeping Vanna's shape: the mapping

| Vanna | schemagate |
|---|---|
| `vn.train(ddl=...)` (1.x) / tools reading a configured DB (2.x) | `cat = Catalog().bootstrap("postgresql://…")` — reflects the schema once |
| `vn.train(documentation=...)` | `cat.hint("orders", "…")` — a human note that outranks everything |
| `User(id=…, group_memberships=[…])` | `Principal("okta:jdoe", roles={…})` |
| a tool's `access_groups` | `cat.restrict("hr_compensation", ["payroll"])` — on the *table*, not the tool |
| `vn.ask(question)` / `chat_sse` | `sel = cat.select(question, principal=p)`; put `sel.prompt_fragment()` in your SQL prompt |
| `vn.generate_sql(...)` | not schemagate's job — keep whatever model call you have |

schemagate is not an agent, a chat server, or a SQL generator. It is the schema
selection step. Keep your Vanna agent, LangChain chain, or hand-rolled loop;
replace the part that decides what DDL goes in the prompt.

## Minimal example

```python
from schemagate import Catalog, Principal

cat = Catalog().bootstrap("postgresql://localhost/app")
cat.restrict("hr_compensation", ["payroll"])          # once, at startup

def build_prompt(question, user):                      # per request
    p = Principal(f"okta:{user.id}", roles=set(user.group_memberships))
    sel = cat.select(question, top_k=6, principal=p)
    return f"Schema:\n{sel.prompt_fragment()}\n\nQuestion: {question}"
```

Your `User` object drops straight in: `id` becomes the principal's subject,
`group_memberships` become its roles. Whatever generated SQL before still
does — it just never sees `hr_compensation` unless the caller holds
`payroll`.

## If you're using an agent framework

Cursor, Windsurf, or any MCP client: run `python -m schemagate.mcp_server`
and the agent calls `select_schema(question, principal, roles)` as a tool.
LangChain: `SchemagateRetriever` is a `BaseRetriever`. Both are in the README.

## What you lose, honestly

Vanna trained on question/SQL pairs and learned from feedback. schemagate does
not learn; it reflects and ranks. If your accuracy came from a large
question–SQL memory, keep that memory and use schemagate only for the identity
gate. If it came from schema documentation, `cat.hint()` and
`cat.describe()` do the same job with less machinery.
