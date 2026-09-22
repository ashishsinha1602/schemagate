# Text-to-SQL and row-level security: what schemagate does not yet see

schemagate's claim is that the model is never shown a table the caller may not
read. `restrict_from_grants()` makes that true by asking the database who may
read what — it reads `ALL_TAB_PRIVS` on Oracle, the equivalent elsewhere, and
marks each object with the roles that hold `SELECT` on it.

That is the right question for table-level permissions. It is the wrong
question for row-level security -- PostgreSQL's `ENABLE ROW LEVEL SECURITY`
and Oracle's Virtual Private Database -- which is how a great many shops
actually enforce access: the `GRANT` stays, and a policy silently appends a
predicate to every query, so two users running identical SQL get different
rows. Both are measured below, PostgreSQL first because that is where most
text-to-SQL against RLS runs.

## Measured: PostgreSQL 16 (RLS)

**PostgreSQL 16.15.** One table `employee_salary` (4 rows, 2 in dept
`SALES`) with `ENABLE ROW LEVEL SECURITY`; two login roles that both hold
`GRANT SELECT` -- `sgrls_r1` with a policy `USING (dept = 'SALES')`,
`sgrls_r2` with `USING (false)`; a predicate view `v_sales_salary AS SELECT *
FROM employee_salary WHERE dept = 'SALES'`; and the same view again as
`v_sales_salary_si`, created `WITH (security_invoker = true)`.

| | `sgrls_r1` -- admits `dept = 'SALES'` | `sgrls_r2` -- admits `false` |
|---|---|---|
| rows the reader can select | 2 of 4 | **0 of 4** |
| rows the predicate view returns | 2 | **2** |
| rows the `security_invoker` view returns | 2 | 0 |
| visible in `information_schema.tables` | yes | **yes** |
| columns in `information_schema.columns` | 4 | **4** |
| `SELECT` in `information_schema.table_privileges` | yes | **yes** |
| reader can read `pg_policies` | yes (2 policies) | **yes (2 policies)** |

Every dictionary answer is identical for a reader who gets two rows and one
who gets none -- the same finding as Oracle below. Then through the shipped
path -- `Catalog().bootstrap(...)` followed by `restrict_from_grants(cat,
engine)`, with the caller `Principal("db:sgrls_r2", roles={"sgrls_r2"})`:

```
selected and put in the prompt : ['v_sales_salary', 'employee_salary', 'v_sales_salary_si']
prompt fragment contains SALARY: True
rows that same caller can read : 0
rows the predicate view returns: 2
rows the security_invoker view : 0
```

### The view is the dangerous row

On Oracle the predicate view returns 0 rows for the reader whose policy admits
nothing: the policy follows through the view, nothing leaks, and the only
damage is a prompt describing a table the caller cannot use.

On PostgreSQL the same view returns **2 rows, with real salaries**, to a
reader whose policy on the base table admits `false`. A PostgreSQL view runs
with the privileges of its *owner*, not its caller, so the base table's
policy is evaluated for the owner -- here a superuser, for whom RLS does not
apply -- and the caller gets whatever the owner would. `GRANT SELECT` on the
view is the whole of the check. The catalogue, believing the grants, puts
`v_sales_salary` in the prompt; the model writes a correct query against it;
the database hands back two salaries this caller was never meant to see. That
is not a prompt describing an unusable table. That is a leak, and the
catalogue is the thing that pointed the model at it.

The `security_invoker` row is the fix, and it is the database's own
(PostgreSQL 15 and later): a view created `WITH (security_invoker = true)`
evaluates the base table's policy for the caller, and `sgrls_r2` gets 0 rows
through it. A predicate view over a policied table that is not
`security_invoker` should be treated as what it is -- a hole shaped exactly
like the policy -- and either recreated that way or not granted to roles the
policy is meant to bind.

## Measured: Oracle 26ai (VPD)

**Measured on Oracle AI Database 26ai (23.26.3.3.0)**, with a `DBMS_RLS`
policy on one table and two readers who both hold `SELECT`:

| | `SGVPD_R1` — policy admits `dept = 'SALES'` | `SGVPD_R2` — policy admits `1 = 0` |
|---|---|---|
| rows the reader can select | 2 of 4 | **0 of 4** |
| visible in `ALL_TABLES` | yes | **yes** |
| `SELECT` in `ALL_TAB_PRIVS` | yes | **yes** |
| columns in `ALL_TAB_COLUMNS` | 4 | **4** |
| reader can see the policy in `ALL_POLICIES` | yes | **yes** |

Then, through the shipped path — `Catalog().bootstrap(...)` followed by
`restrict_from_grants(cat, engine)`, with the caller carrying role
`SGVPD_R2`:

```
selected and put in the prompt : ['employee_salary', 'v_sales_salary']
prompt fragment contains SALARY: True
rows that same caller can read : 0
```

**So the claim does not hold under VPD.** The grant says yes, the policy says
no, and the catalogue believes the grant. The model is handed
`EMPLOYEE_SALARY` with every column including `SALARY`, writes a perfectly
good query against it, and gets nothing back. Nothing leaks — the database
still enforces the policy, which is the point of VPD — but the prompt now
contains the name and shape of a table this caller cannot use, which is
exactly what schemagate exists to prevent.

A predicate view is not a way out. `V_SALES_SALARY`, defined over the same
base table, returned **0 rows** for `SGVPD_R2` as well: the policy follows
through the view. That is correct behaviour and worth knowing — a view neither
escapes VPD nor restores access.

**Probed, same fixture, same database.** Two ways to ask Oracle what a user
gets, from the application's own connection:

| | `SGVPD_R1` | `SGVPD_R2` |
|---|---|---|
| rows as `ADMIN`, no identifier (baseline) | 4 | 4 |
| rows as `ADMIN` with `CLIENT_IDENTIFIER` set to the user | 4 | 4 — this policy keys on `SESSION_USER`, so the identifier is inconclusive |
| rows through proxy authentication, `ADMIN[user]` | **2** | **0** |
| `restrict_from_policies` after the grants: table still visible to the user | yes | **no** |

Proxy authentication is the `SET ROLE` of Oracle: the session user *is* the
proxied user, so a policy keyed on `SESSION_USER` fires for them. It needs
one statement from a DBA per user, `ALTER USER SGVPD_R2 GRANT CONNECT
THROUGH ADMIN`; without it the role is kept and the report prints that
statement. The client identifier needs no privilege and is the right probe
for the other kind of policy — one keyed on
`SYS_CONTEXT('USERENV','CLIENT_IDENTIFIER')`, the pattern Oracle documents
for connection-pooled applications — and it can only withhold: rows with no
identifier and none with it is a policy demonstrably reacting, rows on their
own prove nothing, and it defers to the proxy.

## What to do about it today

`restrict_from_grants()` is still right for table-level permissions and should
keep being used, and `restrict_from_policies()` (below) now runs after it on
every path that reads grants. Where the policy cannot be probed -- a
PostgreSQL connection that may not `SET ROLE`, an Oracle user the connection
may not proxy for -- add the restriction yourself, because you know the
policy and the catalogue does not:

```python
cat.restrict("employee_salary", ["payroll"])       # roles that VPD actually admits
```

or leave the object out of the catalogue entirely with `exclude=` at bootstrap
if no caller of this application should see it. On PostgreSQL, also recreate
any predicate view over a policied table `WITH (security_invoker = true)`, or
revoke it from the roles the policy binds -- that one is a leak, not a
usability problem, and it is fixed in the database, not in a prompt.

## The fix: `restrict_from_policies()`

The last row of each table is the useful one: **the reader can see the policy**.
`pg_policies` and `ALL_POLICIES` are readable by a user who holds the grant, so a catalogue built
as that user can find out that a policy exists on an object. `schemagate.rls`
does three things with that, and `--restrict-from-grants` (CLI, Studio) runs
them right after the grants:

1. **Flag it.** An object under a row-level policy is marked, and its DDL in
   the prompt carries one line -- *rows are filtered per caller by a row-level
   policy; an empty result may be the filter, not an absence* -- so the model
   does not report an empty result as a fact about the world.
2. **Probe it.** For each role the grant reader left on a policied object,
   ask the database what that role gets: on PostgreSQL `SET ROLE` and one
   row; on Oracle the client identifier and then proxy authentication, as
   measured above. A role that gets nothing loses the object, exactly as a
   missing grant would: on the fixtures above, `sgrls_r2` and `SGVPD_R2` no
   longer see the salary table and `sgrls_r1` and `SGVPD_R1` still do. One
   round trip per (object, role) at bootstrap, not per question. When the
   connection cannot act as the role -- not a superuser or member on
   PostgreSQL, not authorised to proxy on Oracle -- the role is *kept* and the
   report names it and the statement that would allow it, because "could not
   check" must never read as "checked and denied".
3. **Name the views that bypass the policy** (PostgreSQL). A view over a
   policied table that was not created `WITH (security_invoker = true)` is
   flagged and listed in the report; `hide_bypassing_views=True` removes it
   from the catalogue. It is not removed by default, because a predicate view is
   also the ordinary way to expose a subset on purpose -- the report tells
   you which it is.

```python
from schemagate.grants import restrict_from_grants
from schemagate.rls import restrict_from_policies
restrict_from_grants(cat, engine)
print(restrict_from_policies(cat, engine, report=True))
```

Oracle gets steps 1 and 2; step 3 has no Oracle case, because a predicate
view there carries the policy through (measured above). The turn from "the
caller may read this table" into "the caller can get rows out of this table"
is complete on both, given a connection that may act as the role, and the
report says exactly which roles it could not act as.

## Reproducing it

**PostgreSQL**, as a superuser, then connect as each role and compare:

```sql
CREATE TABLE employee_salary (id int primary key, name text, dept text, salary numeric);
INSERT INTO employee_salary VALUES (1,'Ann','SALES',91000),(2,'Bob','SALES',87000),
                                   (3,'Cy','ENG',120000),(4,'Di','HR',70000);
ALTER TABLE employee_salary ENABLE ROW LEVEL SECURITY;
CREATE ROLE sgrls_r1 LOGIN PASSWORD '...';  CREATE ROLE sgrls_r2 LOGIN PASSWORD '...';
CREATE POLICY p_r1 ON employee_salary FOR SELECT TO sgrls_r1 USING (dept = 'SALES');
CREATE POLICY p_r2 ON employee_salary FOR SELECT TO sgrls_r2 USING (false);
CREATE VIEW v_sales_salary AS SELECT * FROM employee_salary WHERE dept = 'SALES';
CREATE VIEW v_sales_salary_si WITH (security_invoker = true)
    AS SELECT * FROM employee_salary WHERE dept = 'SALES';
GRANT USAGE ON SCHEMA public TO sgrls_r1, sgrls_r2;
GRANT SELECT ON employee_salary, v_sales_salary, v_sales_salary_si TO sgrls_r1, sgrls_r2;
```

Then `SELECT COUNT(*)` from the table and from each view as `sgrls_r2`, and
build a catalogue as the superuser with `restrict_from_grants` and select for
`Principal("db:sgrls_r2", roles={"sgrls_r2"})`.

**Oracle.** To probe, the application user also needs `ALTER USER <reader>
GRANT CONNECT THROUGH <app>` for each reader. The fixture is four statements: a table with rows in two departments, a
function returning a different predicate per `SYS_CONTEXT('USERENV',
'SESSION_USER')`, `DBMS_RLS.ADD_POLICY` over `SELECT`, and two users with
`GRANT SELECT`. Then build a catalogue as each user and compare
`cat.select(...)` against `SELECT COUNT(*)` as that same user.

The interesting reader is the one whose predicate is `1 = 0`: it holds every
permission the data dictionary records, and can read nothing.
