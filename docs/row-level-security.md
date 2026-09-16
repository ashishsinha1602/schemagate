# Row-level security, and what schemagate does not yet see

schemagate's claim is that the model is never shown a table the caller may not
read. `restrict_from_grants()` makes that true by asking the database who may
read what — it reads `ALL_TAB_PRIVS` on Oracle, the equivalent elsewhere, and
marks each object with the roles that hold `SELECT` on it.

That is the right question for table-level permissions. It is the wrong
question for Oracle's Virtual Private Database, which is how a great many
Oracle shops actually enforce access: the `GRANT` stays, and a policy function
silently appends a predicate to every query, so two users running identical
SQL get different rows.

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
keep being used. Where VPD is in play, add the restriction yourself, because
you know the policy and the catalogue does not:

```python
cat.restrict("employee_salary", ["payroll"])       # roles that VPD actually admits
```

or leave the object out of the catalogue entirely with `exclude=` at bootstrap
if no caller of this application should see it.

## The fix, and why it is reachable

The last row of that table is the useful one: **the reader can see the policy**.
`ALL_POLICIES` is readable by a user who holds the grant, so a catalogue built
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

The fixture is four statements: a table with rows in two departments, a
function returning a different predicate per `SYS_CONTEXT('USERENV',
'SESSION_USER')`, `DBMS_RLS.ADD_POLICY` over `SELECT`, and two users with
`GRANT SELECT`. Then build a catalogue as each user and compare
`cat.select(...)` against `SELECT COUNT(*)` as that same user.

The interesting reader is the one whose predicate is `1 = 0`: it holds every
permission the data dictionary records, and can read nothing.
