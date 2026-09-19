# Security

schemagate decides which schema objects a caller may see. If you find a way for
a caller to see an object they are not entitled to — in the selected list, in
the rendered DDL, through foreign-key expansion, through the MCP server, or
through the Studio — that is a security bug, not a ranking bug.

Report it privately at
<https://github.com/ashishsinha1602/schemagate/security/advisories/new>
(the "Report a vulnerability" button on the Security tab). Please include a
minimal catalog (object names, roles, the principal) and the question that
reproduces it.

Do not open a public issue for entitlement bypasses.

## What happens next

- **Within 3 days**: acknowledgement, and a first assessment of whether it is
  an entitlement bypass.
- **Within 14 days**: a fix on `main` for a confirmed bypass, and a release.
  Ranking bugs are not on this clock; they go through the normal issue flow.
- **Disclosure**: the advisory is published when the fix is released, with
  credit to the reporter unless they ask otherwise. If a fix is going to take
  longer than 90 days, the reporter is told why and may disclose.

## Supported versions

Only the latest release on PyPI receives fixes. There is no long-term branch;
the release cadence is frequent enough that upgrading is the fix.

## Verifying what you installed

Every release on PyPI carries a [PEP 740](https://peps.python.org/pep-0740/)
attestation naming the workflow, repository and commit that built it:

    gh attestation verify schemagate-<version>-py3-none-any.whl --repo ashishsinha1602/schemagate

Release assets on GitHub are signed with Sigstore (`.sig` and `.pem` next to
each file).

## What schemagate does and does not protect

- It filters *schema metadata* by identity before retrieval. It never sees or
  filters row data; row-level security in the database is still yours to
  configure.
- The AI describer sends only object and column names, types and comments to
  the provider you configure. It has no field a row could travel in.
- The MCP server redacts database passwords from every output it produces.
- Anonymous callers (no principal) see only objects with no role requirement.
