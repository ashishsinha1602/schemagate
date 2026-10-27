# schemagate with LlamaIndex

LlamaIndex's text-to-SQL engines send the model table schemas. On a real
database there are too many to send. Picking which ones to send is a retrieval
problem, and it is also an access problem: that pick happens *before* anything
has checked what this caller is allowed to read.

`SchemagateRetriever` is a LlamaIndex retriever. It selects the tables a
question needs, from the set this caller may see. A table the caller can't
read is never a candidate, so it can't end up in the prompt.

```
pip install 'schemagate[llamaindex]'
```

## Use it like any retriever

```python
from schemagate import Catalog, Principal
from schemagate.integrations.llamaindex import SchemagateRetriever, prompt_fragment

cat = Catalog().bootstrap("postgresql://localhost/app")

retriever = SchemagateRetriever(
    cat,
    top_k=6,
    principal=Principal("okta:jdoe", roles={"finance"}),
)

nodes = retriever.retrieve("revenue by month")
ddl = prompt_fragment(nodes)   # one DDL block, ready for a prompt
```

Each selected object comes back as one `NodeWithScore`. The node text is the
object's DDL, and `score` is its selection score. The metadata carries
`name`, `kind`, `columns` and `reason`, which says how the object got in
(`hybrid`, `vector`, `lexical`, `covers`, `term`, `fk`, `pinned`; the table is
in [langchain.md](langchain.md#use-it-like-any-retriever)). `aretrieve` works
too.

## One retriever per caller

The principal is fixed when the retriever is built, so a query engine can't
forget to pass it. Leave it out and the caller is anonymous and sees only
unrestricted objects: it fails closed. `with_principal` gives a copy bound to
someone else, sharing the catalog, so making one per request costs nothing:

```python
hr = retriever.with_principal(Principal("okta:hr", roles={"payroll"}))
```

## What it saves

The model gets the few tables the question needs, not the whole schema. How
many prompt tokens that saves, measured per schema, is in the README under
[What it saves](../README.md#what-it-saves).
