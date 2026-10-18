# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Per-caller access control for jev4pg (github.com/Sheltercosmo/jev4pg).

jev4pg plans and validates SQL from one catalogue per tenant: every user of a tenant sees every
table and column registered for it, and its semantic operators send rows to its model provider.
schemagate already knows, per caller, which tables and columns may be read. This adapter puts that
knowledge in front of jev4pg's catalogue, so a caller's datasets -- and everything jev4pg derives
from them -- shrink to what that caller may read:

    from schemagate import Catalog, Principal
    from schemagate.integrations.jev4pg import ScopedCatalog, acting_as

    sg = Catalog().bootstrap(url)                    # with restrict(...) / --restrict-from-grants
    catalog = ScopedCatalog(jev4pg_catalog, sg)      # hand this to jev4pg wherever it takes a Catalog
    with acting_as(Principal("okta:jdoe", roles=frozenset({"sales"}))):
        ...                                          # jev4pg planning, validation, execution

One choke point covers jev4pg's whole pipeline, because its planner context (`model_catalog`), its
SQL validator (`SQLService.prepare`, which already refuses unknown datasets and columns) and its
semantic operators all read datasets through `Catalog.list`. Nothing here imports jev4pg: the
wrapper is duck-typed against its catalogue (`list`, `get`, `model_catalog`).

Fails closed. A jev4pg dataset that does not match an object in the schemagate catalogue, or that
the caller may not read, is dropped. Without `acting_as`, every restricted object is hidden, as for
an anonymous caller.
"""
from __future__ import annotations

import contextvars
import copy
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

_CALLER: contextvars.ContextVar = contextvars.ContextVar("schemagate_jev4pg_caller", default=None)


@contextmanager
def acting_as(principal):
    """Scope jev4pg's catalogue to ``principal`` for the duration of the block (thread- and task-safe)."""
    token = _CALLER.set(principal)
    try:
        yield principal
    finally:
        _CALLER.reset(token)


def _visible_columns(sg_catalog, principal) -> Dict[str, Optional[set]]:
    """{'schema.table' and 'table' -> set of visible column names (lower case)} for this caller."""
    out: Dict[str, Optional[set]] = {}
    for doc in sg_catalog.objects():
        if not sg_catalog._visible(doc, principal):
            continue
        cols = {c.name.lower() for c in doc.visible_columns(principal)}
        out[doc.qname.lower()] = cols
        out.setdefault((doc.name or "").lower(), cols)
    return out


def _match(dataset, visible) -> Optional[set]:
    schema, table = (dataset.get("schema_name") or ""), (dataset.get("table_name") or "")
    for key in (f"{schema}.{table}".lower(), table.lower()):
        if key and key in visible:
            return visible[key]
    return None


def scope_datasets(datasets: List[Dict[str, Any]], sg_catalog, principal) -> List[Dict[str, Any]]:
    """jev4pg dataset records reduced to what ``principal`` may read. Inputs are not modified."""
    visible = _visible_columns(sg_catalog, principal)
    keep: List[Dict[str, Any]] = []
    allowed_cols: Dict[Any, set] = {}
    for d in datasets:
        cols = _match(d, visible)
        if cols is None:
            continue                                   # hidden, or unknown to schemagate: fail closed
        d = copy.deepcopy(d)
        d["columns"] = [c for c in d.get("columns", []) if str(c.get("name", "")).lower() in cols]
        if not d["columns"]:
            continue
        allowed_cols[d.get("id")] = {str(c["name"]).lower() for c in d["columns"]}
        keep.append(d)
    ids = set(allowed_cols)

    def ok(cols, target_id=None, own_id=None):
        names = [str(c).lower() for c in (cols if isinstance(cols, list) else [cols])]
        pool = allowed_cols.get(target_id if target_id is not None else own_id, set())
        return all(n in pool for n in names)

    for d in keep:
        own = d.get("id")
        binding = d.get("source_binding")
        if isinstance(binding, dict):
            # the physical column list would otherwise name withheld columns in the planner context
            if isinstance(binding.get("columns"), list):
                binding["columns"] = [c for c in binding["columns"]
                                      if str(c.get("name", "")).lower() in allowed_cols[own]]
            if isinstance(binding.get("foreign_keys"), list):
                binding["foreign_keys"] = [fk for fk in binding["foreign_keys"]
                                           if ok(fk.get("source_columns", []), own_id=own)]
        if isinstance(d.get("source_relationships"), list):
            d["source_relationships"] = [
                r for r in d["source_relationships"]
                if r.get("target_id") in ids and ok(r.get("source_columns", []), own_id=own)
                and ok(r.get("target_columns", []), target_id=r.get("target_id"))]
        if isinstance(d.get("links"), list):
            d["links"] = [
                lk for lk in d["links"]
                if lk.get("target_id") in ids and ok(lk.get("source_column"), own_id=own)
                and ok(lk.get("target_column"), target_id=lk.get("target_id"))]
    return keep


class ScopedCatalog:
    """A jev4pg Catalog whose datasets are scoped to the caller set with `acting_as`."""

    def __init__(self, base, sg_catalog):
        self._base, self._sg = base, sg_catalog

    def __getattr__(self, name):                      # db, ledger, attach, table, ... unchanged
        return getattr(self._base, name)

    def list(self, tenant, *, connection=None):
        return scope_datasets(self._base.list(tenant, connection=connection), self._sg, _CALLER.get())

    def get(self, tenant, identity, *, connection=None):
        matches = [d for d in self.list(tenant, connection=connection) if identity in (d.get("id"), d.get("name"))]
        if len(matches) != 1:
            raise ValueError("Unknown or ambiguous dataset in this tenant")   # same words as jev4pg
        return matches[0]

    def model_catalog(self, tenant, *args, **kwargs):
        # jev4pg's own implementation, run with this wrapper as `self`, so it reads the scoped list;
        # then drop feature columns derived from a column this caller may not read.
        result = type(self._base).model_catalog(self, tenant, *args, **kwargs)
        visible = {d.get("id"): {str(c["name"]).lower() for c in d["columns"] if "source_column" not in c}
                   for d in result}
        for d in result:
            d["columns"] = [c for c in d["columns"]
                            if "source_column" not in c or str(c["source_column"]).lower() in visible[d.get("id")]]
        return result
