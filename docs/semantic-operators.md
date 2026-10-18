# Semantic operators: questions about what text says

SQL answers "how many invoices were raised in March". It cannot answer "which complaints ask for a
refund" when no column records it: the meaning is in free text. schemagate's semantic operators ask
a model about one text column of rows that a query has already returned.

| Operator | Does | Python | MCP |
|---|---|---|---|
| filter | keeps the rows whose text meets a criterion | `semantic_filter(provider, columns, rows, column, criterion)` | `semantic_query(sql, column, criterion=...)` |
| extract | adds a short answer per row | `semantic_extract(provider, columns, rows, column, instruction)` | `semantic_query(sql, column, extract=...)` |

## Access control comes first

The MCP tool runs the SQL through `run_query` before any model sees anything, so the scope check
applies as it does everywhere else. A query that names a table or column the caller may not read is
refused, and nothing is sent. The operators themselves never read the database: they only see rows
the caller's own query returned.

Row text is treated as data. Each value goes to the model as a numbered, quoted item, and the reply
is parsed for row numbers (filter) or `number: answer` lines (extract) only. Text planted in a row
can at most change which rows of that same result are kept. It cannot reveal anything the caller
could not already query.

## Off by default

These operators send the text of result rows to the configured model provider. The MCP server
exposes them only with:

```
SCHEMAGATE_MCP_SEMANTIC=1
SCHEMAGATE_MCP_PROVIDER=anthropic          # or openai, gemini, oci, local
SCHEMAGATE_MCP_MODEL=claude-haiku-5-5
```

Set without a model, the server refuses to start. `health` reports `semantic: true` when it is on.
At most 200 rows are judged per call, in batches of 20; rows beyond the cap are reported, never
silently dropped.

## Example

On the bundled demo database, with claude-haiku-5-5:

```
semantic_query("SELECT DISTINCT description FROM billing_invoice_line", "description",
               criterion="is a plant-based milk alternative")
-> judged 24 rows, kept: Coconut Milk 400ml, Oat Milk 1L
```
