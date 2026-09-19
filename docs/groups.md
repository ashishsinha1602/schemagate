# Where a caller's roles come from

`restrict_from_grants()` answers half of the access question — which roles
may see an object — by reading the database's own grants, because a
hand-copied ACL drifts. This page is the other half: **which roles does the
caller hold**, read from wherever the organisation already keeps that — a
directory, a membership table, an HTTP endpoint, the database's role graph,
or a file.

Until this existed the caller supplied its own roles. That is fine for a
desktop client talking to its own database and useless for a hosted server,
where "the client says it holds `payroll`" is not an access check. With a
`groups` block configured, **the roles a client sends are ignored** and the
directory's answer is used instead.

## The block

Add it to the same JSON file `--config` / `SCHEMAGATE_CATALOG_CONFIG` already
reads:

```json
{
  "restrict": {"hr_compensation": ["payroll"]},
  "groups": {
    "ttl": 300,
    "map": {"5f1c3b2e-…": "payroll", "Payroll Team": "payroll"},
    "passthrough": true,
    "sources": [
      {"type": "entra", "tenant": "contoso.onmicrosoft.com",
       "client_id": "…", "client_secret": "${ENTRA_CLIENT_SECRET}",
       "security_only": true},
      {"type": "native"},
      {"type": "sql", "for": ["okta"],
       "sql": "SELECT role FROM app_membership WHERE subject = :subject"},
      {"type": "http", "for": ["okta"],
       "url": "https://idp.example.com/users/{id}/groups",
       "headers": {"Authorization": "Bearer ${GROUPS_API_TOKEN}"}},
      {"type": "static", "members": {"okta:jdoe": ["finance"]}}
    ]
  }
}
```

`${NAME}` is replaced from the environment when the file is read, so the
file holds no secret. A reference to an unset variable is an error at
startup, not an empty string: the server refuses to start rather than answer
anyone with the client's own roles.

| key | meaning | default |
|---|---|---|
| `sources` | the places to ask, in order; results are a union | required |
| `for` (per source) | subject namespaces this source answers for — `entra:`, `db:`, `okta:` … | see each source |
| `map` | group id or name → role name | `{}` |
| `passthrough` | keep unmapped groups as roles, by name | `true` |
| `ttl` | seconds an answer is cached; a revoked membership is honoured within this | `300` |
| `maxsize` | subjects held in the cache | `10000` |

A single source can be written unwrapped: `"groups": {"type": "native"}`.

## Sources

**`entra` — Microsoft Entra ID (Azure AD), through Microsoft Graph.**
Client-credentials flow, then `POST /users/{id}/getMemberGroups`, which is
transitive: a user in *Payroll Team*, itself nested in *Finance*, holds both.
Groups come back as object ids **and** display names, so `map` may key on
either and a `restrict` may name the group as the directory shows it.
`security_only: true` drops Microsoft 365 groups and distribution lists.
Subjects are `entra:<object id>` or `entra:<upn>` (`entra:jdoe@contoso.com`).
Serves `entra`, `aad`, `azuread` by default.

The app registration needs application permissions **`User.Read.All`** and
**`GroupMember.Read.All`** with admin consent. A missing permission surfaces
as `HTTP 403 … Authorization_RequestDenied … Insufficient privileges`, which
is passed through in the error because it is the one line the operator
needs; the token and the secret never are.

**`native` — the database's own role graph, for `db:<user>` subjects.**
Reads the same views `restrict_from_grants` reads (`pg_auth_members`,
`DBA_ROLE_PRIVS`, `mysql.role_edges`) and walks them upward from the user,
transitively and cycle-safe. So a user who holds `SELECT` through
`GRANT reporting TO analysts; GRANT analysts TO jdoe` resolves to both roles,
and a catalog restricted from the same grants lets exactly that user through.
Uses the catalog's own connection unless `url` is given. Names are matched
case-insensitively (Oracle upper-cases, PostgreSQL folds down); MySQL is
matched by user name, host dropped, as `role_edges` records it.

On Oracle the full graph is `DBA_ROLE_PRIVS`, which needs a privilege an
application user rarely has; the fallback `USER_ROLE_PRIVS` sees only the
connected user's *direct* roles. Measured on Autonomous Database 26ai:
through ADMIN, `db:SGBENCH` → `{SG_GRP_ANALYSTS, SG_GRP_REPORTING}`; through
SGBENCH's own connection, `{SG_GRP_ANALYSTS}` only. The fallback
**under-grants, never over** — but if nested roles matter, resolve through a
connection that can read `DBA_ROLE_PRIVS`.

**`sql` — a membership table you already have.** One bound parameter,
`:subject`, holding the local part of the subject (`bind: "local"`, default)
or the whole namespaced subject (`bind: "subject"`). The first column of each
row is a group. Bound, never formatted: a subject is caller-controlled text.

**`http` — any endpoint that returns groups as JSON.** `{id}` in the URL is
the URL-quoted local part, `{subject}` the whole subject. The reply may be a
list of strings, a list of objects carrying `id` / `displayName` / `name`, or
an object holding one of those under `path` (default: the first of `groups`,
`roles`, `value`). Headers may carry `${TOKEN}`.

**`static` — a mapping in the file.** `{"okta:jdoe": ["finance"]}`. The
forty-table case, and the fixture for tests.

## What the server does with it

- `select_schema`, `list_objects`, `describe_object`, `run_query` and
  `answer` all build the caller from the resolver. Roles in the request are
  dropped, not merged — a merge would let anyone add `payroll` to whatever
  the directory said.
- A source that cannot answer — token expired, endpoint down, user not found
  by Graph — returns `{"error": …}` to that caller. **Not** an anonymous
  selection: "no groups" and "could not ask" are different answers and only
  one is safe to act on. The server keeps serving everyone else, and the
  failure is not cached, so the next call asks again.
- An anonymous caller (no `principal`) never consults the directory and sees
  only unrestricted objects, as before.
- `refresh_catalog` also drops the membership cache, so "re-reflect" means
  "re-ask the directory" too.
- `health` reports `groups`: source kinds, mapped count, cache size,
  hits/misses/errors. No group names, no subjects.

## From code

```python
from schemagate import Catalog, Groups
from schemagate.groups import EntraGroups, NativeRoles

cat = Catalog().bootstrap(engine)
groups = Groups([EntraGroups(tenant, client_id, secret, security_only=True),
                 NativeRoles(engine)],
                map={"Payroll Team": "payroll"})

who = groups.principal("entra:jdoe@contoso.com")   # roles from the directory
cat.select("what do we pay our doctors", principal=who)
```

`Groups.resolve(principal)` does the same for a `Principal` already built,
discarding whatever roles it carried. `Groups.forget(subject)` honours a
revocation now rather than within `ttl`.

## From the command line

```bash
schemagate select "salary by employee" --url ... --config catalog.json --principal entra:jdoe@contoso.com
```

With a `groups` block in the config and no `--role`, the principal's roles
come from the directory. An explicit `--role` still wins on the command
line: the operator typing it is the one doing the checking.

## What it is not

It is a scoping mechanism, not authentication. The server still trusts the
*subject* it is handed — this page makes the *roles* come from somewhere the
client does not control. Run the server over stdio, or over HTTP behind
something that authenticates the user and sets `principal` for them; with
that in place, and a `groups` block, the client controls nothing that
matters.

It does not see row-level policies either; see
[row-level-security.md](row-level-security.md).

## How it was tested

- `tests/test_groups.py` (38): every source against fakes — scripted Graph
  replies for the token, `getMemberGroups` and `getByIds` calls; a sqlite
  membership table; a fake role graph with a cycle; `${ENV}` expansion and
  the unset-variable refusal; the cache's ttl, bound and `forget`.
- `tests/test_groups_server.py` (12): every identity tool consults the
  directory and ignores the client's roles; every tool fails closed when the
  directory is down while the anonymous path keeps serving; sixteen threads
  hammering one resolver; a real MCP client over stdio with a `groups` block
  in `SCHEMAGATE_CATALOG_CONFIG`; a bad block stopping the server.
- `tests/test_groups_live.py` (5): `native` on live PostgreSQL 16 and MySQL
  8.4 — two levels of role inheritance, the grants-restricted catalog and the
  resolver agreeing with `has_table_privilege` / an actual `SELECT`. The same
  check on Oracle Autonomous Database 26ai ran as a script, as ADMIN and as
  the application user (the fallback case above).
- `tests/test_groups_live_server.py` (2): groups **defined in a table** on
  the live database, with the real `python -m schemagate.mcp_server` started
  against that database and a real MCP client asking it. No demo catalog. A
  client claiming `payroll` does not see the payroll table; the user the
  table puts in *Payroll Team* does, and `run_query` returns them real rows;
  a user the table has never heard of gets no roles, not an error.
  PostgreSQL 16 and MySQL 8.4 in CI on every push; Oracle Autonomous
  Database 26ai by script, wallet in `SCHEMAGATE_CONNECT_ARGS`.
- Entra itself was exercised against scripted Graph responses only; the
  request shapes follow the Graph reference for `getMemberGroups` and
  `directoryObjects/getByIds`. A live tenant run is owed before the source is
  called certified.
