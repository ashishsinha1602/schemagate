# Governance

## How decisions are made

schemagate is maintained by one person, Ashish Sinha
([@ashishsinha1602](https://github.com/ashishsinha1602)), who makes the final
call on what is merged and released. Decisions are made in the open: proposals
and disagreements go in GitHub issues or pull requests, and the reasoning for
a change is written in its pull request and in [CHANGELOG.md](CHANGELOG.md).
Anything that changes what a caller may see is treated as a security decision
and follows [SECURITY.md](SECURITY.md).

When a second maintainer joins, decisions will need the agreement of both, and
this file will say so.

## Roles

| Role | Who | Responsibilities |
|---|---|---|
| **Maintainer** | @ashishsinha1602 | Reviews and merges pull requests; cuts releases (tag, PyPI, MCP Registry, OCI stack); answers issues; handles vulnerability reports within the times in SECURITY.md; keeps CI, branch protection and dependency updates working; keeps the docs in step with each release. |
| **Contributor** | anyone | Opens issues and pull requests following [CONTRIBUTING.md](CONTRIBUTING.md): one change per PR, tests included, CHANGELOG line, `Signed-off-by` (DCO). |
| **Security reporter** | anyone | Reports entitlement bypasses privately through GitHub security advisories, never in a public issue. Credited in the advisory unless they ask not to be. |

## Continuity

The code, issues, releases and CI live on GitHub, and everything needed to
build and publish a release is in this repository: releases are built and
published by GitHub Actions through PyPI trusted publishing, so no personal
token is required to ship one. The licence (Apache-2.0) lets anyone fork and
continue the project.

The project currently has a single maintainer, so its "bus factor" is one. To
remove that, the plan is to add a second maintainer with admin rights on the
GitHub repository and owner rights on the PyPI project. Until then, if the
maintainer is unreachable for 60 days, a fork is the supported way to
continue.

## Changes to this document

Changes to governance are made by pull request to this file, like any other change.
