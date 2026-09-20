# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Row-level policies: what the grant reader cannot see, read from the same
dictionary, and checked the only way that answers the real question.

`restrict_from_grants` answers "who holds SELECT". A row-level policy answers
a different question -- "which rows" -- and can answer "none" for a caller who
holds the grant. Measured on PostgreSQL 16 and Oracle 26ai
(docs/row-level-security.md): every dictionary answer is identical for a
reader who gets rows and one who gets none, so the catalogue put the table in
the prompt for both.

Three things, in the order that page proposed them:

1. **Flag it.** An object under a row-level policy is marked
   (``doc.extra["row_policy"] = True``) and its DDL carries a line saying rows
   are filtered per caller, so a model does not report an empty result as an
   absence of facts.
2. **Probe it** (PostgreSQL). For each role the grant reader left on a
   policied object, ``SET ROLE`` to it and ask for one row. A role that gets
   nothing loses the object, exactly as a missing grant would. The connection
   must be allowed to ``SET ROLE`` -- a superuser, or a member of the role;
   when it is not, the role is *kept* and the report says so, because "could
   not check" must never read as "checked and denied".
3. **Name the views that bypass the policy** (PostgreSQL). A view runs with
   its owner's privileges unless created ``WITH (security_invoker = true)``,
   so a plain predicate view over a policied table hands the caller the
   owner's rows. Those are flagged (``doc.extra["policy_bypass"] = True``) and
   reported; ``hide_bypassing_views=True`` removes them from the catalogue,
   the same thing ``exclude=`` at bootstrap does. (An empty role list would
   not do: no roles means everyone, by the one visibility rule in `models`.)

Oracle: policied objects are read from ``ALL_POLICIES`` and flagged. There is
no ``SET ROLE`` equivalent that changes what VPD sees, so nothing is probed
and the report says so.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from .models import POLICY_NOTE

__all__ = ["PolicyReport", "POLICY_READERS", "restrict_from_policies",
           "apply_policies", "CannotSetRole", "POLICY_NOTE"]

log = logging.getLogger("schemagate.rls")

#: dialect name -> callable(engine) -> set of (schema, name), both as the
#: dictionary spells them.
POLICY_READERS: Dict[str, Callable] = {}

Key = Tuple[Optional[str], str]


@dataclass
class PolicyReport:
    """What was read, what was applied, and what could not be."""
    dialect: str = ""
    #: qualified names of catalog objects under a row-level policy
    policied: List[str] = field(default_factory=list)
    #: views over a policied table that run with their owner's privileges
    bypassing_views: List[str] = field(default_factory=list)
    #: (object, role) pairs that were asked for one row
    probed: int = 0
    #: "object <- role": the role held the grant and got no rows
    withheld: List[str] = field(default_factory=list)
    #: roles the connection could not SET ROLE to; kept, not withheld
    unprobed_roles: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        out = (f"{self.dialect}: {len(self.policied)} policied object(s), "
               f"{len(self.bypassing_views)} policy-bypassing view(s), "
               f"{self.probed} probe(s), {len(self.withheld)} withheld")
        for w in self.withheld:
            out += f"\n  withheld: {w}"
        for v in self.bypassing_views:
            out += f"\n  bypasses the policy: {v}"
        if self.unprobed_roles:
            out += ("\n  not probed (connection cannot SET ROLE): "
                    + ", ".join(sorted(set(self.unprobed_roles))))
        for w in self.warnings:
            out += f"\n  warning: {w}"
        return out


class CannotSetRole(Exception):
    """The connection is neither a superuser nor a member of the role."""


# --------------------------------------------------------------------------
# PostgreSQL
# --------------------------------------------------------------------------

#: Tables and partitioned tables with RLS enabled. `relrowsecurity` is set by
#: ALTER TABLE ... ENABLE ROW LEVEL SECURITY whether or not any policy exists
#: yet; a table with it on and no policy admits nothing to non-owners, which
#: is exactly the case worth flagging.
_PG_POLICIED = """
    SELECT n.nspname, c.relname
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.relrowsecurity
       AND c.relkind IN ('r', 'p')
       AND n.nspname NOT IN ('pg_catalog', 'information_schema')
"""

#: Views whose rewrite rule depends on a policied table and that were not
#: created WITH (security_invoker = true). pg_depend rows for a view's query
#: hang off its pg_rewrite entry, which is why the join goes through it.
_PG_BYPASSING = """
    SELECT DISTINCT vn.nspname, v.relname
      FROM pg_depend d
      JOIN pg_rewrite rw ON rw.oid = d.objid
      JOIN pg_class v ON v.oid = rw.ev_class
      JOIN pg_namespace vn ON vn.oid = v.relnamespace
      JOIN pg_class t ON t.oid = d.refobjid
     WHERE d.classid = 'pg_rewrite'::regclass
       AND d.refclassid = 'pg_class'::regclass
       AND v.relkind = 'v'
       AND t.relrowsecurity
       AND t.relkind IN ('r', 'p')
       AND v.oid <> t.oid
       AND NOT EXISTS (
             SELECT 1 FROM unnest(COALESCE(v.reloptions, ARRAY[]::text[])) AS o
              WHERE lower(o) IN ('security_invoker=true', 'security_invoker=on'))
       AND vn.nspname NOT IN ('pg_catalog', 'information_schema')
"""


def _pg_policied(engine) -> Set[Key]:
    with engine.connect() as conn:
        return {(s, o) for s, o in conn.exec_driver_sql(_PG_POLICIED).fetchall()}


def _pg_bypassing_views(engine) -> Set[Key]:
    with engine.connect() as conn:
        return {(s, o) for s, o in conn.exec_driver_sql(_PG_BYPASSING).fetchall()}


def _pg_probe(engine, role: str, schema: Optional[str], name: str) -> bool:
    """Whether `role` gets at least one row from the object. Raises
    CannotSetRole when the connection may not become that role."""
    q = engine.dialect.identifier_preparer.quote
    target = f"{q(schema)}.{q(name)}" if schema else q(name)
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            try:
                conn.exec_driver_sql(f"SET ROLE {q(role)}")
            except Exception as e:                    # noqa: BLE001
                raise CannotSetRole(str(e)) from e
            row = conn.exec_driver_sql(f"SELECT 1 FROM {target} LIMIT 1").fetchone()
            return row is not None
        finally:
            # Nothing here should persist: not the role, not a lock, not a
            # transaction on a connection that goes back to the pool.
            try:
                tx.rollback()
            except Exception:                         # noqa: BLE001
                pass


# --------------------------------------------------------------------------
# Oracle
# --------------------------------------------------------------------------

#: Objects under an enabled VPD policy that covers SELECT. Readable by any
#: user who holds a grant on the object, which is the whole reason step 1 is
#: reachable without extra privileges.
_ORA_POLICIED = """
    SELECT object_owner, object_name
      FROM all_policies
     WHERE enable = 'YES' AND sel = 'YES'
"""


def _ora_policied(engine) -> Set[Key]:
    with engine.connect() as conn:
        return {(s, o) for s, o in conn.exec_driver_sql(_ORA_POLICIED).fetchall()}


POLICY_READERS["postgresql"] = _pg_policied
POLICY_READERS["oracle"] = _ora_policied

#: Only PostgreSQL can be asked "what does this role get" from one connection.
_PROBERS: Dict[str, Callable] = {"postgresql": _pg_probe}
_BYPASS_READERS: Dict[str, Callable] = {"postgresql": _pg_bypassing_views}


# --------------------------------------------------------------------------
# applying it
# --------------------------------------------------------------------------

def _fold(keys: Set[Key]) -> Set[Key]:
    return {(s.casefold() if s else None, o.casefold()) for s, o in keys}


def _match(doc, folded: Set[Key]) -> bool:
    key = (doc.schema.casefold() if doc.schema else None, doc.name.casefold())
    if key in folded:
        return True
    # unqualified reflection against a qualified dictionary, and vice versa
    return (None, key[1]) in folded or any(k[1] == key[1] and key[0] is None
                                            for k in folded)


def apply_policies(catalog, policied: Set[Key], bypassing: Set[Key], *,
                   probe: Optional[Callable[[str, Optional[str], str], bool]] = None,
                   hide_bypassing_views: bool = False,
                   report: Optional[PolicyReport] = None) -> PolicyReport:
    """The pure half: given what the dictionary said, mark and withhold.

    ``probe(role, schema, name) -> bool`` is called for every role the grant
    reader left on a policied object; it may raise CannotSetRole, after which
    that role is kept everywhere and named in the report. Split out from
    `restrict_from_policies` so the logic is testable without a server.
    """
    rep = report or PolicyReport()
    fp, fb = _fold(policied), _fold(bypassing)
    cannot: Set[str] = set()

    for key, doc in list(catalog._docs.items()):
        if _match(doc, fp):
            doc.extra["row_policy"] = True
            rep.policied.append(doc.qname)
            if probe is not None and doc.roles:
                kept: List[str] = []
                for role in doc.roles:
                    if role in cannot:
                        kept.append(role)
                        continue
                    try:
                        rep.probed += 1
                        got = probe(role, doc.schema, doc.name)
                    except CannotSetRole:
                        cannot.add(role)
                        kept.append(role)
                        continue
                    if got:
                        kept.append(role)
                    else:
                        rep.withheld.append(f"{doc.qname} <- {role}")
                doc.roles = kept
            elif probe is not None and doc.roles is None:
                rep.warnings.append(
                    f"{doc.qname} is under a row-level policy and readable by "
                    "PUBLIC; nothing was probed because there is no role to probe")
        if _match(doc, fb):
            doc.extra["policy_bypass"] = True
            rep.bypassing_views.append(doc.qname)
            if hide_bypassing_views:
                del catalog._docs[key]

    rep.unprobed_roles.extend(sorted(cannot))
    if cannot:
        rep.warnings.append(
            "the connection could not SET ROLE to "
            + ", ".join(sorted(cannot))
            + "; those roles keep every policied object they hold a grant on")
    catalog._stale = True
    return rep


def restrict_from_policies(catalog, engine, *, probe: bool = True,
                           hide_bypassing_views: bool = False,
                           report: bool = False):
    """Flag policied objects, withhold them from roles that get no rows, and
    name the views that bypass the policy. Run it *after*
    `restrict_from_grants`, because probing walks the roles that left on
    each object.

    Returns the catalog, or a ``PolicyReport`` when ``report=True``.
    """
    name = engine.dialect.name
    rep = PolicyReport(dialect=name)
    reader = POLICY_READERS.get(name)
    if reader is None:
        rep.warnings.append(
            f"no row-level policy reader for {name}; "
            f"supported: {', '.join(sorted(POLICY_READERS))}")
        return rep if report else catalog
    try:
        policied = reader(engine)
    except Exception as e:                            # noqa: BLE001
        rep.warnings.append(f"could not read policies ({type(e).__name__}: {e})")
        return rep if report else catalog

    bypassing: Set[Key] = set()
    bypass_reader = _BYPASS_READERS.get(name)
    if bypass_reader is not None:
        try:
            bypassing = bypass_reader(engine)
        except Exception as e:                        # noqa: BLE001
            rep.warnings.append(
                f"could not read view definitions ({type(e).__name__}: {e}); "
                "policy-bypassing views were not identified")

    prober = _PROBERS.get(name) if probe else None
    if probe and prober is None and policied:
        rep.warnings.append(
            f"{name} cannot be asked what a role gets from one connection; "
            "policied objects are flagged, not probed")

    fn = (lambda role, schema, obj: prober(engine, role, schema, obj)) if prober else None
    apply_policies(catalog, policied, bypassing, probe=fn,
                   hide_bypassing_views=hide_bypassing_views, report=rep)
    return rep if report else catalog
