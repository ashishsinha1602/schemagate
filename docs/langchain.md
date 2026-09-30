# schemagate with LangChain

A LangChain SQL agent sends the model your schema. On a small database that is
fine. On a real one it is the whole problem: `SQLDatabaseToolkit` lists every
table it can see, the listing alone outgrows the context window, and the agent
picks tables from a truncated view of a database it was never shown properly.

The usual answers are to hand-pick a table subset per question, or to raise the
context limit and pay for it. Both leave the same hole: the agent decides what
to read *before* anything has checked what this caller is allowed to read.

`SchemagateRetriever` is a drop-in LangChain retriever that selects the tables a
question needs, from the set this caller may see.

```
pip install 'schemagate[langchain]'
```

## Use it like any retriever

```python
from schemagate import Catalog, Principal
from schemagate.integrations.langchain import SchemagateRetriever

cat = Catalog().bootstrap("postgresql://localhost/app")

retriever = SchemagateRetriever(
    catalog=cat,
    top_k=6,
    principal=Principal("okta:jdoe", roles={"finance"}),
)

docs = retriever.invoke("revenue by month")
```

Each selected object comes back as one `Document`. `page_content` is its DDL,
ready to drop into a prompt. The metadata carries what was chosen and why:

```python
for d in docs:
    print(d.metadata["name"], d.metadata["kind"],
          round(d.metadata["score"], 4), d.metadata["reason"])
```

`reason` says how the object got in:

| reason | meaning |
| --- | --- |
| `hybrid` | ranked by both the lexical and the vector channel |
| `vector` | ranked by the vector channel only |
| `lexical` | ranked by the lexical channel only |
| `covers` | pulled in to cover a term nothing else answered |
| `fk` | a foreign-key target of something already chosen |
| `pinned` | named outright in the question |

That is worth logging. When an agent writes the wrong query, `reason` tells you
whether retrieval handed it the wrong tables or the model misused the right
ones -- two different bugs that look identical from the outside.

## Into a prompt

`prompt_fragment` joins the documents back into a single DDL block:

```python
from schemagate.integrations.langchain import prompt_fragment

schema = prompt_fragment(docs)
```

That string is what you interpolate into your SQL-writing prompt, in place of
the full schema dump.

## One retriever per caller

The principal is fixed at construction, on purpose. A retriever is usually
built once per request, and binding identity to it means a chain cannot forget
to pass it. If you need the same catalog for a different caller, ask for a copy:

```python
payroll_view = retriever.with_principal(
    Principal("okta:payroll-svc", roles={"payroll"})
)
```

The catalog and settings are shared; only the caller changes. Retrievers are
cheap, so build one per request rather than mutating a shared one.

## Why identity belongs in retrieval, not after it

A conventional pipeline retrieves tables, writes SQL, and finds out at
execution time that the caller has no grant. The model has already seen the
table name, the column names and the comments by then -- and if the database
enforces with row-level security rather than grants, the query runs and returns
nothing, which the agent reports as "no records found" rather than "denied".

Selecting inside the caller's visible set closes both. A table this caller
cannot read is never a candidate, so it never reaches the prompt and never
produces a query that comes back empty for the wrong reason.

See [row-level security](/schemagate/row-level-security/) for the measured
version of that failure on Oracle 26ai, and [the benchmarks](/schemagate/benchmarks/)
for table recall on Spider, BIRD and Spider 2.0.

## Settings

| argument | default | what it does |
| --- | --- | --- |
| `catalog` | required | the `Catalog` to select from |
| `principal` | `None` | the caller. `None` sees only unrestricted objects |
| `top_k` | `6` | how many objects to select before FK expansion |
| `expand_fks` | `True` | pull in foreign-key targets of selected objects |
| `max_columns` | `40` | columns per object in the rendered DDL |

`principal=None` is not "unscoped" -- it is a caller holding no roles, so
anything passed to `restrict()` is hidden from it. That is the fail-closed
default: forgetting to pass a principal shows less, never more.
