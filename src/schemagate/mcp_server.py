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
is a network control rather than an identity one.

**Or let your identity provider decide.** Set ``SCHEMAGATE_MCP_OAUTH_ISSUER``
and ``SCHEMAGATE_MCP_OAUTH_AUDIENCE`` and the HTTP transport becomes an OAuth
resource server (``schemagate.oauth``): every request needs a token signed by
that provider, and ``principal`` and ``roles`` are taken from the token, never
from the client. That one is a lock.

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

import argparse
import functools
import inspect
import logging
import os
import re
import threading
import time
from typing import Annotated, Any, Callable, Dict, List, Literal, Optional

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
    # catalogue freshness (SCHEMAGATE_CATALOG_MAX_AGE), on the monotonic clock
    "max_age": None, "read_at_mono": None, "last_attempt_mono": None,
    "reread_timeout": None,
}

#: The clock catalogue age is measured on. Monotonic, so a wall-clock change
#: cannot make a stale catalogue look fresh; tests replace it.
_clock: Callable[[], float] = time.monotonic
#: Only one call re-reads an expired catalogue; the others join that re-read.
#: The lock guards the bookkeeping, never the re-read itself.
_REFRESH_LOCK = threading.Lock()
#: The re-read in flight, if any: {"done": Event, "ok": bool}. It runs on its
#: own thread so that a caller's wait for it can be bounded.
_REREAD_JOB: Dict[str, Any] = {"job": None}
#: A failed automatic re-read is retried at most this often, so a database
#: outage is not answered with a reflection storm. Calls in between are
#: refused straight away.
STALE_RETRY_SECONDS = 5.0
#: How long a call waits for the re-read of an expired catalogue before it is
#: refused as stale. A database that accepts the connection and never answers
#: must not hold every caller open with it: past this, callers are refused and
#: the re-read keeps running; if it does return, the catalogue it brings is
#: served from then on. SCHEMAGATE_REREAD_TIMEOUT overrides it.
REREAD_TIMEOUT = 30.0


class StaleCatalogError(Exception):
    """The catalogue is older than ``SCHEMAGATE_CATALOG_MAX_AGE`` and re-reading
    it failed. Every scoping tool refuses until a re-read succeeds: answering
    from permissions that may since have been revoked is the failure this
    setting exists to bound."""


def _max_age() -> Optional[float]:
    """``SCHEMAGATE_CATALOG_MAX_AGE`` in seconds, or None when unset.

    Read at startup and validated there: a typo must stop the server rather
    than leave it running with no bound the operator believes is in place."""
    raw = (os.environ.get("SCHEMAGATE_CATALOG_MAX_AGE") or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        raise SystemExit(f"SCHEMAGATE_CATALOG_MAX_AGE must be a number of seconds, got {raw!r}") from None
    if not value > 0 or value == float("inf"):
        raise SystemExit(f"SCHEMAGATE_CATALOG_MAX_AGE must be a positive number of seconds, got {raw!r}")
    return value


def _reread_timeout() -> float:
    """``SCHEMAGATE_REREAD_TIMEOUT`` in seconds, default `REREAD_TIMEOUT`.
    Validated at startup for the same reason as the max age."""
    raw = (os.environ.get("SCHEMAGATE_REREAD_TIMEOUT") or "").strip()
    if not raw:
        return REREAD_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        raise SystemExit(f"SCHEMAGATE_REREAD_TIMEOUT must be a number of seconds, got {raw!r}") from None
    if not value > 0 or value == float("inf"):
        raise SystemExit(f"SCHEMAGATE_REREAD_TIMEOUT must be a positive number of seconds, got {raw!r}")
    return value


def _truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


#: Rerank candidates: the maths shortlists this many, the model picks top_k
#: from them. Measured at 20 (BENCHMARKS.md, "The reranker, measured").
RERANK_CANDIDATES = 20


def _server_provider():
    """The model this server is configured with, or None.

    ``SCHEMAGATE_MCP_PROVIDER`` and ``SCHEMAGATE_MCP_MODEL``, the key from the
    provider's usual environment variable. Shared by `answer` (to write SQL)
    and, with ``SCHEMAGATE_MCP_RERANK``, `select_schema` (to reorder the
    shortlist), so the two can never be configured differently by accident.
    Raises ValueError for a provider name it does not know.
    """
    name = os.environ.get("SCHEMAGATE_MCP_PROVIDER")
    model = os.environ.get("SCHEMAGATE_MCP_MODEL")
    if not name or not model:
        return None
    from .ai import providers as _p
    classes = {"anthropic": _p.AnthropicProvider, "openai": _p.OpenAIProvider,
               "gemini": _p.GeminiProvider, "oci": _p.OCIGenAIProvider,
               "local": _p.LocalProvider}
    cls = classes.get(name.lower())
    if cls is None:
        raise ValueError(f"unknown provider {name!r}")
    return cls(model=model)


def _semantic_check() -> bool:
    """Whether `semantic_query` is on. Off by default because it sends the text of result rows to
    the configured model provider; ``SCHEMAGATE_MCP_SEMANTIC=1`` without a model stops the server."""
    if not _truthy("SCHEMAGATE_MCP_SEMANTIC"):
        return False
    try:
        if _server_provider() is None:
            raise ValueError("SCHEMAGATE_MCP_PROVIDER and SCHEMAGATE_MCP_MODEL are not both set")
    except ValueError as e:
        raise SystemExit(f"schemagate.mcp_server: SCHEMAGATE_MCP_SEMANTIC=1 needs a model: {e}")
    return True


def _deep_check() -> bool:
    """Whether `deep_answer` is on. Off by default for the same reason as `semantic_query`: its
    exploring queries send rows to the model provider. ``SCHEMAGATE_MCP_DEEP=1`` without a model
    stops the server."""
    if not _truthy("SCHEMAGATE_MCP_DEEP"):
        return False
    try:
        if _server_provider() is None:
            raise ValueError("SCHEMAGATE_MCP_PROVIDER and SCHEMAGATE_MCP_MODEL are not both set")
    except ValueError as e:
        raise SystemExit(f"schemagate.mcp_server: SCHEMAGATE_MCP_DEEP=1 needs a model: {e}")
    return True


def _rerank_check() -> bool:
    """Whether `select_schema` reranks. Read at startup and validated there:
    ``SCHEMAGATE_MCP_RERANK=1`` without a usable model stops the server rather
    than quietly selecting without the reranker someone asked for."""
    if not _truthy("SCHEMAGATE_MCP_RERANK"):
        return False
    try:
        if _server_provider() is None:
            raise ValueError("SCHEMAGATE_MCP_PROVIDER and SCHEMAGATE_MCP_MODEL are not both set")
    except ValueError as e:
        raise SystemExit(f"schemagate.mcp_server: SCHEMAGATE_MCP_RERANK=1 needs a model: {e}")
    return True

#: Hard caps so one pathological request cannot stall the server.
MAX_QUESTION_CHARS = 2000
MAX_TOP_K = 50
MAX_ROLES = 100
#: Rows a single `run_query` may return. A model asking for a whole table
#: should get a page of it and be told there is more, not fill the context.
MAX_ROWS = 200
DEFAULT_ROWS = 50
#: Model calls one deep_answer may make.
MAX_DEEP_STEPS = 12
#: deep_answer's exploring reads, kept five minutes per caller and catalogue version.
from .deep import ExploreCache as _ExploreCache                            # noqa: E402
_EXPLORE_CACHE = _ExploreCache(ttl=float(os.environ.get("SCHEMAGATE_DEEP_CACHE_SECONDS", "300")))
#: A statement time limit run_query applies when one is set here -- deep_answer sets it for its
#: exploring reads only, so a slow look at the data cannot hold a question for minutes. Unset
#: (None) for every other call, which is every call a client makes directly.
import contextvars as _contextvars                                         # noqa: E402
_QUERY_TIMEOUT: "_contextvars.ContextVar[Optional[float]]" = _contextvars.ContextVar(
    "schemagate_query_timeout", default=None)
EXPLORE_SECONDS = float(os.environ.get("SCHEMAGATE_DEEP_EXPLORE_SECONDS", "10"))
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
    if url != "demo" and _truthy("SCHEMAGATE_RESTRICT_FROM_GRANTS"):
        # After the config, as in the CLI: the database's own grants are the
        # source of truth for who may see an object, and a hand-written file
        # must not quietly re-open something the database has revoked. Then
        # row-level policies, the half the grants cannot see.
        from .introspect import engine_from_url
        from .grants import restrict_from_grants
        from .rls import restrict_from_policies
        engine = engine_from_url(url, pool_pre_ping=True)
        try:
            log.info("%s", restrict_from_grants(cat, engine, report=True))
            log.info("%s", restrict_from_policies(cat, engine, report=True))
        finally:
            engine.dispose()
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
                          last_refresh_ok=True, last_error=None,
                          read_at_mono=_clock(), last_attempt_mono=None)
            return catalog

        url = url or os.environ.get("SCHEMAGATE_DATABASE_URL")
        if not url:
            raise SystemExit(
                "schemagate.mcp_server: set SCHEMAGATE_DATABASE_URL to a SQLAlchemy URL, "
                "or use SCHEMAGATE_DATABASE_URL=demo for the bundled schema")
        config_path = config_path or os.environ.get("SCHEMAGATE_CATALOG_CONFIG")
        max_age = _max_age()                 # validated before any database work
        reread_timeout = _reread_timeout()   # likewise
        _STATE["rerank"] = _rerank_check()   # likewise
        _STATE["semantic"] = _semantic_check()
        _STATE["deep"] = _deep_check()
        cat = _reflect(url, config_path)
        _CATALOG = cat
        _GROUPS = _groups_from(config_path, url)
        _MEMORY = Memory.from_env(cat.embedder, _memory_label(url))
        globals()["_URL"] = cat._demo_url if url == "demo" else url
        globals()["_ENGINE"] = None
        _STATE.update(url=_redact(url), config=config_path,
                      last_refresh_at=time.time(), last_refresh_ok=True,
                      last_error=None, max_age=max_age, reread_timeout=reread_timeout,
                      read_at_mono=_clock(), last_attempt_mono=None)
        if max_age:
            log.info("catalogue max age %.0f s: an older catalogue is re-read before use, "
                     "and if that fails or takes more than %.0f s the scoping tools refuse",
                     max_age, reread_timeout)
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
#: `WITH name AS (`, and the `, name AS (` that follow it; also `WITH RECURSIVE name AS (` and a CTE with a
#: column list, `name(a, b) AS (`. Without those two forms the CTE's name read as a table the caller may not
#: see, and every recursive query was refused.
_CTE = re.compile(r"(?:\bwith\b(?:\s+recursive\b)?|,)\s*(" + _PART + r")\s*(?:\([^()]*\))?\s+as\s*\(", re.I)


def _unquote(part: str) -> str:
    return part.strip()[1:-1] if part.strip()[:1] in ('"', "[", "`") else part.strip()


def _sql_body(sql: str) -> str:
    """The statement with comments removed and string literals emptied."""
    body = re.sub(r"--[^\n]*", " ", sql)
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    return re.sub(r"'(?:[^']|'')*'", "''", body)


#: A single-quoted string. Emptied before table names are read, except where
#: SQLite reads it as a table name (see `_table_body`).
_STRING = re.compile(r"'(?:[^']|'')*'")
#: what may precede a table name: FROM / JOIN, a comma in a FROM list, or the
#: dot of a schema-qualified name
_TABLE_BEFORE = re.compile(r"(?:\b(?:from|join)|,|\.)\s*$", re.I)


def _table_body(sql: str) -> str:
    """The statement with comments removed, for reading table names.

    SQLite takes a single-quoted string as an identifier where only an
    identifier fits: `FROM 'payroll'`, `JOIN 'payroll'`, `main.'payroll'` all
    read the table. Emptied like any other literal, such a name was invisible
    to the scope check and the table it named was read without a check. A
    string in a table position is therefore read as the name it is; every
    other string is still emptied. The other dialects reject the syntax, so
    reading it as a name there only refuses what would have failed anyway.
    """
    body = re.sub(r"--[^\n]*", " ", sql)
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)

    def one(m: "re.Match[str]") -> str:
        before, after = body[:m.start()], body[m.end():]
        if _TABLE_BEFORE.search(before) or after.lstrip().startswith("."):
            return '"' + m.group(0)[1:-1].replace("''", "'").replace('"', "") + '"'
        return "''"
    return _STRING.sub(one, body)


def _referenced_tables(sql: str) -> List[str]:
    """Base tables the statement reads, with CTE and subquery aliases removed."""
    body = _table_body(sql)
    ctes = {_unquote(c).lower() for c in _CTE.findall(body)}
    out, seen = [], set()
    for clause in _REFERENCED.findall(body):
        # Case-insensitive like _REFERENCED: matched case-sensitively, `students AS T1`
        # read `AS` as the alias and `T1` as a second table, and refused the query.
        for item in re.findall(_ITEM, clause, re.I):
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


#: SQLAlchemy dialect name -> sqlglot's.
_SQLGLOT_DIALECT = {"postgresql": "postgres", "mssql": "tsql", "mysql": "mysql",
                    "mariadb": "mysql", "oracle": "oracle", "sqlite": "sqlite"}


class _Unparsed(Exception):
    """sqlglot could not read the statement."""


def _parsed_refs(sql: str):
    """(tables, columns, star) as a real SQL parser reads ``sql``, or None without sqlglot.

    The pattern-based readers above found three bypasses in a week, each a
    dialect's own way of writing a name (a schema-qualified twin, a shadowed
    column, SQLite's single-quoted table). A parser that knows each dialect's
    grammar reads those as what they are. Its findings are *added* to the
    pattern readers' -- a statement is refused if either sees a name this
    caller may not use -- so this can only make the check stricter. Raises
    `_Unparsed` when the statement cannot be parsed: fail closed.
    """
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:
        return None
    try:
        trees = [t for t in sqlglot.parse(sql, read=_SQLGLOT_DIALECT.get(_dialect_name()))
                 if t is not None]
    except Exception as e:                               # noqa: BLE001 -- any parse failure
        raise _Unparsed(str(e).splitlines()[0][:160] if str(e) else type(e).__name__) from e
    tables: List[str] = []
    seen = set()
    cols, star = set(), False
    for t in trees:
        ctes = {(c.alias_or_name or "").lower() for c in t.find_all(exp.CTE)}
        for x in t.find_all(exp.Table):
            if not x.name:
                continue
            if not (x.db or x.catalog) and x.name.lower() in ctes:
                continue
            name = ".".join(part for part in (x.catalog, x.db, x.name) if part)
            if name.lower() not in seen:
                seen.add(name.lower())
                tables.append(name)
        cols |= {c.name.lower() for c in t.find_all(exp.Column) if c.name and c.name != "*"}
        star = star or any(not isinstance(st.parent, exp.Count) for st in t.find_all(exp.Star))
    return tables, cols, star


#: words before a bracket that make it a list or a group, not a function call
_NOT_A_CALL = {"in", "values", "and", "or", "not", "select", "where", "on", "exists", "any", "all", "some",
               "as", "from", "join", "when", "then", "else", "case", "by", "having", "over"}


def _calling(masked: str, pos: int) -> Optional[str]:
    """The function whose argument list holds position ``pos``, or None.

    ``masked`` is the statement with string literals blanked, so the brackets
    counted are the statement's own. Walks back to the innermost unclosed `(`
    and reads the name in front of it: `run_sql(` is a call; `IN (`, `VALUES (`
    and a bare `(` are not.
    """
    depth = 0
    for i in range(pos - 1, -1, -1):
        ch = masked[i]
        if ch == ")":
            depth += 1
        elif ch == "(":
            if depth == 0:
                name = re.search(r"([A-Za-z_][\w$#]*(?:\s*\.\s*[A-Za-z_][\w$#]*)*)\s*$", masked[:i])
                if not name or name.group(1).lower() in _NOT_A_CALL:
                    return None
                return name.group(1).lower()
            depth -= 1
    return None


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
    # Every name is matched case-insensitively. Where that folds a hidden and
    # a visible object together -- the same table name in two schemas, or two
    # quoted names that differ only in case -- the reference is refused: the
    # database may resolve it to the hidden one, so the safe answer is no.
    vis_q, vis_bare, hid_q, hid_bare = {}, {}, set(), set()
    for doc in cat.objects():
        q, b = doc.qname.lower(), (doc.name or "").lower()
        if cat._visible(doc, who):
            vis_q[q] = doc
            vis_bare.setdefault(b, []).append(doc)
        else:
            hid_q.add(q)
            hid_bare.add(b)

    def resolve(ref: str) -> List[Any]:
        """The visible objects ``ref`` can only mean, or [] if it may name a
        hidden one. A qualified name must match a visible object exactly
        (``db.schema.table`` is tried as ``schema.table`` too); it never
        falls back to its bare table name, which may be another schema's."""
        r = ref.lower()
        if "." in r:
            parts = r.split(".")
            for cand in (r, ".".join(parts[-2:])):
                if cand in vis_q and cand not in hid_q:
                    return [vis_q[cand]]
            return []
        if r in hid_bare:
            return []
        return vis_bare.get(r, [])

    try:
        parsed = _parsed_refs(sql)
    except _Unparsed as e:
        return ("not available to this caller: the statement could not be parsed to check "
                "which tables and columns it reads (%s). Write it as a plain SELECT." % e)
    refs = _referenced_tables(sql)
    if parsed:
        known = {r.lower() for r in refs}
        refs += [t for t in parsed[0] if t.lower() not in known]
    resolved = {t: resolve(t) for t in refs}
    unknown = [t for t in refs if not resolved[t]]
    # Backstop, whatever the syntax: a name this caller may not see, anywhere
    # in the statement, is refused -- a FROM-list form the parser does not
    # know, a LATERAL, a dialect's own table function. A hidden table whose
    # name is also a visible object's name is left to the check above.
    idents = _identifiers(sql)
    if parsed:
        idents |= parsed[1]
    visible_names = set(vis_q) | set(vis_bare)
    unknown += sorted(n for n in (idents & (hid_q | hid_bare)) - visible_names
                      if n not in {u.lower() for u in unknown})
    # A string the database may run as SQL. `check_read_only` refuses the known
    # functions that do (query_to_xml, DBMS_XMLGEN, ...), but a list of names
    # is never complete: an extension or a user-defined function can execute
    # its text argument too. So a string that is itself a query naming a hidden
    # table, or is exactly a hidden table's name handed to a function, is
    # refused here whatever the function is (GHSA-r77g-5v43-wh54).
    hidden_only = (hid_q | hid_bare) - visible_names
    if hidden_only:
        body = re.sub(r"--[^\n]*", " ", sql)
        body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
        # the same text with every literal blanked to spaces, so brackets inside strings do not count
        masked = _STRING.sub(lambda m: " " * len(m.group(0)), body)
        for m in _STRING.finditer(body):
            # Only a string handed to a function can be run: `SELECT 'from secret' AS label` is a
            # label and `x IN ('a', 'secret')` a list.
            if _calling(masked, m.start()) is None:
                continue
            text = m.group(0)[1:-1].replace("''", "'")
            names = {".".join(_unquote(p).lower() for p in re.findall(_PART, r))
                     for r in re.findall(_REF, text)}
            names |= {_unquote(p).lower() for p in re.findall(_PART, text)}
            as_query = re.search(r"\b(?:select|from|join|table|with|values)\b", text, re.I)
            as_name = ".".join(_unquote(p).lower() for p in re.findall(_PART, text.strip())) in hidden_only
            hit = sorted(names & hidden_only) if as_query else []
            if as_name:
                hit = hit or [text.strip().lower()]
            unknown += [n for n in hit if n not in {u.lower() for u in unknown}]
    if unknown:
        # A bare name refused only because it is ambiguous can still be used
        # qualified. Say so by naming the visible objects it could mean --
        # never the hidden one, nor that one exists. Where qualifying would
        # not help either (names that differ only in case), give no hint.
        usable = sorted({d.qname for t in unknown if "." not in t
                         for d in vis_bare.get(t.lower(), []) if d.qname.lower() not in hid_q})
        hint = (" Use the qualified name select_schema returns: %s." % ", ".join(usable)) if usable else ""
        return ("not available to this caller: %s.%s Call select_schema and use "
                "only the objects it returns." % (", ".join(sorted(set(unknown))), hint))
    # Column rules. A table the caller may read can still hold a column it
    # may not: `SELECT *` would return it, and so would naming it.
    used = [d for t in refs for d in resolved[t]]
    # Per table, not across them: a column withheld on one table stays
    # withheld when another referenced table happens to have a visible column
    # of the same name (`SELECT b.salary FROM b CROSS JOIN a`). Fails closed:
    # naming it at all is refused while any referenced table withholds it.
    withheld = set()
    for d in used:
        vis = {c.name.lower() for c in d.visible_columns(who)}
        withheld |= {c.name.lower() for c in d.columns} - vis
    if withheld:
        named = sorted(idents & withheld)
        if named:
            return ("not available to this caller: column %s. Call select_schema and "
                    "use only the columns it returns." % ", ".join(named))
        if _STAR.search(_sql_body(sql)) or (parsed and parsed[2]):
            return ("not available to this caller: SELECT * would include columns this "
                    "caller may not see. Name the columns select_schema returned.")
    return None


def _catalog() -> Catalog:
    if _CATALOG is None:
        build_catalog()
    _ensure_fresh()
    return _CATALOG  # type: ignore[return-value]


def _catalog_age() -> Optional[float]:
    read = _STATE.get("read_at_mono")
    return None if read is None else max(0.0, _clock() - read)


def _ensure_fresh() -> None:
    """Re-read an expired catalogue before it is used; refuse if that fails.

    Only with ``SCHEMAGATE_CATALOG_MAX_AGE`` set and a database to re-read (a
    catalogue handed in directly has none). One re-read runs at a time, on its
    own thread; every caller that finds the catalogue expired joins it and
    waits at most `REREAD_TIMEOUT` seconds. A re-read that fails, or has not
    answered by then, refuses the caller with `StaleCatalogError`: nobody is
    answered from the expired catalogue, and nobody is held open by a database
    that took the connection and went quiet. A re-read that returns late still
    publishes its catalogue, and the next call is served from it. A failed
    re-read is retried at most every `STALE_RETRY_SECONDS`. The refusal never
    carries the database's own error text, which can name hosts and users;
    that goes to the log and to `health`.
    """
    max_age = _STATE.get("max_age")
    if not max_age or _STATE.get("url") in (None, "<provided>"):
        return
    age = _catalog_age()
    if age is not None and age <= max_age:
        return
    job = _join_reread()
    if job is not None:
        timeout = _STATE.get("reread_timeout") or REREAD_TIMEOUT
        if not job["done"].wait(timeout):
            _STATE.update(last_refresh_ok=False,
                          last_error=f"refresh: no answer from the database after {timeout:.0f} s; "
                                     "the re-read is still running")
            log.warning("catalogue re-read has taken more than %.0f s; refusing calls until it returns",
                        timeout)
        elif job["ok"]:
            return
    age = _catalog_age() or 0.0
    raise StaleCatalogError(
        f"permissions are stale: the catalogue was read {age:.0f} s ago, the limit "
        f"(SCHEMAGATE_CATALOG_MAX_AGE) is {max_age:.0f} s, and re-reading the database "
        "failed. Refusing until a re-read succeeds; the operator can see why in health "
        "and the server log.")


def _join_reread() -> Optional[Dict[str, Any]]:
    """The re-read in flight, starting one if none is and the retry pacing
    allows. None means a recent attempt failed and it is too soon to try again."""
    with _REFRESH_LOCK:
        job = _REREAD_JOB.get("job")
        if job is not None and not job["done"].is_set():
            return job                                   # join the one already running
        last = _STATE.get("last_attempt_mono")
        if last is not None and _clock() - last < STALE_RETRY_SECONDS:
            return None
        _STATE["last_attempt_mono"] = _clock()
        job = {"done": threading.Event(), "ok": False}
        _REREAD_JOB["job"] = job
        threading.Thread(target=_run_reread, args=(job,), daemon=True,
                         name="schemagate-reread").start()
        return job


def _run_reread(job: Dict[str, Any]) -> None:
    try:
        job["ok"] = bool(_reread().get("ok"))
    except Exception:                                    # noqa: BLE001  _reread reports its own failures
        log.exception("catalogue re-read thread failed")
    finally:
        job["done"].set()


def _reread_in_flight() -> bool:
    job = _REREAD_JOB.get("job")
    return job is not None and not job["done"].is_set()


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
        except StaleCatalogError as e:
            _STATE["errors"] += 1
            result = {"error": str(e), "_denied_reason": "stale catalogue"}
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
TextColumn = Annotated[str, Field(description=(
    "The result column whose text the model reads, e.g. 'body' or 'complaint_text'. Must be one of "
    "the columns the SQL returns."))]
Criterion = Annotated[Optional[str], Field(description=(
    "Keep only rows whose text meets this, in plain language, e.g. 'asks for a refund'. Give this "
    "or extract, not both."))]
Extract = Annotated[Optional[str], Field(description=(
    "Add one short answer per row, e.g. 'which product is mentioned'. Give this or criterion, not "
    "both."))]
MaxRows = Annotated[int, Field(description=(
    "Most rows to return (default 50, at most 200). The result says when it was truncated."), ge=1, le=200)]
DeepMode = Annotated[Literal["adaptive", "deep"], Field(description=(
    "'adaptive' (default): one plain query first, and the step-by-step path only when that one fails, "
    "comes back empty or is all zero -- most questions cost one model call. 'deep': always work in steps."))]
MaxSteps = Annotated[int, Field(description=(
    "Most model calls for this question (default 6, at most 12). Each exploring query, request for "
    "more tables, repair and final query is one; a plain question uses one."), ge=1, le=12)]

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
    # The model only reorders a shortlist of what this caller may already
    # see, and a reply it cannot parse leaves the maths order: reranking can
    # neither surface a withheld object nor fail the call.
    reranker = _server_provider() if _STATE.get("rerank") else None
    sel = cat.select(question, top_k=top_k, principal=who,
                     expand_fks=bool(expand_foreign_keys),
                     pin=_memory().pins_for(question),
                     reranker=reranker, rerank_candidates=RERANK_CANDIDATES)
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
        cols, rows = run_sql(_engine(), sql, limit=max_rows + 1, timeout=_QUERY_TIMEOUT.get())
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
def semantic_query(sql: SqlArg, column: TextColumn, criterion: Criterion = None,
                   extract: Extract = None, principal: PrincipalArg = None,
                   roles: RolesArg = None, max_rows: MaxRows = DEFAULT_ROWS) -> Dict[str, Any]:
    """Run a query, then ask the server's model about a text column of its rows.

    For questions SQL cannot answer from structure alone -- "which complaints are about a refund"
    when no column says so. Give exactly one of ``criterion`` (keep the rows whose text meets it)
    or ``extract`` (add a short answer per row). The query goes through `run_query` first, scope
    check included, so the model only ever sees rows this caller may read. Off unless the server
    runs with ``SCHEMAGATE_MCP_SEMANTIC=1``: it sends the text of those rows to the model provider.
    """
    from . import semantic as S

    if not _STATE.get("semantic"):
        return {"error": "semantic_query is off on this server: it sends row text to the model "
                         "provider, so it needs SCHEMAGATE_MCP_SEMANTIC=1 and a configured model"}
    if bool((criterion or "").strip()) == bool((extract or "").strip()):
        return {"error": "give exactly one of criterion (filter rows) or extract (one answer per row)"}
    try:
        cap = max(1, min(int(max_rows), S.MAX_ROWS))
    except (TypeError, ValueError):
        cap = DEFAULT_ROWS
    out = run_query(sql, principal=principal, roles=roles, max_rows=cap)
    if "error" in out:
        return out
    provider = _server_provider()
    try:
        if criterion and criterion.strip():
            res = S.semantic_filter(provider, out["columns"], out["rows"], column, criterion, max_rows=cap)
        else:
            res = S.semantic_extract(provider, out["columns"], out["rows"], column, extract, max_rows=cap)
    except S.SemanticError as e:
        return {"error": str(e), "sql": out["sql"]}
    return {
        "sql": out["sql"],
        "columns": res.columns,
        "rows": res.rows,
        "row_count": len(res.rows),
        "judged": res.judged,
        "query_truncated": out["truncated"],
        "notes": res.notes,
        "sent_to_model": f"the text of column {column!r} from {res.judged} rows",
        "principal": out["principal"],
        # run_query's wrapper strips its own private keys; recompute for this call's audit record
        "_tables": _referenced_tables(out["sql"]),
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

    try:
        provider = _server_provider()
    except ValueError as e:
        return dict(picked, error=str(e))
    if provider is None:
        return dict(picked, sql=None, rows=None,
                    next="no model is configured on this server: write the "
                         "SELECT yourself from prompt_fragment, then call "
                         "run_query with it. Set SCHEMAGATE_MCP_PROVIDER and "
                         "SCHEMAGATE_MCP_MODEL to have the server write it.")

    from .answer import UnsafeSQL, generate_sql
    # `select_schema` returns the DDL under "ddl". This used to read
    # "prompt_fragment", a key nothing sets, so the model was handed an
    # empty table list and every answer was INSUFFICIENT or invented. The
    # only test of this tool covered the no-model path, which is how it
    # stayed that way.
    try:
        sql = generate_sql(provider, question, picked["ddl"],
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
def deep_answer(question: Question, principal: PrincipalArg = None,
                roles: RolesArg = None, top_k: TopK = 6,
                max_rows: MaxRows = DEFAULT_ROWS,
                max_steps: MaxSteps = 6,
                mode: DeepMode = "adaptive") -> Dict[str, Any]:
    """`answer`, in steps: look at the data, ask for more tables, fix a rejected query, then answer.

    Every step's SQL goes through `run_query` -- read-only check, scope check
    and audit record each time -- and a TABLES step only ever adds objects this
    caller may see. Returns the answer with the trace of how it got there.
    Off unless the server runs with ``SCHEMAGATE_MCP_DEEP=1``: the rows an
    exploring query returns are sent to the model provider.
    """
    from . import deep as D

    if not _STATE.get("deep"):
        return {"error": "deep_answer is off on this server: its exploring queries send rows to the "
                         "model provider, so it needs SCHEMAGATE_MCP_DEEP=1 and a configured model"}
    question = str(question or "").strip()
    if not question:
        return {"error": "question is empty"}
    picked = select_schema(question, principal=principal, roles=roles, top_k=top_k)
    if "error" in picked:
        return picked
    try:
        max_rows = max(1, min(int(max_rows), MAX_ROWS))
    except (TypeError, ValueError):
        max_rows = DEFAULT_ROWS
    try:
        max_steps = max(1, min(int(max_steps), MAX_DEEP_STEPS))
    except (TypeError, ValueError):
        max_steps = 6

    who = _principal(principal, roles)
    cat = _catalog()
    shown = list(picked["objects"])

    def more_tables(topic: str) -> str:
        # the same scoped selection as select_schema, so nothing withheld can be added
        sel = cat.select(f"{question} {topic}"[:MAX_QUESTION_CHARS], top_k=max(1, min(int(top_k), MAX_TOP_K)),
                         principal=who, expand_fks=True)
        new = [d for d in sel.objects if d.qname not in shown]
        shown.extend(d.qname for d in new)
        return "\n\n".join(d.render_ddl(40, principal=who, question=topic) for d in new)

    def run(sql: str, limit: int) -> Dict[str, Any]:
        token = _QUERY_TIMEOUT.set(EXPLORE_SECONDS if D.EXPLORING.get() else None)
        try:
            out = run_query(sql, principal=principal, roles=roles, max_rows=limit)
        finally:
            _QUERY_TIMEOUT.reset(token)
        return {k: v for k, v in out.items() if not k.startswith("_")}

    # Exploring reads are cached per caller and per catalogue version: who asks, with which roles,
    # against which reflection. A refresh or a different caller never sees another's entry.
    scope = (who.subject if who else None, tuple(sorted(getattr(who, "roles", None) or ())),
             id(cat), _STATE.get("last_refresh_at"))
    run = _EXPLORE_CACHE.wrap(run, scope)
    answer_fn = D.deep_answer if mode == "deep" else D.adaptive_answer
    res = answer_fn(_server_provider(), question, picked["ddl"], run, more_tables,
                    dialect=_dialect_name(), max_steps=max_steps, max_rows=max_rows)
    if res.sql:
        # as in `answer`: the question and the query, never the rows
        _memory().remember(question, res.sql, source="deep_answer")
    explored = sum(1 for s in res.steps if s["kind"] == "explore" and s.get("outcome", "").endswith("seen"))
    return dict(res.to_dict(), objects=shown,
                principal=who.subject if who else None,
                sent_to_model=("schema only" if not explored else
                               f"schema, and up to {D.PREVIEW_ROWS} rows from each of {explored} "
                               "exploring queries"),
                _tables=_referenced_tables(res.sql) if res.sql else [])


@_guard
def refresh_catalog() -> Dict[str, Any]:
    """Re-reflect the database and swap the index in, atomically.

    If the database is unreachable the previous index stays in service and
    the failure is reported here and in ``health`` -- the server never
    drops its last good catalog for a bad one.
    """
    if not os.environ.get("SCHEMAGATE_DATABASE_URL"):
        return {"error": "no SCHEMAGATE_DATABASE_URL; catalog was provided directly"}
    return _reread()


def _reread() -> Dict[str, Any]:
    """Re-reflect and swap the catalogue in. Shared by `refresh_catalog` and the
    automatic re-read of an expired catalogue. A failure keeps the previous
    catalogue in memory, but with a max age set `_ensure_fresh` will not serve
    it past that age."""
    global _CATALOG
    url = os.environ.get("SCHEMAGATE_DATABASE_URL")
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
                      last_error=None, read_at_mono=_clock(), last_attempt_mono=None)
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
        "catalog_age_seconds": None if _catalog_age() is None else round(_catalog_age(), 1),
        "catalog_max_age_seconds": _STATE.get("max_age"),
        "catalog_reread_timeout_seconds": _STATE.get("reread_timeout"),
        "reread_in_flight": _reread_in_flight(),
        "rerank": bool(_STATE.get("rerank")),
        "semantic": bool(_STATE.get("semantic")),
        "deep": bool(_STATE.get("deep")),
        # where identity comes from: "oauth" (a verified token), "none" (HTTP, client-asserted), "stdio"
        "auth": _STATE.get("auth"),
        "catalog_stale": bool(_STATE.get("max_age") and (_catalog_age() or 0) > _STATE["max_age"]),
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
        "absent, not ranked low. Pass principal and roles whenever you know who is asking. Returns 'ddl' (put "
        "it in your SQL prompt), 'objects' (the names chosen), 'explain' (score and reason per object) and "
        "'selected' / 'total_objects'. Reads table structure only, never rows. Next: write one SELECT against "
        "'ddl' and call run_query with the same principal and roles; call describe_object if a table needs "
        "more columns than the compact DDL shows. If the right table is missing, raise top_k or rephrase "
        "rather than writing SQL against a table that was not returned."),
    "list_objects": (
        "List every table and view this caller may read: 'objects' holds each one's name, kind (table or "
        "view), column count and description, with 'count' visible out of 'total_objects'. Use it to show "
        "what data exists, or when select_schema did not return what you expected. It returns no DDL and no "
        "rows, and on a large database it is long: to answer a question, call select_schema instead. Pass "
        "principal and roles; restricted objects are absent for callers without the role."),
    "describe_object": (
        "Full DDL (all visible columns, keys, comments) for one table or view, if the caller may read it. Use "
        "it when select_schema's compact DDL is not enough. A restricted or missing object returns the same "
        "'not available' error, so its existence is not revealed."),
    "run_query": (
        "Execute one read-only SELECT and return the rows (capped by max_rows). Write the SQL against the DDL "
        "select_schema returned for the same caller. Refuses writes, multiple statements, and any table or "
        "column the caller may not read, with an error that says so ('not available to this caller'), "
        "which you can pass on to the user instead of reporting 'no results'."),
    "semantic_query": (
        "For questions about what text says when no column records it, e.g. 'which complaints ask "
        "for a refund'. Runs one read-only SELECT through the same checks as run_query, then has the "
        "server's model read one text column of the returned rows and either keep the rows that meet "
        "a criterion or add a short answer per row. Returns columns, rows, how many rows were judged, "
        "and which text was sent to the model. Off unless the server enables it "
        "(SCHEMAGATE_MCP_SEMANTIC=1), because the row text goes to the model provider; at most 200 "
        "rows are judged. Use plain run_query whenever a column already holds the answer."),
    "answer": (
        "Question in, rows out: selects the schema, writes the SQL with the server's own configured model, "
        "and runs it, all scoped to the caller. Only available when the server has a model configured; most "
        "clients should use select_schema then run_query with their own model instead."),
    "deep_answer": (
        "Like answer, but able to work in steps (mode 'adaptive', the default, tries one plain query first and "
        "only works in steps when it fails or comes back empty; mode 'deep' always does): the server's model may "
        "run small exploring queries to see real "
        "values (how a status or country is spelled, a date format, whether a join matches), ask for more "
        "tables, and fix a query the database rejected, before running the final query. Every query goes "
        "through the same read-only and caller-scope checks as run_query. Returns the rows plus a step-by-"
        "step trace (each step's SQL and outcome) and what was sent to the model. Off unless the server "
        "enables it (SCHEMAGATE_MCP_DEEP=1), because exploring rows go to the model provider; use it for "
        "questions that name values or span several tables, and answer for simple ones."),
    "refresh_catalog": (
        "Re-read the database structure (new tables, changed columns, changed grants) and swap the index in. "
        "Call it after a migration or a permission change, or when health shows the catalog is stale; it is "
        "not needed before ordinary questions. Takes no arguments, never changes the database, and can take "
        "seconds on a large schema. Returns {ok: true, objects, seconds}. If the database is unreachable it "
        "returns {ok: false, kept_previous: true, error}: the previous catalog stays in service."),
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
        # The `mcp` extra only installs the MCP SDK on Python 3.10+ (the SDK's own floor),
        # so on 3.9 "pip install 'schemagate[mcp]'" succeeds and the server still cannot
        # start. Saying "install the extra" there sends people round in a circle.
        import sys
        if sys.version_info < (3, 10):
            raise ImportError(
                "the MCP server needs Python 3.10 or newer (the MCP SDK does); this is "
                f"Python {sys.version.split()[0]}. With uvx: uvx --python 3.12 --from "
                "'schemagate[mcp]' schemagate-mcp") from e
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
                 run_query, semantic_query, answer, deep_answer, refresh_catalog, health):
        name = tool.__name__
        kw: Dict[str, Any] = {"description": TOOL_DESCRIPTIONS[name]}
        if ToolAnnotations is not None:
            # Every tool only reads. refresh_catalog changes the server's own index, never the database.
            # semantic_query and deep_answer also send rows to an outside model provider, hence openWorld.
            sends_rows = name in ("semantic_query", "deep_answer")
            kw["annotations"] = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                                idempotentHint=not sends_rows,
                                                openWorldHint=sends_rows)
        try:
            app.tool(**kw)(tool)
        except TypeError:                             # an SDK without annotations=
            app.tool(description=kw["description"])(tool)
    return app


#: the tools whose principal and roles OAuth fills in from the token
IDENTITY_TOOLS = ("select_schema", "list_objects", "describe_object", "run_query", "semantic_query", "answer",
                  "deep_answer")


def _oauth_verifier(transport: str):
    """The token verifier when ``SCHEMAGATE_MCP_OAUTH_ISSUER`` is set, else None. Bad settings stop the server."""
    from . import oauth
    try:
        cfg = oauth.OAuthConfig.from_env()
        if cfg is None:
            return None
        if transport == "stdio":
            raise ValueError("OAuth applies to the HTTP transports; set SCHEMAGATE_MCP_TRANSPORT=streamable-http")
        verifier = oauth.Verifier(cfg)
    except (ValueError, ImportError) as e:
        raise SystemExit(f"schemagate-mcp: OAuth: {e}") from None
    log.info("OAuth on: tokens from %s for audience %s; principal and roles come from the token",
             cfg.issuer, cfg.audience)
    return verifier


def _serve_oauth(app, verifier, transport: str, host: str, port: int) -> None:
    """Serve the SDK's HTTP app behind `oauth.OAuthMiddleware`, with uvicorn (an mcp dependency)."""
    import uvicorn

    from .oauth import OAuthMiddleware
    build = app.sse_app if transport == "sse" else app.streamable_http_app
    try:
        asgi = build(host=host)                 # mcp 2.x: host decides the DNS-rebinding defaults
    except TypeError:
        asgi = build()                          # mcp 1.x: host was given to the constructor
    uvicorn.run(OAuthMiddleware(asgi, verifier, IDENTITY_TOOLS), host=host, port=port,
                log_level=os.environ.get("SCHEMAGATE_LOG_LEVEL", "INFO").lower(), proxy_headers=True)


def main(argv: Optional[List[str]] = None) -> None:
    """``schemagate-mcp`` and ``python -m schemagate.mcp_server``.

    Everything is configured by environment variables, as before; ``--url``
    and ``--config`` are the same two settings for clients that pass command
    arguments rather than an environment (``claude mcp add``, a one-line
    ``uvx`` entry). A URL with a password belongs in the environment variable:
    command arguments are visible to every process on the machine.
    """
    ap = argparse.ArgumentParser(
        prog="schemagate-mcp",
        description="schemagate MCP server: the schema an agent may see, filtered by the caller's roles.")
    ap.add_argument("--url", help="SQLAlchemy database URL, or 'demo' for the bundled sample schema "
                                  "(overrides SCHEMAGATE_DATABASE_URL; keep passwords in that variable instead)")
    ap.add_argument("--config", help="JSON file with restrictions and hints (overrides SCHEMAGATE_CATALOG_CONFIG)")
    ap.add_argument("--version", action="version", version=f"schemagate {__version__}")
    a = ap.parse_args(argv)
    if a.url:
        os.environ["SCHEMAGATE_DATABASE_URL"] = a.url
    if a.config:
        os.environ["SCHEMAGATE_CATALOG_CONFIG"] = a.config
    logging.basicConfig(level=os.environ.get("SCHEMAGATE_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        _server_class()             # fail before reflecting a database if the extra is missing
    except ImportError as e:
        raise SystemExit(f"schemagate-mcp: {e}") from None
    transport = os.environ.get("SCHEMAGATE_MCP_TRANSPORT", "stdio")
    verifier = _oauth_verifier(transport)       # before reflecting: a bad OAuth setting stops here
    build_catalog()
    app = create_server()
    _STATE["auth"] = "oauth" if verifier is not None else ("none" if transport != "stdio" else "stdio")
    log.info("schemagate %s serving %d objects over %s", __version__,
             len(_catalog()._docs), transport)
    if transport == "stdio":
        app.run()
        return
    host = os.environ.get("SCHEMAGATE_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("SCHEMAGATE_MCP_PORT", "8765"))
    if verifier is not None:
        _serve_oauth(app, verifier, transport, host, port)
        return
    if host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("HTTP on %s without OAuth: principal and roles are whatever the client sends. "
                    "Set SCHEMAGATE_MCP_OAUTH_ISSUER, or keep it behind something that authenticates.", host)
    try:
        app.run(transport=transport, host=host, port=port)   # mcp 2.x
    except TypeError:
        app.run(transport=transport)                          # mcp 1.x


if __name__ == "__main__":
    main()
