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

Oracle (VPD) is probed two ways, because a policy function can key on
either of two things:

- **Client identifier.** ``DBMS_SESSION.SET_IDENTIFIER(role)`` on the
  existing connection, then one row. No privilege needed. A policy that reads
  ``SYS_CONTEXT('USERENV','CLIENT_IDENTIFIER')`` -- the pattern Oracle
  documents for connection-pooled applications -- reacts; one that keys on
  the session user does not. So this probe can only *withhold*: it withholds
  when the identifier turned a table that had rows into one with none, which
  is a policy demonstrably reacting to it. Rows prove nothing on their own.
- **Proxy authentication.** Connect as ``app[role]``: the session user *is*
  the role, so a policy keyed on ``SESSION_USER`` fires for it. This is the
  ``SET ROLE`` analogue and its answer is final. It needs one statement from
  a DBA per user -- ``ALTER USER role GRANT CONNECT THROUGH app`` -- and when
  that is missing the role is kept and the report says which statement.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

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
    #: roles the connection could not act as (SET ROLE, proxy); kept, not withheld
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
            out += ("\n  not probed (connection cannot act as them): "
                    + ", ".join(sorted(set(self.unprobed_roles))))
        for w in self.warnings:
            out += f"\n  warning: {w}"
        return out


class CannotSetRole(Exception):
    """The connection cannot act as the role: on PostgreSQL neither a
    superuser nor a member of it; on Oracle not authorised to proxy for it.
    The message says what would fix it."""


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


def _ora_one(conn, target: str) -> bool:
    return conn.exec_driver_sql(
        f"SELECT 1 FROM {target} FETCH FIRST 1 ROW ONLY").fetchone() is not None


class _OracleProber:
    """Client identifier first, proxy authentication for the final word.

    One proxied engine per role, reused across every policied object and
    disposed by ``close()``; the app connection is never left with an
    identifier set, even when the probe raises.
    """

    def __init__(self, engine, connect_args: Optional[Dict[str, Any]] = None):
        self.engine = engine
        self.connect_args = dict(connect_args or {})
        self._proxied: Dict[str, Any] = {}

    def _target(self, schema: Optional[str], name: str) -> str:
        d = self.engine.dialect
        q = d.identifier_preparer.quote
        # reflection normalises Oracle's upper-case names to lower; put them back
        name = d.denormalize_name(name)
        schema = d.denormalize_name(schema) if schema else None
        return f"{q(schema)}.{q(name)}" if schema else q(name)

    def __call__(self, role: str, schema: Optional[str], name: str) -> bool:
        target = self._target(schema, name)
        with self.engine.connect() as conn:
            if _ora_one(conn, target):
                conn.exec_driver_sql(
                    "BEGIN DBMS_SESSION.SET_IDENTIFIER(:1); END;", (role,))
                try:
                    reacted_to_nothing = not _ora_one(conn, target)
                finally:
                    conn.exec_driver_sql("BEGIN DBMS_SESSION.CLEAR_IDENTIFIER; END;")
                if reacted_to_nothing:
                    # rows without the identifier, none with it: the policy
                    # keys on the identifier and admits this role nothing
                    return False
        return self._proxy(role, target)

    def _proxy(self, role: str, target: str) -> bool:
        eng = self._proxied.get(role)
        if eng is None:
            from .introspect import engine_from_url
            app = self.engine.url.username or ""
            url = self.engine.url.set(username=f"{app}[{role}]")
            try:
                eng = engine_from_url(url, connect_args=self.connect_args,
                                      pool_pre_ping=True)
                with eng.connect() as conn:
                    conn.exec_driver_sql("SELECT 1 FROM dual").fetchone()
            except Exception as e:                    # noqa: BLE001
                first = str(e).splitlines()[0][:120]
                raise CannotSetRole(
                    f"cannot proxy for {role} ({first}); a DBA can allow it with "
                    f"ALTER USER {role} GRANT CONNECT THROUGH {app}") from e
            self._proxied[role] = eng
        with eng.connect() as conn:
            return _ora_one(conn, target)

    def close(self) -> None:
        for eng in self._proxied.values():
            try:
                eng.dispose()
            except Exception:                         # noqa: BLE001
                pass
        self._proxied.clear()


class _PostgresProber:
    def __init__(self, engine, connect_args=None):
        self.engine = engine

    def __call__(self, role, schema, name):
        return _pg_probe(self.engine, role, schema, name)

    def close(self) -> None:
        pass


POLICY_READERS["postgresql"] = _pg_policied
POLICY_READERS["oracle"] = _ora_policied

#: dialect -> prober factory(engine, connect_args); the prober is called with
#: (role, schema, name) and closed when the run is over.
_PROBERS: Dict[str, Callable] = {"postgresql": _PostgresProber,
                                 "oracle": _OracleProber}
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
    why: Dict[str, str] = {}

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
                    except CannotSetRole as e:
                        cannot.add(role)
                        why.setdefault(role, str(e))
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
            "the connection could not act as "
            + ", ".join(sorted(cannot))
            + "; those roles keep every policied object they hold a grant on")
        for role in sorted(cannot):
            if why.get(role):
                rep.warnings.append(why[role])
    catalog._stale = True
    return rep


def restrict_from_policies(catalog, engine, *, probe: bool = True,
                           hide_bypassing_views: bool = False,
                           connect_args: Optional[Dict[str, Any]] = None,
                           report: bool = False):
    """Flag policied objects, withhold them from roles that get no rows, and
    name the views that bypass the policy. Run it *after*
    `restrict_from_grants`, because probing walks the roles that left on
    each object.

    ``connect_args`` is what the engine was built with -- a wallet directory
    and password, say -- so that an Oracle proxy session can be opened the
    same way; the environment's ``SCHEMAGATE_CONNECT_ARGS`` is merged in
    regardless.

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

    factory = _PROBERS.get(name) if probe else None
    if probe and factory is None and policied:
        rep.warnings.append(
            f"{name} cannot be asked what a role gets from one connection; "
            "policied objects are flagged, not probed")

    prober = factory(engine, connect_args) if factory else None
    try:
        apply_policies(catalog, policied, bypassing, probe=prober,
                       hide_bypassing_views=hide_bypassing_views, report=rep)
    finally:
        if prober is not None:
            prober.close()
    return rep if report else catalog
