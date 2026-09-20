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

## What to do about it today

`restrict_from_grants()` is still right for table-level permissions and should
keep being used. Where RLS or VPD is in play, add the restriction yourself,
because you know the policy and the catalogue does not:

```python
cat.restrict("employee_salary", ["payroll"])       # roles that VPD actually admits
```

or leave the object out of the catalogue entirely with `exclude=` at bootstrap
if no caller of this application should see it. On PostgreSQL, also recreate
any predicate view over a policied table `WITH (security_invoker = true)`, or
revoke it from the roles the policy binds -- that one is a leak, not a
usability problem, and it is fixed in the database, not in a prompt.

## The fix, and why it is reachable

The last row of each table is the useful one: **the reader can see the policy**.
`pg_policies` and `ALL_POLICIES` are readable by a user who holds the grant, so a catalogue built
as that user can find out that a policy exists on an object, which function
implements it, and which statement types it covers.

That is enough to do better than today in two steps, neither of which requires
privileges the caller does not already have:

1. **Flag it.** An object under a `SELECT` policy is marked as row-restricted,
   and the prompt fragment says so, so the model knows the table it is being
   shown is filtered and does not report an empty result as an absence of
   facts.
2. **Test it.** `SELECT 1 FROM <object> WHERE ROWNUM = 1` as the calling user
   answers the only question that matters — does this caller get anything at
   all — and an object that yields nothing can be withheld exactly as a
   missing grant is today.

Step 2 costs one round trip per policied object at bootstrap, not per question,
and it turns the claim from "the caller may read this table" into "the caller
can get rows out of this table", which is what a person asking a question
actually means.

Not implemented yet. Filed here rather than in a commit message because the
measurement is the part worth keeping: the mechanism most enterprise Oracle
deployments use is invisible to the mechanism this library reads.

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

**Oracle.** The fixture is four statements: a table with rows in two departments, a
function returning a different predicate per `SYS_CONTEXT('USERENV',
'SESSION_USER')`, `DBMS_RLS.ADD_POLICY` over `SELECT`, and two users with
`GRANT SELECT`. Then build a catalogue as each user and compare
`cat.select(...)` against `SELECT COUNT(*)` as that same user.

The interesting reader is the one whose predicate is `1 = 0`: it holds every
permission the data dictionary records, and can read nothing.
