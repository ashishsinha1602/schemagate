# Security: what to expect, and why it holds

This page is schemagate's security requirements and its assurance case: what
you can and cannot rely on, the threats it was designed against, and the
evidence for each claim. To report a problem, see [SECURITY.md](../SECURITY.md).

## What you can rely on

1. **A caller is never shown an object their roles may not read.** Tables,
   views and columns outside the caller's visibility are absent from every
   selection, every rendered prompt, foreign-key expansion, the MCP tools and
   the Studio. They are not masked or renamed; they are not there.
2. **SQL that names a hidden object does not run.** The MCP server's
   `run_query` parses the statement and checks every table and column against
   the same visibility before the database sees it, including quoted,
   bracketed and schema-qualified names, comma joins and `SELECT *`.
3. **SQL that writes does not run.** `run_query` accepts one read statement.
   Writes, DDL, and a second statement hidden in a comment or a string literal
   are refused (`answer.check_read_only`). Results are capped (`max_rows`).
4. **Visibility can come from the database itself.** With
   `--restrict-from-grants` (or `SCHEMAGATE_RESTRICT_FROM_GRANTS=1` for the MCP
   server) the rules are read from the database's GRANTs, so there is no second
   copy to fall out of date. How long a change takes to reach the server is
   bounded and stated below, under "How fresh are the permissions". Row-level policies are probed
   as the caller, and views that would bypass a policy are flagged
   ([row-level-security.md](row-level-security.md)).
5. **Decisions can be proven afterwards.** With the audit log on, each record
   is hash-chained to the one before it and, with the `pq` extra, signed with
   ML-DSA-65 (FIPS 204). `schemagate audit verify` names any record that was
   edited, removed or reordered.
6. **Releases can be verified.** Every PyPI release carries a PEP 740
   attestation naming the workflow and commit that built it, and the OCI stack
   zip is signed with Sigstore. [SECURITY.md](../SECURITY.md) shows the commands.

## What you cannot rely on

- **schemagate does not authenticate the caller.** `principal` and `roles`
  are what the embedding application passes in. Over stdio the only caller is
  the local client. Over HTTP, put it behind something that authenticates the
  user and sets the principal; do not expose it on a network you do not
  control and rely on `principal` to keep people apart.
- **It does not replace database permissions.** Run the queries under a
  database account that can read only what the caller may read. schemagate
  narrows what the model sees and runs; the database is the final control.
- **It does not hide data inside allowed objects.** If a caller may read a
  table, they may read every row the database returns to them; row-level
  security is the database's job.
- **The public demo endpoint** serves a sample schema with no real data and no
  authentication. It is for trying the tools, not for real databases.

## How fresh are the permissions

Two separate claims, because the two paths refresh differently:

- **Restrictions in schemagate's own role lists** (the config file, or
  `Catalog.restrict` in Python) are evaluated on every call against the
  caller's current roles. Changing them in a running Python process takes
  effect on the next call. The MCP server reads its config file when it builds
  the catalogue, so for the server a change lands on the next re-read.
- **Permissions read from the database** (`SCHEMAGATE_RESTRICT_FROM_GRANTS`)
  are a snapshot taken when the catalogue is built. Without
  `SCHEMAGATE_CATALOG_MAX_AGE` the snapshot lasts until `refresh_catalog`.
  With it, a GRANT or REVOKE reaches the server **within** that many seconds.
  That is a bounded window, not "immediately".

Past the age, a failed re-read makes every scoping tool refuse ("permissions
are stale") rather than serve the last snapshot, and the refusal names no host,
user or database error; the operator finds those in `health` and the server
log. A failed re-read is retried at most every 5 seconds.

Caller roles from a `groups` resolver are cached for its `ttl` (300 seconds by
default) and a resolver that fails refuses the call; that bound is separate
from the catalogue's.

## Threat model

| Threat | Mitigation | Evidence |
|---|---|---|
| The model is told about a restricted table and writes SQL against it | Restricted objects are removed before ranking and rendering, for every interface | `tests/test_identity.py`, `tests/test_isolation.py`, `tests/test_caller_boundaries.py` |
| The model names a hidden table anyway (hallucinated, memorised, quoted, bracketed, comma-joined) | `run_query` resolves and re-checks every name before running | `tests/test_mcp_server.py` and the run_query fix in CHANGELOG 1.1.1 |
| `SELECT *` pulls a hidden column | `*` is expanded against visibility and refused if it would include one | `tests/test_mcp_server.py` |
| The model writes or chains statements | single-read check that strips comments and literals first | `tests/test_answer.py` |
| A Postgres view runs with its owner's rights and bypasses row-level security | policied tables are probed as the caller; non-`security_invoker` views over them are flagged or hidden | `tests/test_rls.py`, live job `postgres.yml` |
| The rules drift from the database | `--restrict-from-grants` reads GRANTs directly; `SCHEMAGATE_CATALOG_MAX_AGE` bounds how old they may be and refuses past it if they cannot be re-read | `tests/test_grants.py`, `tests/test_catalog_max_age.py`, `tests/freshness_e2e.py` (real GRANT/REVOKE on PostgreSQL, MySQL, Oracle) |
| Someone edits the audit trail after the fact | hash chain plus ML-DSA-65 signatures; `audit verify` | `tests/test_pq_audit.py` |
| A tampered release | PEP 740 attestations, Sigstore-signed stack zip, pinned Actions | `.github/workflows/publish.yml` |
| Injection through the build pipeline | no `pull_request_target`; least-privilege tokens; CodeQL on every push | OpenSSF Scorecard: Dangerous-Workflow and Token-Permissions 10/10 |

## Secure design principles applied

- **Fail closed.** A restricted object asked for with no principal is hidden,
  not shown: an anonymous caller never falls through to everything
  (`models.allowed`). A name `run_query` cannot resolve is refused, not passed
  through. (An object with *no* restriction is visible to everyone; restrict
  it, or use `--restrict-from-grants`, to change that.)
- **Allow-list, not deny-list.** The prompt is built from what the caller may
  see, rather than by removing what they may not.
- **Complete mediation.** Visibility is checked at selection *and* at
  execution, so the second check does not trust the first.
- **One source of truth.** Every interface calls the same `Catalog`; none
  carries its own copy of the rules.
- **Least privilege.** Read-only queries, capped results, CI tokens scoped per
  job, and the recommendation that the database account be scoped to the caller.

## Cryptography

schemagate does not implement cryptography. The audit log uses ML-DSA-65 and
SHA-256 from [pyca/cryptography](https://cryptography.io/); keys are generated
by that library from the operating system's random source and kept in a
separate key file, optionally encrypted with a passphrase taken from an
environment variable. TLS to databases is provided by each database driver
with its default certificate verification.
