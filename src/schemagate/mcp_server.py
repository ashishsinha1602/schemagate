# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""MCP server: let an agent ask schemagate which tables it needs.

Any MCP-capable client -- Cursor, Windsurf, Zed, an agent you
wrote -- can call ``select_schema`` and get back the compact DDL for exactly
the objects a question needs, already filtered to what the caller may see.
The agent then writes SQL against that, and never sees the rest.

    pip install 'schemagate[mcp]'
    SCHEMAGATE_DATABASE_URL=postgresql://localhost/app python -m schemagate.mcp_server

A desktop MCP client, in its config file::

    {"mcpServers": {"schemagate": {
        "command": "python", "args": ["-m", "schemagate.mcp_server"],
        "env": {"SCHEMAGATE_DATABASE_URL": "postgresql://localhost/app"}}}}

To host it for a team instead of one desktop::

    SCHEMAGATE_MCP_TRANSPORT=streamable-http SCHEMAGATE_MCP_PORT=8765 python -m schemagate.mcp_server

Identity: every tool takes ``principal`` and ``roles``. The server does not
guess who is asking -- if the client omits them, the caller is treated as
anonymous and sees only unrestricted objects. Fail closed.

Where the trust boundary is
---------------------------
Read this before exposing the server on a port. **The principal and roles are
asserted by the client, and this server believes them.** There is no
authentication here: no token, no session, no signature. Fail-closed protects
the caller who omits a role, not the one who invents it -- anyone who can
reach the transport can pass ``roles=["payroll"]`` and read what that role may
read. Since ``run_query`` returns rows rather than schema, that is data.

So it is safe exactly where the transport is: over stdio, where the only
caller is the desktop client on your own machine; or over HTTP **behind
something that authenticates the user and fills in the principal itself** --
a gateway, a proxy, your own service. Do not put the HTTP transport on a
network you do not control and rely on ``principal`` to keep people apart.
It is a scoping mechanism, not a lock.

The OCI stack narrows it to a CIDR you name and refuses ``0.0.0.0/0``, which
is a network control rather than an identity one. A shared secret is not yet
implemented.

Restrictions and hints come from ``SCHEMAGATE_CATALOG_CONFIG``, a JSON file::

    {"restrict": {"hr_compensation": ["payroll"]},
     "hint":     {"invoice_draft": "drafts only, not revenue"},
     "describe": {"v_stock_shortfall": "Items below their reorder level."}}

``describe`` is filled by ``schemagate describe`` (with a key, or by pasting
the prompt into any chat -- no key needed).

Staying up
----------
The index lives in memory after startup, so the database going away does
not take the server with it: ``select_schema`` keeps answering from the
last good reflection, and ``refresh_catalog`` reports failure instead of
raising. Every tool returns ``{"error": ...}`` for bad input rather than
letting an exception reach the transport. ``health`` tells a load balancer
or a person what state the server is in.
"""
from __future__ import annotations

import functools
import inspect
import logging
import os
import re
import threading
import time
from typing import Annotated, Any, Dict, List, Optional

from . import __version__
from .catalog import Catalog
from .audit import AUDITED, AuditLog, summarize
from .learn import Memory
from .identity import IdentityError, Principal

log = logging.getLogger("schemagate.mcp")

_CATALOG: Optional[Catalog] = None
#: The URL the catalog was reflected from, kept so `run_query` has something
#: to execute against. Reflection disposes its engine on purpose -- the index
#: lives in memory and holds nothing open -- so execution builds its own,
#: lazily, and only if someone actually runs a query.
_URL: Optional[str] = None
_ENGINE: Any = None
#: Every identity decision, recorded. Memory-only unless SCHEMAGATE_AUDIT_LOG
#: names a file. Built in build_catalog; a module-level default so the tool
#: functions can be called in tests before any catalog exists.
_AUDIT: Any = None
#: Where a caller's roles come from, when the catalog config has a
#: ``groups`` block. None means the roles the client supplies are used --
#: the behaviour the warning in the module docstring is about.
_GROUPS: Any = None
#: Question -> SQL pairs that answered correctly, consulted for pins and
#: worked examples. Memory-only unless SCHEMAGATE_MEMORY names a file.
#: Built once the catalog exists, because it uses the catalog's embedder.
_MEMORY: Any = None
_LOCK = threading.Lock()
_STATE: Dict[str, Any] = {
    "started_at": None, "url": None, "config": None,
    "last_refresh_at": None, "last_refresh_ok": None, "last_error": None,
    "calls": 0, "errors": 0,
}

#: Hard caps so one pathological request cannot stall the server.
MAX_QUESTION_CHARS = 2000
MAX_TOP_K = 50
MAX_ROLES = 100
#: Rows a single `run_query` may return. A model asking for a whole table
#: should get a page of it and be told there is more, not fill the context.
MAX_ROWS = 200
DEFAULT_ROWS = 50
#: Characters of SQL accepted. Generous for a real query, small enough that
#: nobody posts a novel through the tool.
MAX_SQL_CHARS = 20000


def _apply_config(cat: Catalog, config_path: Optional[str]) -> None:
    if not config_path:
        return
    from . import config as _config
    _config.apply(cat, _config.load(config_path))


def _groups_from(config_path: Optional[str], url: Optional[str]):
    """The resolver named by the config's ``groups`` block, or None.

    Built at startup so a bad block -- a ``${SECRET}`` that is not set, an
    unknown source type -- stops the server before it answers anyone with
    the client's own roles, rather than at the first request.
    """
    if not config_path:
        return None
    from . import config as _config
    return _config.groups_from(_config.load(config_path),
                               default_url=None if url == "demo" else url)


def _reflect(url: str, config_path: Optional[str]) -> Catalog:
    if url == "demo":
        from .demo_schema import demo_catalog
        cat = demo_catalog(name="demo")          # cat._demo_url: run_query's target
    else:
        from .introspect import engine_from_url
        # pool_pre_ping: a connection that died while idle is replaced
        # rather than raised on first use after a database restart
        engine = engine_from_url(url, pool_pre_ping=True)
        try:
            # `--values` for the server. The CLI and Studio had it; the server,
            # which is how most people reach a database through a model, had
            # no way to ask -- so its users got 'Card' guessed for 'CARD'.
            # Still off unless set: it reads rows, not just the catalog.
            values = str(os.environ.get("SCHEMAGATE_VALUES", "")).strip().lower() in (
                "1", "true", "yes", "on")
            try:
                budget = float(os.environ.get("SCHEMAGATE_VALUES_BUDGET", "30"))
            except ValueError:
                budget = 30.0    # a typo here must not stop the server starting
            cat = Catalog().bootstrap(engine, sample_values=values,
                                      sample_budget=budget)
        finally:
            engine.dispose()     # the index is in memory; hold nothing open
    _apply_config(cat, config_path)
    if url != "demo":
        # The catalogue, without being asked for it -- after the config so a
        # hint or a database comment is never overwritten. No key: no-op.
        from .ai.auto import ensure_described
        from sqlalchemy.engine import make_url
        try:
            label = make_url(url).render_as_string(hide_password=True)
        except Exception:                                        # noqa: BLE001
            label = None
        ensure_described(cat, label=label)
    return cat


def build_catalog(url: Optional[str] = None, config_path: Optional[str] = None,
                  catalog: Optional[Catalog] = None, groups: Any = None) -> Catalog:
    """Build (or accept) the catalog the server will answer from.

    Tests pass ``catalog=`` directly; the CLI path reads
    ``SCHEMAGATE_DATABASE_URL`` and the optional ``SCHEMAGATE_CATALOG_CONFIG``.
    """
    global _CATALOG, _AUDIT, _MEMORY, _GROUPS
    with _LOCK:
        _STATE["started_at"] = _STATE["started_at"] or time.time()
        _AUDIT = AuditLog.from_env()
        if catalog is not None:
            _CATALOG = catalog
            _GROUPS = groups
            _MEMORY = Memory.from_env(catalog.embedder, catalog.name)
            _STATE.update(url="<provided>", last_refresh_at=time.time(),
                          last_refresh_ok=True, last_error=None)
            return catalog

        url = url or os.environ.get("SCHEMAGATE_DATABASE_URL")
        if not url:
            raise SystemExit(
                "schemagate.mcp_server: set SCHEMAGATE_DATABASE_URL to a SQLAlchemy URL, "
                "or use SCHEMAGATE_DATABASE_URL=demo for the bundled schema")
        config_path = config_path or os.environ.get("SCHEMAGATE_CATALOG_CONFIG")
        cat = _reflect(url, config_path)
        _CATALOG = cat
        _GROUPS = _groups_from(config_path, url)
        _MEMORY = Memory.from_env(cat.embedder, _memory_label(url))
        globals()["_URL"] = cat._demo_url if url == "demo" else url
        globals()["_ENGINE"] = None
        _STATE.update(url=_redact(url), config=config_path,
                      last_refresh_at=time.time(), last_refresh_ok=True,
                      last_error=None)
        return cat


def _memory_label(url: str) -> str:
    """A stable, password-free name for this database's memory file."""
    try:
        from sqlalchemy.engine import make_url
        u = make_url(url)
        return "%s-%s-%s" % (u.get_backend_name(), u.host or "local", u.database or "db")
    except Exception:                                    # noqa: BLE001
        return "default"


def _memory():
    global _MEMORY
    if _MEMORY is None:
        cat = _CATALOG
        _MEMORY = Memory(cat.embedder) if cat is not None else Memory(__import__("schemagate.catalog", fromlist=["default_embedder"]).default_embedder())
    return _MEMORY


def _redact(url: str) -> str:
    """Never echo a password back through a tool result or a log line."""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        creds, host = rest.rsplit("@", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return url


def _dialect_name() -> str:
    """The dialect the SQL will run on, from the URL alone -- no connection.
    Empty when the catalog was supplied directly and there is no URL."""
    if not _URL:
        return ""
    try:
        from sqlalchemy.engine import make_url
        return make_url(_URL).get_dialect().name
    except Exception:                                    # noqa: BLE001
        return ""


def _engine():
    """The engine used to run queries, built on first use and kept pooled."""
    global _ENGINE
    with _LOCK:
        if _ENGINE is None:
            if not _URL:
                raise RuntimeError(
                    "this server has no database URL to run queries against "
                    "(the catalog was supplied directly)")
            from .introspect import engine_from_url
            _ENGINE = engine_from_url(_URL, pool_pre_ping=True, pool_recycle=1800)
        return _ENGINE


#: One identifier part, bare or quoted the way some dialect quotes it:
#: "x" (ANSI, Postgres, Oracle), [x] (SQL Server, SQLite), `x` (MySQL, SQLite).
#: The previous pattern knew only "x", so `FROM [hr_compensation]` and
#: FROM `hr_compensation` named nothing it could see -- and an empty list of
#: names passed the scope check.
_PART = r'(?:"[^"]+"|\[[^\]]+\]|`[^`]+`|[A-Za-z_][\w$#]*)'
_REF = _PART + r"(?:\s*\.\s*" + _PART + r")*"
_NOT_ALIAS = (r"(?!(?:where|join|on|using|group|order|limit|union|intersect|except|inner|left|right|full|"
              r"cross|natural|having|window|offset|fetch|for|outer|lateral|straight_join|qualify|"
              r"connect|start|pivot|unpivot|sample|tablesample|match_recognize)\b)")
_ITEM = _REF + r"(?:\s+(?:as\s+)?" + _NOT_ALIAS + _PART + r")?"
#: `FROM a, b c, d AS e` and `JOIN x` -- every item of a FROM list, not just
#: the first: `FROM hr_employee, hr_compensation` used to read as one table.
_REFERENCED = re.compile(r"\b(?:from|join)\s+(" + _ITEM + r"(?:\s*,\s*" + _ITEM + r")*)", re.I)
#: `WITH name AS (`, and the `, name AS (` that follow it.
_CTE = re.compile(r"(?:\bwith\b|,)\s*(" + _PART + r")\s+as\s*\(", re.I)


def _unquote(part: str) -> str:
    return part.strip()[1:-1] if part.strip()[:1] in ('"', "[", "`") else part.strip()


def _sql_body(sql: str) -> str:
    """The statement with comments removed and string literals emptied."""
    body = re.sub(r"--[^\n]*", " ", sql)
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    return re.sub(r"'(?:[^']|'')*'", "''", body)


def _referenced_tables(sql: str) -> List[str]:
    """Base tables the statement reads, with CTE and subquery aliases removed."""
    body = _sql_body(sql)
    ctes = {_unquote(c).lower() for c in _CTE.findall(body)}
    out, seen = [], set()
    for clause in _REFERENCED.findall(body):
        for item in re.findall(_ITEM, clause):
            ref = re.match(_REF, item.strip())
            if not ref:
                continue
            name = ".".join(_unquote(p) for p in re.findall(_PART, ref.group(0)))
            if not name or name.lower() in ctes or name.lower() in seen:
                continue
            seen.add(name.lower())
            out.append(name)
    return out


def _identifiers(sql: str) -> set:
    """Every identifier part in the statement, unquoted and lower-cased."""
    return {_unquote(p).lower() for p in re.findall(_PART, _sql_body(sql))}


#: A projection that takes every column: `SELECT *`, `SELECT DISTINCT *`,
#: `, *`, `t.*`. COUNT(*) is not one; it reads no column's values.
_STAR = re.compile(r"\bselect\s+(?:distinct\s+|all\s+|top\s*\(?\s*\d+\s*\)?\s+)?\*|,\s*\*\s*(?:,|\bfrom\b)|"
                   r"(?:\w|\"|\]|`)\s*\.\s*\*", re.I)


def _check_scope(cat: Catalog, sql: str, who: Optional[Principal]) -> Optional[str]:
    """Refuse SQL that reads anything this caller may not see.

    This is the whole point of the library, so it is enforced here and not
    left to the model: `select_schema` withholding a table means nothing if
    the next tool will run `SELECT * FROM` it anyway. An agent that guesses a
    name, or a prompt-injected one that is told to, gets the same answer.

    Fail closed. A table that does not resolve to an object this principal can
    see is refused, whether it is restricted, misspelled, or something the
    catalog never reflected -- because from here those look identical, and
    the safe reading of "I do not recognise this" is no.
    """
    visible, hidden = {}, set()
    for doc in cat.objects():
        if not cat._visible(doc, who):
            hidden.add((doc.name or "").lower())
            hidden.add(doc.qname.lower())
            continue
        visible[(doc.name or "").lower()] = doc
        visible[doc.qname.lower()] = doc
    refs = _referenced_tables(sql)
    unknown = [t for t in refs
               if t.lower() not in visible
               and t.lower().split(".")[-1] not in visible]
    # Backstop, whatever the syntax: a name this caller may not see, anywhere
    # in the statement, is refused -- a FROM-list form the parser does not
    # know, a LATERAL, a dialect's own table function. A hidden table whose
    # name is also a visible object's name is left to the check above.
    idents = _identifiers(sql)
    unknown += sorted(n for n in (idents & hidden) - set(visible) if n not in {u.lower() for u in unknown})
    if unknown:
        return ("not available to this caller: %s. Call select_schema and use "
                "only the objects it returns." % ", ".join(sorted(set(unknown))))
    # Column rules. A table the caller may read can still hold a column it
    # may not: `SELECT *` would return it, and so would naming it.
    used = [visible.get(t.lower()) or visible.get(t.lower().split(".")[-1]) for t in refs]
    used = [d for d in used if d is not None]
    shown = {c.name.lower() for d in used for c in d.visible_columns(who)}
    withheld = {c.name.lower() for d in used for c in d.columns} - shown
    if withheld:
        named = sorted(idents & withheld)
        if named:
            return ("not available to this caller: column %s. Call select_schema and "
                    "use only the columns it returns." % ", ".join(named))
        if _STAR.search(_sql_body(sql)):
            return ("not available to this caller: SELECT * would include columns this "
                    "caller may not see. Name the columns select_schema returned.")
    return None


def _catalog() -> Catalog:
    if _CATALOG is None:
        build_catalog()
    return _CATALOG  # type: ignore[return-value]


def _principal(subject: Optional[str], roles: Optional[List[str]]) -> Optional[Principal]:
    if not subject:
        return None
    if roles is not None and len(roles) > MAX_ROLES:
        raise IdentityError(f"too many roles ({len(roles)}); max {MAX_ROLES}")
    if _GROUPS is not None:
        # The directory's answer, not the client's. Roles the client sent
        # are dropped, not merged: a merge would let anyone add `payroll`
        # to whatever the directory said, which is the hole this closes.
        # A source that cannot answer raises, and _guard turns that into an
        # error reply -- never into an anonymous selection.
        if roles:
            log.debug("client-supplied roles ignored; groups resolver is configured")
        return _GROUPS.principal(str(subject))
    return Principal(str(subject),
                     roles=frozenset(str(r) for r in (roles or [])))


def _guard(fn):
    """Every tool returns a dict, whatever happens inside it.

    Bad identity -> {"error": ...} with the message the user needs.
    Anything else -> {"error": ...} with a generic message, logged with
    the traceback server-side. Nothing propagates to the transport, so a
    single bad request cannot end the session for every other client.
    """
    sig = inspect.signature(fn)

    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        _STATE["calls"] += 1
        try:
            result = fn(*args, **kwargs)
        except IdentityError as e:
            _STATE["errors"] += 1
            result = {"error": str(e)}
        except Exception as e:                       # noqa: BLE001
            _STATE["errors"] += 1
            _STATE["last_error"] = f"{type(e).__name__}: {e}"
            log.exception("tool %s failed", fn.__name__)
            result = {"error": f"{fn.__name__} failed: {type(e).__name__}",
                      "hint": "see server log; the catalog is still serving"}
        return _audited(fn.__name__, sig, args, kwargs, result)
    return wrapped


def _audited(tool: str, sig, args, kwargs, result: Dict[str, Any]) -> Dict[str, Any]:
    """Record the call, then hand back the result with the server-side hints
    removed.

    Tools attach `_`-prefixed keys (`_visible_objects`, `_denied_reason`,
    `_tables`, ...) that the audit record wants and the caller must not get:
    `describe_object` answers "missing" and "restricted" with the same words
    on purpose, and the log may know which while the client may not. The
    hints are stripped here, in the one place every tool passes through, so
    a tool cannot forget.
    """
    if tool in AUDITED and isinstance(result, dict):
        try:
            bound = sig.bind_partial(*args, **kwargs)
            named = dict(bound.arguments)
        except Exception:                            # noqa: BLE001
            named = dict(kwargs)                     # audit still happens
        try:
            _audit().record(summarize(tool, named, result))
        except Exception:                            # noqa: BLE001
            log.exception("audit record failed")    # never the caller's problem
    if isinstance(result, dict):
        return {k: v for k, v in result.items() if not k.startswith("_")}
    return result


def _audit():
    global _AUDIT
    if _AUDIT is None:
        _AUDIT = AuditLog.from_env()
    return _AUDIT



# --- what each parameter means, in the tool schema an agent reads -------
# Field is pydantic's, present whenever the mcp package is; without it the
# descriptions are inert metadata and the functions behave the same.
try:
    from pydantic import Field
except ImportError:                                   # pragma: no cover - library use without [mcp]
    def Field(*_a, **_k):                             # type: ignore[no-redef]
        return None

Question = Annotated[str, Field(description=(
    "The user's question in plain language, e.g. 'revenue by month' or 'which customers owe us money'."))]
PrincipalArg = Annotated[Optional[str], Field(description=(
    "Who is asking, as an identity string such as 'okta:jdoe'. Pass it whenever you know the user: "
    "visibility is decided for this identity. Omitted = anonymous, which sees only unrestricted objects."))]
RolesArg = Annotated[Optional[List[str]], Field(description=(
    "The caller's roles or groups, e.g. ['finance', 'payroll']. Objects and columns restricted to a role "
    "are visible only when it is listed here. Omitted = no roles."))]
TopK = Annotated[int, Field(description=(
    "How many tables and views to select for the question (default 6). Raise it for questions that span "
    "many areas; the caller's visible objects are the upper bound."), ge=1, le=50)]
ExpandFK = Annotated[bool, Field(description=(
    "Also pull in tables joined by foreign key to the selected ones (default true), only where the caller "
    "may read them. Set false for the bare top matches."))]
ObjectName = Annotated[str, Field(description=(
    "Table or view name as returned by select_schema or list_objects, bare ('orders') or schema-qualified "
    "('sales.orders')."))]
SqlArg = Annotated[str, Field(description=(
    "One read-only SELECT (or WITH ... SELECT) written against the DDL select_schema returned. Writes, DDL "
    "and multiple statements are refused, as is any table or column this caller may not read."))]
MaxRows = Annotated[int, Field(description=(
    "Most rows to return (default 50, at most 200). The result says when it was truncated."), ge=1, le=200)]

# --- tool implementations, importable without the mcp package ------------
# Kept separate from the server wiring so they can be unit-tested directly
# and reused by anyone building their own server.

@_guard
def select_schema(question: Question, principal: PrincipalArg = None,
                  roles: RolesArg = None, top_k: TopK = 6,
                  expand_foreign_keys: ExpandFK = True) -> Dict[str, Any]:
    """Pick the tables and views a question needs, scoped to the caller.

    Returns the compact DDL to put in the SQL-writing prompt, the object
    names, and a per-object explanation. Objects the caller may not read
    are absent -- not hidden, absent -- so the model cannot write SQL
    against them.
    """
    question = str(question or "").strip()
    if not question:
        return {"error": "question is empty"}
    if len(question) > MAX_QUESTION_CHARS:
        question = question[:MAX_QUESTION_CHARS]
    try:
        top_k = max(1, min(int(top_k), MAX_TOP_K))
    except (TypeError, ValueError):
        top_k = 6
    who = _principal(principal, roles)
    cat = _catalog()
    sel = cat.select(question, top_k=top_k, principal=who,
                     expand_fks=bool(expand_foreign_keys),
                     pin=_memory().pins_for(question))
    visible = sum(1 for d in cat.objects() if cat._visible(d, who))
    withheld_cols = sum(len(h.doc.columns) - len(h.doc.visible_columns(who))
                        for h in sel.hits)
    return {
        "question": question,
        "selected": len(sel),
        "total_objects": sel.total_objects,
        "objects": sel.table_names,
        "ddl": sel.prompt_fragment(),
        "explain": [{"object": h.doc.qname, "score": round(h.score, 4),
                     "reason": h.reason} for h in sel.hits],
        # for the audit record only; stripped before the caller sees this
        "_visible_objects": visible,
        "_columns_withheld": withheld_cols,
    }


@_guard
def list_objects(principal: PrincipalArg = None,
                 roles: RolesArg = None) -> Dict[str, Any]:
    """Every object the caller may see, with kind and column count.

    Useful for an agent that wants to know what exists before asking.
    Restricted objects are absent for callers without the role.
    """
    who = _principal(principal, roles)
    cat = _catalog()
    visible = [d for d in cat._docs.values() if cat._visible(d, who)]
    return {
        "count": len(visible),
        "total_objects": len(cat._docs),
        "objects": [{"name": d.qname, "kind": d.kind,
                     "columns": len(d.columns),
                     "description": d.hint or d.description}
                    for d in visible],
    }


@_guard
def describe_object(name: ObjectName, principal: PrincipalArg = None,
                    roles: RolesArg = None) -> Dict[str, Any]:
    """Full DDL for one object, if the caller may see it."""
    who = _principal(principal, roles)
    cat = _catalog()
    name = str(name or "")
    reason = "missing"
    for qname, doc in cat._docs.items():
        if qname == name or doc.name == name:
            if not cat._visible(doc, who):
                reason = "restricted"
                break
            return {"name": doc.qname, "kind": doc.kind, "ddl": doc.render_ddl(),
                    "foreign_keys": [{"columns": fk.columns, "references": fk.ref_table}
                                     for fk in doc.foreign_keys]}
    # same message whether it is missing or restricted: no existence leak.
    # The audit record gets the distinction; `_guard` strips it from the reply.
    return {"error": f"no visible object named {name!r}", "_denied_reason": reason}


@_guard
def run_query(sql: SqlArg, principal: PrincipalArg = None,
              roles: RolesArg = None,
              max_rows: MaxRows = DEFAULT_ROWS) -> Dict[str, Any]:
    """Run one read-only SELECT and return the rows.

    This is the half that was missing. `select_schema` hands back the DDL and
    the client's own model writes the SQL -- and then there was nothing to
    execute it with, so the answer stopped at "here is the query you could
    run". No API key is involved: the model that wrote the SQL is the one
    already talking to you.

    Three things are checked before the database sees it. It must be a single
    statement; it must be a read (`check_read_only`, which refuses writes and
    anything hiding a second statement in a comment or a literal); and every
    table it names must be one this principal may see. That last check is why
    withholding a table from `select_schema` means something.
    """
    from .answer import UnsafeSQL, check_read_only, run_sql

    sql = str(sql or "").strip()
    if not sql:
        return {"error": "sql is empty"}
    if len(sql) > MAX_SQL_CHARS:
        return {"error": f"sql is too long ({len(sql)} chars; max {MAX_SQL_CHARS})"}
    try:
        max_rows = max(1, min(int(max_rows), MAX_ROWS))
    except (TypeError, ValueError):
        max_rows = DEFAULT_ROWS

    who = _principal(principal, roles)
    try:
        sql = check_read_only(sql)
    except UnsafeSQL as e:
        return {"error": f"refused: {e}", "sql": sql, "_refused_reason": "not-read-only"}

    cat = _catalog()
    denied = _check_scope(cat, sql, who)
    if denied:
        return {"error": denied, "sql": sql, "_refused_reason": "out-of-scope",
                "_tables": _referenced_tables(sql)}

    # One extra row, so "there are more" is a fact rather than a guess at the
    # boundary -- asking for 50 and getting 50 says nothing on its own.
    try:
        cols, rows = run_sql(_engine(), sql, limit=max_rows + 1)
    except Exception as e:                               # noqa: BLE001
        # Hand the database's own words back. The generic guard would say
        # "OperationalError", and the caller here is a model whose next move
        # is to fix the query -- "no such column: name" *is* the fix, and
        # withholding it only costs another round trip. Safe to return: the
        # scope check has already run, so this can only describe objects this
        # caller may see, in SQL it wrote itself.
        msg = str(getattr(e, "orig", e)).strip().splitlines()
        return {"error": "the database rejected this query: %s"
                         % (msg[0] if msg else type(e).__name__),
                "sql": sql}
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    return {
        "sql": sql,
        "columns": cols,
        "rows": [list(r) for r in rows],
        "row_count": len(rows),
        "truncated": truncated,
        "principal": who.subject if who else None,
        "_tables": _referenced_tables(sql),
    }


@_guard
def answer(question: Question, principal: PrincipalArg = None,
           roles: RolesArg = None, top_k: TopK = 6,
           max_rows: MaxRows = DEFAULT_ROWS) -> Dict[str, Any]:
    """Question in, rows out -- selection, SQL and execution in one call.

    Only useful when this server has its own model configured
    (`SCHEMAGATE_MCP_PROVIDER` and `SCHEMAGATE_MCP_MODEL`, key from the
    usual environment variable). Most MCP clients should not want it: the
    client *is* a model, and it will write better SQL from `select_schema`
    than a second one bolted on here. It exists for the agent that has no
    model of its own.

    With nothing configured this does not fail -- it returns the selection
    and says to write the SQL and call `run_query`, which is the same loop
    with one fewer model in it.
    """
    question = str(question or "").strip()
    if not question:
        return {"error": "question is empty"}
    picked = select_schema(question, principal=principal, roles=roles,
                           top_k=top_k)
    if "error" in picked:
        return picked

    name = os.environ.get("SCHEMAGATE_MCP_PROVIDER")
    model = os.environ.get("SCHEMAGATE_MCP_MODEL")
    if not name or not model:
        return dict(picked, sql=None, rows=None,
                    next="no model is configured on this server: write the "
                         "SELECT yourself from prompt_fragment, then call "
                         "run_query with it. Set SCHEMAGATE_MCP_PROVIDER and "
                         "SCHEMAGATE_MCP_MODEL to have the server write it.")

    from .ai import providers as _p
    from .answer import UnsafeSQL, generate_sql
    classes = {"anthropic": _p.AnthropicProvider, "openai": _p.OpenAIProvider,
               "gemini": _p.GeminiProvider, "oci": _p.OCIGenAIProvider,
               "local": _p.LocalProvider}
    cls = classes.get(name.lower())
    if cls is None:
        return dict(picked, error=f"unknown provider {name!r}")
    # `select_schema` returns the DDL under "ddl". This used to read
    # "prompt_fragment", a key nothing sets, so the model was handed an
    # empty table list and every answer was INSUFFICIENT or invented. The
    # only test of this tool covered the no-model path, which is how it
    # stayed that way.
    try:
        sql = generate_sql(cls(model=model), question, picked["ddl"],
                           dialect=_dialect_name(),
                           # only pairs whose every table this caller may see
                           examples=_memory().examples_for(
                               question, visible=picked["objects"]))
    except UnsafeSQL as e:
        return dict(picked, sql=None, rows=None, refused=str(e))

    out = run_query(sql, principal=principal, roles=roles, max_rows=max_rows)
    if "error" in out:
        return dict(picked, sql=sql, rows=None, error=out["error"])
    # It ran and returned: that is the evidence worth keeping. The row data
    # is not kept -- remember() stores the question and the query only.
    _memory().remember(question, sql, source="answer")
    return dict(picked, **out)


@_guard
def refresh_catalog() -> Dict[str, Any]:
    """Re-reflect the database and swap the index in, atomically.

    If the database is unreachable the previous index stays in service and
    the failure is reported here and in ``health`` -- the server never
    drops its last good catalog for a bad one.
    """
    global _CATALOG
    url = os.environ.get("SCHEMAGATE_DATABASE_URL")
    if not url:
        return {"error": "no SCHEMAGATE_DATABASE_URL; catalog was provided directly"}
    started = time.time()
    try:
        cat = _reflect(url, os.environ.get("SCHEMAGATE_CATALOG_CONFIG"))
    except Exception as e:                           # noqa: BLE001
        _STATE.update(last_refresh_ok=False,
                      last_error=f"refresh: {type(e).__name__}: {e}")
        log.exception("refresh failed; keeping previous catalog")
        return {"ok": False, "kept_previous": True,
                "error": f"{type(e).__name__}: {e}"}
    with _LOCK:
        _CATALOG = cat
        _STATE.update(last_refresh_at=time.time(), last_refresh_ok=True,
                      last_error=None)
        if _GROUPS is not None:
            _GROUPS.forget()        # a refresh is also "re-ask the directory"
    return {"ok": True, "objects": len(cat._docs),
            "seconds": round(time.time() - started, 2)}


@_guard
def health() -> Dict[str, Any]:
    """Liveness and readiness in one call, for people and load balancers."""
    cat = _CATALOG
    return {
        "status": "ok" if cat is not None else "starting",
        "version": __version__,
        "objects": len(cat._docs) if cat is not None else 0,
        "shadows": len(cat.shadows()) if cat is not None else 0,
        "uptime_seconds": round(time.time() - _STATE["started_at"], 1)
        if _STATE["started_at"] else 0,
        "database": _STATE["url"],
        "last_refresh_ok": _STATE["last_refresh_ok"],
        "last_error": _STATE["last_error"],
        "calls": _STATE["calls"],
        "errors": _STATE["errors"],
        # what the log holds, never what is in it
        "audit": _audit().describe(),
        # how much has been learned, never what
        "memory": _memory().describe(),
        # Counts and source kinds only -- no group names, no subjects.
        "groups": _GROUPS.describe() if _GROUPS is not None else None,
    }


# --- server wiring ---------------------------------------------------------

_INSTRUCTIONS = (
    "Schema selection and read-only query execution. Call select_schema with "
    "the user's question and, whenever you know it, their identity "
    "(principal like 'okta:jdoe' and roles). Write SQL only against the "
    "DDL returned; anything not returned is not available to this caller. "
    "Then call run_query with that SQL and the same principal and roles to "
    "get the rows -- it accepts one read-only SELECT, refuses writes, and "
    "refuses any table this caller may not see. Pass the identity to both: "
    "run_query scopes on what it is given, not on the earlier call.")


#: What an agent reads for each tool: purpose, when to call it, what comes back. The docstrings above are for
#: people reading the code; these are for the model choosing a tool.
TOOL_DESCRIPTIONS = {
    "select_schema": (
        "Start here for any question about the data. Returns the few tables and views the question needs, as "
        "compact DDL to write SQL against, scoped to the caller: objects and columns they may not read are "
        "absent, not ranked low. Also returns each object's name and why it was picked. Pass principal and "
        "roles whenever you know who is asking."),
    "list_objects": (
        "List every table and view this caller may read, with its kind and column count. Use it to see what "
        "exists before asking, or when select_schema did not return what you expected."),
    "describe_object": (
        "Full DDL (all visible columns, keys, comments) for one table or view, if the caller may read it. Use "
        "it when select_schema's compact DDL is not enough. A restricted or missing object returns the same "
        "'not available' error, so its existence is not revealed."),
    "run_query": (
        "Execute one read-only SELECT and return the rows (capped by max_rows). Write the SQL against the DDL "
        "select_schema returned for the same caller. Refuses writes, multiple statements, and any table or "
        "column the caller may not read, with an error that says so ('not available to this caller'), "
        "which you can pass on to the user instead of reporting 'no results'."),
    "answer": (
        "Question in, rows out: selects the schema, writes the SQL with the server's own configured model, "
        "and runs it, all scoped to the caller. Only available when the server has a model configured; most "
        "clients should use select_schema then run_query with their own model instead."),
    "refresh_catalog": (
        "Re-read the database structure (new tables, changed columns, changed grants) and swap the index in. "
        "If the database is unreachable the previous catalog stays in service and the failure is reported."),
    "health": (
        "Server status: whether the catalog is loaded, how many objects it holds, the database dialect, and "
        "audit-log counts. Takes no arguments; safe to call any time."),
}


def _server_class():
    """The high-level server class, whichever SDK major version is installed.

    The MCP Python SDK renamed ``FastMCP`` to ``MCPServer`` in 2.0 and moved
    it. Supporting both means ``pip install schemagate[mcp]`` works whether the
    resolver picks 1.x or 2.x, instead of breaking on a fresh install the
    week after a major release -- which is precisely what happened in the
    clean-environment check before this shim existed.
    """
    try:
        from mcp.server.mcpserver import MCPServer          # mcp >= 2.0
        return MCPServer
    except ImportError:
        pass
    try:
        from mcp.server.fastmcp import FastMCP              # mcp 1.x
        return FastMCP
    except ImportError as e:
        raise ImportError("pip install 'schemagate[mcp]' to run the MCP server") from e


def create_server(catalog: Optional[Catalog] = None):
    """Build the MCP app. Separate from ``main`` so tests can drive it."""
    if catalog is not None:
        build_catalog(catalog=catalog)
    kwargs: Dict[str, Any] = {"instructions": _INSTRUCTIONS}
    host = os.environ.get("SCHEMAGATE_MCP_HOST")
    port = os.environ.get("SCHEMAGATE_MCP_PORT")
    cls = _server_class()
    # 1.x takes host/port in the constructor; 2.x takes them in run()
    if cls.__name__ == "FastMCP":
        if host:
            kwargs["host"] = host
        if port:
            kwargs["port"] = int(port)
    # The version a client sees in `initialize` -> serverInfo. Left alone, the
    # SDK reports its *own* package version -- 1.27.0 -- or an empty string
    # in an image where that metadata does not resolve; either way never
    # schemagate's. 2.x takes it in the constructor; 1.x holds it on the
    # low-level server underneath, which is None until set.
    try:
        app = cls("schemagate", version=__version__, **kwargs)
    except TypeError:
        app = cls("schemagate", **kwargs)
        low = getattr(app, "_mcp_server", None)
        if low is not None and hasattr(low, "version"):
            low.version = __version__
    try:
        from mcp.types import ToolAnnotations
    except ImportError:                               # very old SDKs: descriptions only
        ToolAnnotations = None
    for tool in (select_schema, list_objects, describe_object,
                 run_query, answer, refresh_catalog, health):
        name = tool.__name__
        kw: Dict[str, Any] = {"description": TOOL_DESCRIPTIONS[name]}
        if ToolAnnotations is not None:
            # Every tool only reads. refresh_catalog changes the server's own index, never the database.
            kw["annotations"] = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                                idempotentHint=True, openWorldHint=False)
        try:
            app.tool(**kw)(tool)
        except TypeError:                             # an SDK without annotations=
            app.tool(description=kw["description"])(tool)
    return app


def main() -> None:
    logging.basicConfig(level=os.environ.get("SCHEMAGATE_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    build_catalog()
    app = create_server()
    transport = os.environ.get("SCHEMAGATE_MCP_TRANSPORT", "stdio")
    log.info("schemagate %s serving %d objects over %s", __version__,
             len(_catalog()._docs), transport)
    if transport == "stdio":
        app.run()
        return
    host = os.environ.get("SCHEMAGATE_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("SCHEMAGATE_MCP_PORT", "8765"))
    try:
        app.run(transport=transport, host=host, port=port)   # mcp 2.x
    except TypeError:
        app.run(transport=transport)                          # mcp 1.x


if __name__ == "__main__":
    main()
