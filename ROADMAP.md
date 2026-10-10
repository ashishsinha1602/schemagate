# Roadmap

What schemagate intends to do over the next year (to October 2027), and what it
will not do. It changes by pull request like any other file; issues are the
place to argue for something.

## Next

- **Fail closed when permissions drift.** Stamp each catalogue with the time
  its grants were read, re-read them per session, and refuse to answer past a
  configurable age instead of answering from a stale copy.
- **Row-level policies on more databases.** Probe policies as the caller on
  SQL Server and MySQL, as is done today for PostgreSQL RLS and Oracle VPD.
- **Better retrieval for vague questions.** Query expansion from the
  organisation's vocabulary (`ontology.py`), measured on the published
  benchmarks before it ships.
- **Authentication for the HTTP transport.** A built-in way to verify the
  caller (a token the server checks), so the HTTP MCP server does not depend
  only on a gateway in front of it.

## Later

- More stores for the catalogue beyond in-memory and Oracle.
- A second maintainer (see [GOVERNANCE.md](GOVERNANCE.md)).

## Not planned

- **Writing to databases.** `run_query` stays read-only.
- **A hosted service.** schemagate is a library and a server you run yourself.
- **Replacing database permissions.** It narrows what a model sees; the
  database stays the final control.
- **Its own cryptography.** It will keep using pyca/cryptography.
