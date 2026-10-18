# Per-user access control for jev4pg

[jev4pg](https://github.com/Sheltercosmo/jev4pg) plans, reviews and runs SQL over PostgreSQL with
typed judgments and semantic operators. It scopes data per *tenant*: every user of a tenant sees
every table and column registered for it, and its semantic operators send whole rows to its model
provider. schemagate knows, per *caller*, which tables and columns may be read, from roles or from
the database's own GRANTs. `schemagate.integrations.jev4pg` puts that in front of jev4pg's catalogue.

```python
from schemagate import Catalog, Principal
from schemagate.integrations.jev4pg import ScopedCatalog, acting_as

sg = Catalog().bootstrap("postgresql://...")        # with restrict(...) or --restrict-from-grants rules
catalog = ScopedCatalog(jev4pg_catalog, sg)         # pass this wherever jev4pg takes its Catalog

with acting_as(Principal("okta:jdoe", roles=frozenset({"sales"}))):
    ...                                             # plan, validate, execute as this caller
```

## Why one wrapper covers the whole pipeline

jev4pg reads datasets through `Catalog.list` for its planner context (`model_catalog`), its SQL
validator (`SQLService.prepare`, which already refuses an unknown dataset or column) and the columns
its semantic operators load. `ScopedCatalog` scopes that list, so for each caller:

- datasets they may not read disappear, and so does every relationship and link pointing to one;
- columns they may not read are removed from `columns`, from the physical column list and foreign
  keys in `source_binding`, and from joins in `source_relationships` and `links`;
- feature columns derived from a withheld column are dropped from `model_catalog`;
- jev4pg's own validator then refuses SQL naming anything withheld, because it no longer exists in
  that caller's catalogue.

It fails closed: a jev4pg dataset that matches no object in the schemagate catalogue is dropped, and
with no `acting_as` block every restricted object is hidden, as for an anonymous caller.

## What has and has not been tested

`tests/test_jev4pg_adapter.py` runs the adapter against dataset records with jev4pg's exact shape
(from `sdd/generic/catalog.py` and `sdd/generic/source_catalog.py`, jev4pg 0.7.0), including a
relationship to a hidden table and a join on a hidden column. It has not been run against a live
jev4pg service: that needs jev4pg's JEV provider key and PostgreSQL 17. jev4pg is not on PyPI, so
nothing here imports it.

## Wiring it into the service

`sdd.generic.api.services(executor)` builds jev4pg's `Catalog`. Wrap it there, and set the caller per
request (for example in the dependency that reads the bearer token) with `acting_as`. Because
`Catalog.list` receives only the tenant, the caller travels in a context variable, which is safe across
threads and async tasks.
