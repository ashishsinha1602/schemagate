# Business rules

Some knowledge isn't anywhere in the database: "our fiscal year starts
1 July", "always leave out the test tenant", "churned means no order in 90
days". A model that isn't told writes SQL that runs and answers the wrong
question. Business rules are how you tell it.

## Writing them

Rules live in a Markdown file. Each `##` heading starts one rule:

```markdown
## Fiscal year
Our fiscal year starts 1 July.

## Test accounts
tables: contacts, deals
Always exclude tenant_id 6, the internal test tenant.

## Bonus formula
roles: payroll
bonus = base_salary * rating_multiplier, paid in March.
```

- `tables:` ties a rule to objects. The rule is sent only when one of those
  objects is in the selection.
- `roles:` keeps a rule from callers who hold none of those roles, the same
  way a restricted table is kept from them.
- A rule with no `tables:` line is sent when the question shares a word with
  it.

A prompt carries at most 5 rules. They go above the DDL, under
`-- Business rules to follow:`.

## Two ways in

**A file.** Point the catalog config at it. A relative path is read from the
config file's folder:

```json
{"rules": "rules.md"}
```

**Studio.** `schemagate studio` has a *Business rules* box in the side rail.
Edit the rules and save them. **Test** shows which rules a question would
pick up. Studio saves rules for each database, under
`~/.schemagate/rules/`. If you haven't saved any, the rules from the config
file are used.

## What it changes

With no rules, nothing changes, and the prompt is byte-for-byte the same as
before. That is pinned by a test.

Results below use Gemini 2.5 Flash. Each question's rules came from the
other questions' BIRD evidence (leave-one-out), so no question got its own
answer as a rule.

| Setup | Without rules | With rules |
|---|---|---|
| SQLite, 11 BIRD databases | 36.8 | 48.6 |
| Postgres, one 75-table schema | 22.3 | 26.5 |
| Oracle Free | 32.7 | 33.2 |
| Spider 2.0-lite SQLite, 135 tasks (task docs pasted whole vs. split into rules) | 36.3 | 45.2 |

A rule that matches on words alone can mislead an unrelated question. If a
rule only applies to certain tables, give it a `tables:` line.
