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

Only the latest release on PyPI receives fixes. There is no long-term branch,
and from 1.0 there does not need to be one: the public API does not break
within a major version, so moving to the newest 1.x is an upgrade rather than
a migration.

## Verifying what you installed

Every release on PyPI carries a [PEP 740](https://peps.python.org/pep-0740/)
attestation naming the workflow, repository and commit that built it:

    gh attestation verify schemagate-<version>-py3-none-any.whl --repo ashishsinha1602/schemagate

The OCI stack zip attached to each GitHub release is signed with Sigstore,
keylessly, and the signature ships as one bundle beside it --
`schemagate-oci-stack.zip.sigstore.json`, holding the signature, the
certificate and the transparency-log entry together:

    cosign verify-blob --bundle schemagate-oci-stack.zip.sigstore.json \
      --certificate-identity-regexp 'github.com/ashishsinha1602/schemagate' \
      --certificate-oidc-issuer https://token.actions.githubusercontent.com \
      schemagate-oci-stack.zip

Signing starts at v0.1.58. Earlier releases carry the zip with no bundle, so
there is nothing to verify against -- not a failed check, an absent one.

## What schemagate does and does not protect

- It filters *schema metadata* by identity before retrieval. It never sees or
  filters row data; row-level security in the database is still yours to
  configure.
- The AI describer sends only object and column names, types and comments to
  the provider you configure. It has no field a row could travel in.
- The MCP server redacts database passwords from every output it produces.
- Anonymous callers (no principal) see only objects with no role requirement.
