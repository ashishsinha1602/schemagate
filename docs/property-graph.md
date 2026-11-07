# The schema as a property graph

schemagate can build a graph of your schema from what the database already says, with no file to export and no model call.

```bash
pip install 'schemagate[graph]'     # sqlglot, to read joins and filters out of view SQL

schemagate graph --url postgresql://localhost/app --out schema.json
schemagate graph --url postgresql://localhost/app --format graphml --out schema.graphml
```

```python
graph = cat.graph(principal)        # nodes and edges this caller may see
graph.to_json()                     # or to_graphml(), for yEd, Gephi, networkx and most graph importers
```

| Nodes | Edges | |
|---|---|---|
| `Table`, `View`, `Endpoint` | `HAS_COLUMN` | table to column |
| `Column` | `REFERENCES` | a foreign key, declared or `inferred` from column names |
| `Concept` | `DERIVED_FROM` | a view to the tables its SQL reads |
| | `JOINS` | two tables a view's SQL joins, on these columns |
| | `MAPS_TO` | a concept to its table or column |
| | `BROADER` | a concept to a wider one |

`JOINS` is the useful one on a database that declares no foreign keys: the join is there in the view, even when no constraint says so.

**A graph belongs to one caller.** It follows the same rules as the prompt. An object or column the caller may not see is not a node, an edge needs both of its ends, and a concept that would name something withheld is left out whole. With no caller, restricted objects are left out.

**It doesn't change selection yet.** `select()` still works as it did. The graph is something you can look at, export or build on.

## Concepts, pulled from the database

```bash
schemagate ontology pull --url ... --config catalog.json         # review what it proposes
schemagate ontology pull --url ... --config catalog.json --save  # then keep it
```

```python
cat.pull_concepts()                 # a report; nothing changes
cat.pull_concepts(apply=True)
```

| The database says | The concept |
|---|---|
| comment "Customer master" on `cust_mstr` | "Customer master" finds `cust_mstr` |
| comment "Lifetime spend" on `ttl_amt` | "Lifetime spend" finds `ttl_amt` |
| a longer comment on `seg_cd` | "seg cd" carries it as a definition |
| `v_paid_invoices ... WHERE status = 'paid'` | "paid invoices" finds the view, and the prompt says what it already applies |
| `SUM(total_net) AS net_revenue` in a view | "net revenue" finds the column, and the prompt says how it is computed |

For a running MCP server, `SCHEMAGATE_ONTOLOGY_PULL=1` does this on every catalogue read, so a changed comment or view is picked up. It's off by default, because concepts change what gets selected.

What it won't do:

- **Replace your words.** A phrase the vocabulary already has is left alone.
- **Guess.** One phrase with two meanings is reported, not picked. So is a long comment on a column name other tables share.
- **Invent.** Key columns, comments that restate the name and upkeep notes ("Deprecated") are skipped. A term nobody wrote down still needs a person.
- **Widen access.** A pulled concept follows the same visibility rules as a written one.

A view's filter can contain literal values, such as `salary > 100000`, and they go into the prompt of any caller who may see everything the filter names. Check the report before you save it if your view definitions hold values you wouldn't show those callers.

How much pulled concepts improve answers hasn't been measured. They can only be as good as your comments and views.

## Joins from the query log

A warehouse that declares no foreign keys still has its joins written down: in the queries people run. `--query-log` reads the database's own statement store and turns a join seen at least twice, whose far side is a primary key, into an inferred foreign key, so FK expansion in `select()` follows it. The rest goes into the graph: `JOINS` edges with a count, `QUERIED_WITH` edges for tables read in one statement, and the filters a table is usually read with, as `common_filters` on its node.

```bash
schemagate graph --url ... --query-log              # the engine's statement store
schemagate graph --url ... --query-log queries.sql  # or a file of SQL, or JSONL with sql and count
schemagate ontology pull --url ... --query-log
```

```python
cat.learn_from_log(engine)          # or a path, or a list of SQL strings
```

For a running MCP server, `SCHEMAGATE_QUERY_LOG=1` does this on every catalogue read.

| Engine | Read from | Needs |
|---|---|---|
| PostgreSQL | `pg_stat_statements` | the extension, loaded and created |
| MySQL, MariaDB | `performance_schema.events_statements_summary_by_digest` | `performance_schema` on (MariaDB has it off by default) |
| Oracle | `V$SQL` | `SELECT ON V_$SQL` |
| SQL Server | `sys.dm_exec_query_stats` | `VIEW SERVER STATE` |
| SQLite | nothing; pass a file | |

**What is kept, and what never is.** One bounded, read-only query reads the store. Every literal in a statement is replaced with `?` before the statement is looked at, no statement text is stored anywhere, and a filter is kept only as `column = ?`. So an account number or an email address that someone once typed into a `WHERE` cannot reach the graph, the prompt or the report. `schemagate certify` checks exactly this on your engine. Without the privilege to read the store, the command says what is missing and changes nothing.

## The golden set: `schemagate certify`

One command on any SQLAlchemy URL creates a small schema under its own prefix, runs fixed questions with known answers through reflection, selection, visibility, pulled concepts, the graph and query-log mining, then drops everything it made. No model is called, so the verdict is about schemagate on your engine.

```bash
schemagate certify postgresql://user:pw@host/db
```

Checks that need something the engine or the user lacks (comments on SQLite, a readable statement store, Oracle's graph privilege) are reported as `SKIP` with the reason. A failure is a bug: please open an issue with the output.

## Which databases

| `schemagate certify` on a real server | Comments | View SQL | Query log | Built-in graph |
|---|---|---|---|---|
| Oracle (26ai Free 23.26) | `COMMENT ON` | as written | `V$SQL` | `CREATE PROPERTY GRAPH`, generated, run and enforced |
| PostgreSQL (16, and 19rc1) | `COMMENT ON` | Postgres's rewritten form | `pg_stat_statements` | not in the server |
| MySQL (8.4) | `COMMENT` | MySQL's rewritten form | `performance_schema` | none |
| MariaDB (11) | `COMMENT` | MariaDB's rewritten form | `performance_schema` | none |
| SQL Server (2022) | `MS_Description` | as written | `dm_exec_query_stats` | not generated |
| SQLite | it has none | as written | a file | none |

Every row was certified with the command above on that server. Other databases SQLAlchemy can reach should behave the same way, but they haven't been run; `schemagate certify` on yours will tell you.

## Oracle's built-in property graph

Oracle 23ai and later has `CREATE PROPERTY GRAPH` and `GRAPH_TABLE`, which run over your actual rows. schemagate can write that statement, for you to review and run. It never runs it.

```bash
schemagate graph --url oracle+oracledb://... --format sql --principal okta:analyst --role analyst --graph-name analyst_graph
```

- **Vertices** are the tables this caller may see that have a primary key.
- **Properties are listed by name**, because Oracle's default is every column of the table, withheld ones included. Edge tables say `NO PROPERTIES` for the same reason.
- **Edges** are foreign keys, inferred ones and joins read from view SQL, when they reach a key. Anything left out is listed in a comment at the top, along with how many edges were guessed, so you can check them.

Tested on Oracle AI Database 26ai Free (23.26): the statement was created and traversed, including a join known only from a view, a table pointing at itself, a bridge table and a table named `ORDER`. Reading a withheld column or a hidden table through the graph was refused by the database. `tests/test_graph_oracle_live.py` repeats this if you set `SCHEMAGATE_ORACLE_URL`.

Your database's privileges still decide who may query the graph: grant it only to the callers it was built for.

**`run_query` refuses `GRAPH_TABLE`.** A graph's labels and properties aren't table and column names, so the SQL check can't tell what such a query reads. Callers who go through schemagate write plain joins.

**PostgreSQL has no built-in property graph to generate for.** It was checked on 19rc1, which rejects the syntax, and the 19 release notes don't mention it. On PostgreSQL use the JSON or GraphML graph. Other databases get a clear refusal from `--format sql`.
