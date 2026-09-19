# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Where a caller's roles come from.

`grants.py` answers one half of the question: which roles may see an object.
It reads that from the database, because a hand-copied ACL drifts. This
module answers the other half -- which roles does *this caller* hold -- and
for the same reason reads it from wherever the organisation already keeps it:
a directory (Microsoft Entra ID), a membership table, an HTTP endpoint, the
database's own role graph, or a file for the forty-table case.

Until now the caller supplied its own roles. That is fine for a desktop
client talking to its own database and useless for a hosted server, where
"the client says it holds `payroll`" is not an access check. With a
`Groups` resolver configured the client's roles are ignored and the
directory's answer is used instead, so the server's scoping is only as
trusting as the directory.

Three rules.

**Fail closed.** A source that errors -- token expired, endpoint down, user
not found -- raises `GroupError`. The caller gets an error, not an anonymous
selection, because "no groups" and "could not ask" are different answers and
only one of them is safe to act on.

**Every source declares whose subjects it serves.** `entra:` subjects go to
Graph, `db:` subjects to the role graph, and a source asked about a namespace
it does not serve returns nothing rather than guessing. A chain of sources is
a union, and a subject nobody serves resolves to no roles -- the same thing
an anonymous caller gets.

**Groups become roles through an explicit map, or by name.** Entra returns
object ids, and `restrict()` wants role names, so `map` translates. Anything
unmapped passes through by name when `passthrough` is on (the default), so a
catalog may name a directory group directly. Turn it off for a strict
allow-list.

Nothing here is required. No resolver configured means the behaviour before
this module existed: the roles the caller supplies are the roles it has.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import (Any, Callable, Dict, FrozenSet, Iterable, List, Mapping,
                    Optional, Sequence, Set)

from .identity import IdentityError, Principal

__all__ = ["GroupError", "Groups", "StaticGroups", "DatabaseGroups",
           "NativeRoles", "HttpGroups", "EntraGroups", "from_config",
           "local_part"]


class GroupError(IdentityError):
    """A source could not answer. Never turned into "no groups"."""


def local_part(subject: str) -> str:
    """``okta:jdoe`` -> ``jdoe``. The source prefix is routing, not identity."""
    return subject.split(":", 1)[1] if ":" in subject else subject


def _source_of(subject: str) -> str:
    return subject.split(":", 1)[0].lower() if ":" in subject else ""


def _names(values: Iterable[Any]) -> Set[str]:
    """Strings out of whatever a source returned, blanks dropped."""
    out: Set[str] = set()
    for v in values:
        if isinstance(v, str):
            s = v.strip()
            if s:
                out.add(s)
        elif isinstance(v, Mapping):
            # Entra, Okta and most directory APIs return objects. Keep the
            # id and the display name both, so `map` can key on either.
            for k in ("id", "displayName", "name", "value"):
                s = v.get(k)
                if isinstance(s, str) and s.strip():
                    out.add(s.strip())
        elif isinstance(v, (list, tuple)) and v:
            # A database row.
            s = v[0]
            if isinstance(s, str) and s.strip():
                out.add(s.strip())
    return out


# --------------------------------------------------------------------------
# sources
# --------------------------------------------------------------------------

class _Source:
    """Base for one place groups are read from.

    ``serves`` is the set of subject namespaces this source answers for;
    ``None`` means every namespace. ``name`` is what appears in errors.
    """
    name = "source"
    serves: Optional[FrozenSet[str]] = None

    def __init__(self, serves: Optional[Iterable[str]] = None) -> None:
        self.serves = frozenset(s.lower() for s in serves) if serves is not None else None

    def applies(self, subject: str) -> bool:
        return self.serves is None or _source_of(subject) in self.serves

    def groups(self, subject: str) -> Set[str]:            # pragma: no cover
        raise NotImplementedError

    def __repr__(self) -> str:                             # never secrets
        return f"{type(self).__name__}(serves={sorted(self.serves) if self.serves else 'all'})"


class StaticGroups(_Source):
    """A mapping in a file. ``{"okta:jdoe": ["finance"], ...}``.

    Subjects are matched exactly except for the namespace, which is
    case-insensitive like ``Principal.source``.
    """
    name = "static"

    def __init__(self, members: Mapping[str, Sequence[str]],
                 serves: Optional[Iterable[str]] = None) -> None:
        super().__init__(serves)
        self._members: Dict[str, Set[str]] = {}
        for subject, groups in members.items():
            key = _source_of(subject) + ":" + local_part(subject)
            self._members[key] = _names(groups)

    def groups(self, subject: str) -> Set[str]:
        key = _source_of(subject) + ":" + local_part(subject)
        return set(self._members.get(key, ()))


class DatabaseGroups(_Source):
    """A query against a membership table you already have.

    ``sql`` is run with one bound parameter, ``:subject``, holding the local
    part of the subject by default (``bind="local"``) or the whole namespaced
    subject (``bind="subject"``). The first column of each row is a group.
    Bound, never formatted: a subject is caller-controlled text.
    """
    name = "sql"

    def __init__(self, engine, sql: str, *, bind: str = "local",
                 serves: Optional[Iterable[str]] = None) -> None:
        super().__init__(serves)
        if bind not in ("local", "subject"):
            raise ValueError("bind must be 'local' or 'subject'")
        self._engine, self._sql, self._bind = engine, sql, bind

    def groups(self, subject: str) -> Set[str]:
        from sqlalchemy import text
        value = local_part(subject) if self._bind == "local" else subject
        with self._engine.connect() as conn:
            rows = conn.execute(text(self._sql), {"subject": value}).fetchall()
        # A SQLAlchemy Row is tuple-like but not a tuple; take the column.
        return _names(r[0] for r in rows)


class NativeRoles(_Source):
    """The database's own role graph, for ``db:<user>`` subjects.

    Uses the same readers `restrict_from_grants` uses, so a user who holds
    `SELECT` through `GRANT reporting TO analysts; GRANT analysts TO jdoe`
    resolves to both roles -- and the catalog, restricted from the same
    grants, lets them through. Transitive, cycle-safe, and one query.

    The readers return ``{granted: {roles that inherit it}}``; membership is
    the other direction, so the graph is reversed here and walked upward
    from the user. Names are compared case-insensitively, because Oracle
    upper-cases every identifier and PostgreSQL folds them down.
    """
    name = "native"

    def __init__(self, engine, serves: Iterable[str] = ("db",)) -> None:
        super().__init__(serves)
        self._engine = engine

    def groups(self, subject: str) -> Set[str]:
        from .grants import ROLE_GRAPH_READERS
        reader = ROLE_GRAPH_READERS.get(self._engine.dialect.name)
        if reader is None:
            raise GroupError(
                f"native roles are not readable on {self._engine.dialect.name!r}; "
                f"supported: {', '.join(sorted(ROLE_GRAPH_READERS)) or 'none'}")
        graph = reader(self._engine)
        holds: Dict[str, Set[str]] = {}
        canon: Dict[str, str] = {}
        for granted, inheritors in graph.items():
            canon.setdefault(granted.lower(), granted)
            for who in inheritors:
                canon.setdefault(who.lower(), who)
                holds.setdefault(who.lower(), set()).add(granted.lower())
        seen: Set[str] = set()
        stack = [local_part(subject).lower()]
        while stack:
            role = stack.pop()
            if role in seen:
                continue
            seen.add(role)
            stack.extend(holds.get(role, ()))
        seen.discard(local_part(subject).lower())
        return {canon.get(r, r) for r in seen}


def _http_json(req: urllib.request.Request, timeout: float) -> Any:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        # The body of a 4xx from Graph says which permission is missing.
        # It never carries the secret, and it is the one line the operator
        # needs, so it is kept; the token in the request header is not.
        detail = ""
        with contextlib.suppress(Exception):
            detail = e.read().decode("utf-8", "replace")[:300]
        raise GroupError(f"HTTP {e.code} from {req.full_url.split('?')[0]}: {detail}") from None
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise GroupError(f"could not reach {req.full_url.split('?')[0]}: {e}") from None
    try:
        return json.loads(body.decode("utf-8")) if body else None
    except ValueError:
        raise GroupError(f"non-JSON reply from {req.full_url.split('?')[0]}") from None


class HttpGroups(_Source):
    """Any endpoint that returns a caller's groups as JSON.

    ``url`` is a template: ``{id}`` is the URL-quoted local part, ``{subject}``
    the whole subject. The reply may be a list of strings, a list of objects
    with ``id``/``displayName``/``name``, or an object holding one of those
    under ``path`` (default: the first of ``groups``, ``roles``, ``value``).
    """
    name = "http"

    def __init__(self, url: str, *, headers: Optional[Mapping[str, str]] = None,
                 path: Optional[str] = None, timeout: float = 5.0,
                 serves: Optional[Iterable[str]] = None) -> None:
        super().__init__(serves)
        self._url, self._headers = url, dict(headers or {})
        self._path, self._timeout = path, timeout

    def groups(self, subject: str) -> Set[str]:
        url = self._url.format(id=urllib.parse.quote(local_part(subject), safe=""),
                               subject=urllib.parse.quote(subject, safe=""))
        req = urllib.request.Request(url, headers={"Accept": "application/json",
                                                   **self._headers})
        data = _http_json(req, self._timeout)
        if isinstance(data, Mapping):
            keys = [self._path] if self._path else ["groups", "roles", "value"]
            for k in keys:
                if k in data:
                    data = data[k]
                    break
            else:
                raise GroupError(f"reply from {url.split('?')[0]} has none of {keys}")
        if not isinstance(data, list):
            raise GroupError(f"reply from {url.split('?')[0]} is not a list of groups")
        return _names(data)


class EntraGroups(_Source):
    """Microsoft Entra ID (Azure AD), through Microsoft Graph.

    Client-credentials flow, then ``POST /users/{id}/getMemberGroups`` --
    which is **transitive**: a user in *Finance Analysts*, itself nested in
    *Finance*, gets both. ``{id}`` is the user's object id or UPN, whichever
    the subject carries (``entra:jdoe@contoso.com`` works).

    Returned as object ids plus display names (one ``getByIds`` call), so
    ``map`` may key on either and a ``restrict`` may name the group as the
    directory shows it. ``security_only=True`` drops Microsoft 365 groups
    and distribution lists, which is usually what an ACL wants.

    App registration needs application permissions ``User.Read.All`` and
    ``GroupMember.Read.All`` with admin consent. The secret is read once and
    never appears in ``repr``, logs or errors.
    """
    name = "entra"
    _AUTHORITY = "https://login.microsoftonline.com"
    _GRAPH = "https://graph.microsoft.com/v1.0"

    def __init__(self, tenant: str, client_id: str, client_secret: str, *,
                 names: bool = True, security_only: bool = False,
                 timeout: float = 10.0, serves: Iterable[str] = ("entra", "aad", "azuread")) -> None:
        super().__init__(serves)
        if not (tenant and client_id and client_secret):
            raise GroupError("entra source needs tenant, client_id and client_secret")
        self._tenant, self._client_id = tenant, client_id
        self._secret = client_secret
        self._names, self._security_only, self._timeout = names, security_only, timeout
        self._token: Optional[str] = None
        self._token_exp = 0.0
        self._lock = threading.Lock()

    def _bearer(self) -> str:
        with self._lock:
            if self._token and time.monotonic() < self._token_exp:
                return self._token
            form = urllib.parse.urlencode({
                "client_id": self._client_id, "client_secret": self._secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials"}).encode()
            req = urllib.request.Request(
                f"{self._AUTHORITY}/{urllib.parse.quote(self._tenant)}/oauth2/v2.0/token",
                data=form, headers={"Content-Type": "application/x-www-form-urlencoded"})
            data = _http_json(req, self._timeout)
            tok = (data or {}).get("access_token") if isinstance(data, Mapping) else None
            if not tok:
                raise GroupError("token endpoint returned no access_token")
            # Refresh a minute early; a token that expires mid-request is a
            # 401 that looks like a permission problem.
            self._token = tok
            self._token_exp = time.monotonic() + float((data or {}).get("expires_in", 3600)) - 60
            return tok

    def _graph(self, path: str, payload: Mapping[str, Any]) -> Any:
        req = urllib.request.Request(
            f"{self._GRAPH}{path}", data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self._bearer()}",
                     "Content-Type": "application/json", "Accept": "application/json"})
        return _http_json(req, self._timeout)

    def groups(self, subject: str) -> Set[str]:
        user = urllib.parse.quote(local_part(subject), safe="@")
        data = self._graph(f"/users/{user}/getMemberGroups",
                           {"securityEnabledOnly": self._security_only})
        ids = _names((data or {}).get("value", [])) if isinstance(data, Mapping) else set()
        out = set(ids)
        if self._names and ids:
            # getByIds takes at most 1000 ids per call.
            id_list = sorted(ids)
            for i in range(0, len(id_list), 1000):
                got = self._graph("/directoryObjects/getByIds",
                                  {"ids": id_list[i:i + 1000], "types": ["group"]})
                if isinstance(got, Mapping):
                    out |= _names(got.get("value", []))
        return out


# --------------------------------------------------------------------------
# the resolver
# --------------------------------------------------------------------------

@dataclass
class _Entry:
    roles: FrozenSet[str]
    at: float


class Groups:
    """Roles for a subject, from one or more sources, cached.

    >>> g = Groups([StaticGroups({"okta:jdoe": ["Finance Analysts"]})],
    ...            map={"Finance Analysts": "finance"})
    >>> sorted(g.roles_for("okta:jdoe"))
    ['Finance Analysts', 'finance']
    >>> g.principal("okta:jdoe")
    Principal('okta:jdoe')

    ``ttl`` bounds how stale an answer may be; a revoked membership is honoured
    within that many seconds. ``maxsize`` bounds memory; past it the oldest
    entries go. A failing source raises `GroupError` and nothing is cached,
    so a transient outage is retried on the next call rather than remembered.
    """

    def __init__(self, sources: Sequence[_Source], *,
                 map: Optional[Mapping[str, str]] = None,
                 passthrough: bool = True, ttl: float = 300.0,
                 maxsize: int = 10_000,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.sources = list(sources)
        self.map = {str(k): str(v) for k, v in (map or {}).items()}
        self.passthrough = passthrough
        self.ttl, self.maxsize, self._clock = float(ttl), int(maxsize), clock
        self._cache: Dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self.stats = {"hits": 0, "misses": 0, "errors": 0}

    # -- resolution -------------------------------------------------------

    def groups_for(self, subject: str) -> Set[str]:
        """Raw group names/ids from every source that serves this subject."""
        out: Set[str] = set()
        for src in self.sources:
            if not src.applies(subject):
                continue
            try:
                out |= src.groups(subject)
            except GroupError:
                raise
            except Exception as e:                           # noqa: BLE001
                # The source's own exception may carry a URL with a token in
                # it or a connection string. Type and a short message only.
                raise GroupError(f"{src.name} source failed for {subject!r}: "
                                 f"{type(e).__name__}: {str(e)[:200]}") from None
        return out

    def roles_for(self, subject: str) -> FrozenSet[str]:
        """Roles for ``subject``: mapped groups, plus unmapped ones by name
        when ``passthrough`` is on. Cached for ``ttl`` seconds."""
        now = self._clock()
        with self._lock:
            hit = self._cache.get(subject)
            if hit is not None and now - hit.at < self.ttl:
                self.stats["hits"] += 1
                return hit.roles
        try:
            groups = self.groups_for(subject)
        except GroupError:
            with self._lock:
                self.stats["errors"] += 1
            raise
        roles: Set[str] = set()
        for g in groups:
            if g in self.map:
                roles.add(self.map[g])
            elif self.passthrough:
                roles.add(g)
        # A group may also be listed under a mapped alias with different case.
        frozen = frozenset(roles)
        with self._lock:
            self.stats["misses"] += 1
            if len(self._cache) >= self.maxsize:
                oldest = min(self._cache, key=lambda k: self._cache[k].at)
                del self._cache[oldest]
            self._cache[subject] = _Entry(frozen, now)
        return frozen

    def principal(self, subject: str) -> Principal:
        """A Principal whose roles are the directory's answer, not the caller's."""
        p = Principal(subject)               # validates the namespace first
        return Principal(p.subject, roles=self.roles_for(p.subject))

    def resolve(self, principal: Principal) -> Principal:
        """Same, for a Principal already built. Its own roles are discarded."""
        return self.principal(principal.subject)

    def forget(self, subject: Optional[str] = None) -> None:
        """Drop the cache, for one subject or all. A revocation that must be
        honoured now rather than within ``ttl``."""
        with self._lock:
            if subject is None:
                self._cache.clear()
            else:
                self._cache.pop(subject, None)

    def describe(self) -> Dict[str, Any]:
        """For a health endpoint. Counts and kinds; no names, no subjects."""
        return {"sources": [s.name for s in self.sources], "mapped": len(self.map),
                "passthrough": self.passthrough, "ttl": self.ttl,
                "cached": len(self._cache), **self.stats}


# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand(value: Any, env: Mapping[str, str]) -> Any:
    """``${NAME}`` -> the environment variable, so the JSON file holds no
    secret. A reference to an unset variable is an error, not an empty
    string: an empty client secret fails at Graph with a message that does
    not say why."""
    if isinstance(value, str):
        def sub(m):
            name = m.group(1)
            if name not in env:
                raise GroupError(f"groups config refers to ${{{name}}} but it is not set")
            return env[name]
        return _ENV_REF.sub(sub, value)
    if isinstance(value, Mapping):
        return {k: _expand(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v, env) for v in value]
    return value


def from_config(block: Optional[Mapping[str, Any]], *,
                env: Optional[Mapping[str, str]] = None,
                default_url: Optional[str] = None,
                engine_factory: Optional[Callable[[str], Any]] = None) -> Optional[Groups]:
    """Build a resolver from the ``groups`` block of a catalog config.

    ::

        {"groups": {
           "ttl": 300,
           "map": {"5f1c...": "finance", "Finance Analysts": "finance"},
           "passthrough": true,
           "sources": [
             {"type": "static", "members": {"okta:jdoe": ["finance"]}},
             {"type": "sql", "sql": "SELECT role FROM app_membership WHERE subject = :subject",
              "url": "postgresql://...", "for": ["okta"]},
             {"type": "native"},
             {"type": "http", "url": "https://idp.example.com/users/{id}/groups",
              "headers": {"Authorization": "Bearer ${GROUPS_API_TOKEN}"}, "for": ["okta"]},
             {"type": "entra", "tenant": "contoso.onmicrosoft.com",
              "client_id": "...", "client_secret": "${ENTRA_CLIENT_SECRET}",
              "security_only": true}]}}

    ``for`` limits a source to those subject namespaces. ``sql`` and
    ``native`` sources use ``url`` when given and the catalog's own database
    (``default_url``) otherwise. Returns ``None`` for an absent or empty
    block, which means "trust the caller's roles" as before.
    """
    if not block:
        return None
    env = os.environ if env is None else env
    block = _expand(dict(block), env)
    raw_sources = block.get("sources")
    if raw_sources is None and block.get("type"):
        raw_sources = [block]                # a single source, unwrapped
    if not raw_sources:
        return None

    def engine_for(spec: Mapping[str, Any]):
        url = spec.get("url") or default_url
        if not url:
            raise GroupError(f"{spec.get('type')} source needs a url (none given and no catalog url)")
        if engine_factory is not None:
            return engine_factory(url)
        from .introspect import engine_from_url
        return engine_from_url(url, pool_pre_ping=True)

    sources: List[_Source] = []
    for spec in raw_sources:
        kind = str(spec.get("type", "")).lower()
        serves = spec.get("for")
        if kind == "static":
            sources.append(StaticGroups(spec.get("members") or {}, serves=serves))
        elif kind == "sql":
            if not spec.get("sql"):
                raise GroupError("sql source needs a 'sql' query with a :subject parameter")
            sources.append(DatabaseGroups(engine_for(spec), spec["sql"],
                                          bind=spec.get("bind", "local"), serves=serves))
        elif kind == "native":
            sources.append(NativeRoles(engine_for(spec), serves=serves or ("db",)))
        elif kind == "http":
            if not spec.get("url"):
                raise GroupError("http source needs a url")
            sources.append(HttpGroups(spec["url"], headers=spec.get("headers"),
                                      path=spec.get("path"),
                                      timeout=float(spec.get("timeout", 5.0)), serves=serves))
        elif kind == "entra":
            sources.append(EntraGroups(
                spec.get("tenant", ""), spec.get("client_id", ""), spec.get("client_secret", ""),
                names=bool(spec.get("names", True)),
                security_only=bool(spec.get("security_only", False)),
                timeout=float(spec.get("timeout", 10.0)),
                serves=serves or ("entra", "aad", "azuread")))
        else:
            raise GroupError(f"unknown groups source type {kind!r}; "
                             "expected static, sql, native, http or entra")
    return Groups(sources, map=block.get("map"),
                  passthrough=bool(block.get("passthrough", True)),
                  ttl=float(block.get("ttl", 300.0)),
                  maxsize=int(block.get("maxsize", 10_000)))
