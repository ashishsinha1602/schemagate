# Architecture

schemagate sits between a database and a language model. A caller (a person, or
an agent acting for one) asks a question; schemagate decides which tables and
columns that caller may see, picks the few that the question needs, and hands
the model only those. Everything else in this document follows from one rule:
**an object the caller may not read never reaches the model, and never runs.**

## The path of one question

```
database ──introspect──▶ Catalog ──visibility──▶ allowed objects ──rank──▶ Selection ──render──▶ prompt
   ▲                       │                                                            │
   └──────── run_query ◀───┴──────────────── re-checked against the same visibility ◀──┘
```

1. **Introspect** (`introspect.py`, `dialects/`). SQLAlchemy reflection reads
   tables, views, columns, keys and comments. Dialect modules add what
   reflection misses (Oracle synonyms and comments, SQL Server schemas).
2. **Catalog** (`catalog.py`, `models.py`). Each object becomes a document:
   its DDL, comments, sample values and an embedding. The catalog is built once
   and stored (`store.py`, `stores/memory.py`, `stores/oracle.py`).
3. **Visibility** (`identity.py`, `grants.py`, `groups.py`, `rls.py`). Who the
   caller is and which roles they hold; which objects and columns those roles
   may read. Visibility comes from schemagate's own role lists, or from the
   database's GRANTs (`--restrict-from-grants`) so there is no second copy of
   the rules to drift. Row-level policies are probed as the caller.
4. **Rank** (`embedder.py`, `embedders/`, `rerank.py`, `learn.py`,
   `ontology.py`). Only *allowed* objects are scored. Lexical and vector
   similarity, foreign-key expansion, the organisation's vocabulary, and SQL
   that ran before narrow them to the few the question needs; an optional
   model reranks the short list.
5. **Render** (`models.py`). The selection becomes compact DDL for the prompt.
   Hidden columns are absent, not masked.
6. **Execute** (`mcp_server.py`, `answer.py`). If an agent runs SQL through the
   MCP server's `run_query`, the SQL is parsed and every table and column it
   names is checked against the caller's visibility again before anything
   runs. Quoted, bracketed and schema-qualified names, comma joins and
   `SELECT *` are resolved first, so they cannot be used to reach a hidden
   object.
7. **Record** (`audit.py`, `pq.py`). Optionally, every decision (who asked,
   what they were shown, what was refused) is written to an append-only log,
   hash-chained and signed with ML-DSA-65.

## Interfaces

| Interface | Module | For |
|---|---|---|
| Python API | `schemagate` (`Catalog`, `Selection`) | applications |
| LangChain retriever | `integrations/langchain.py` | LangChain agents |
| MCP server (stdio, streamable HTTP) | `mcp_server.py` | Claude, Cursor, any MCP client |
| Command line | `cli.py` | trying it, scripting, `schemagate audit` |
| Studio (local web page) | `studio.py`, `studio.html` | exploring a catalogue by hand |

All of them call the same `Catalog`; none has its own visibility logic.

## Trust boundaries

- **The database** is the source of truth for data and, with
  `--restrict-from-grants`, for permissions. schemagate never writes to it.
- **The caller's identity** comes from the application that embeds schemagate
  (the `principal` and `roles` arguments). schemagate trusts what it is given;
  authenticating the caller is the application's job.
- **The model** is untrusted. Anything it writes is checked before it runs.

## Optional parts

AI descriptions (`ai/`), Oracle storage, Hugging Face embedders, the MCP
server and the post-quantum audit log are extras (`pip install
"schemagate[...]"`). The core has no network dependency and runs on the
built-in demo schema with no database at all.
