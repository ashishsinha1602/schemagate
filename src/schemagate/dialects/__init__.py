# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Per-dialect refinements to reflection.

``schemagate.introspect`` is deliberately free of vendor SQL: the Inspector
does the work and anything SQLAlchemy supports is supported. A handful of
things the Inspector cannot know are worth a dictionary query on specific
engines -- which schemas the vendor itself installs, the real name of a
column type SQLAlchemy has no class for. Those live here, one module per
dialect, and are looked up by ``engine.dialect.name``. No hook, no query.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Set

#: dialect name -> callable(engine) -> schema names to leave out
MAINTAINED_SCHEMAS: Dict[str, Callable] = {}
#: dialect name -> callable(engine, schema, table, columns) -> None (in place)
FILL_UNKNOWN_TYPES: Dict[str, Callable] = {}
#: dialect name -> callable(schema name) -> bool
INTERNAL_SCHEMA: Dict[str, Callable] = {}
#: dialect name -> callable(engine) -> {(schema, object name)} to leave out
MAINTAINED_OBJECTS: Dict[str, Callable] = {}


def is_internal_schema(engine, schema: Optional[str]) -> bool:
    """Is this schema the platform's rather than the user's?

    Strictly per-dialect. A shared list is a trap: ``PUBLIC`` is a pseudo-schema
    on Oracle and the default user schema on PostgreSQL, so one engine's tidy-up
    is another's empty catalog.
    """
    if not schema:
        return False
    hook = INTERNAL_SCHEMA.get(engine.dialect.name)
    if hook is None:
        return False
    try:
        return bool(hook(schema))
    except Exception:
        return False


def vendor_maintained(engine) -> Set[str]:
    hook = MAINTAINED_SCHEMAS.get(engine.dialect.name)
    if hook is None:
        return set()
    try:
        return set(hook(engine))
    except Exception:
        # over-inclusive beats a silently missing table
        return set()


def vendor_maintained_objects(engine) -> Set[tuple]:
    """Individual objects an extension owns, inside an otherwise user schema.

    Excluding whole schemas is not enough: PostGIS puts `spatial_ref_sys` --
    8,500 rows of map projections -- straight into `public`, next to the
    user's own tables.
    """
    hook = MAINTAINED_OBJECTS.get(engine.dialect.name)
    if hook is None:
        return set()
    try:
        return set(hook(engine))
    except Exception:
        return set()


def fill_unknown_types(engine, schema: Optional[str], table: str, columns: List[dict]) -> None:
    hook = FILL_UNKNOWN_TYPES.get(engine.dialect.name)
    if hook is None:
        return
    try:
        hook(engine, schema, table, columns)
    except Exception:
        pass


#: Dialects whose ``information_schema.columns`` is the ANSI view, used when
#: SQLAlchemy's own column query is refused.
_INFO_SCHEMA_DIALECTS = {"postgresql", "mysql", "mariadb", "mssql", "snowflake"}


def ansi_columns(bind, schema):
    """``{table: [column dict]}`` for one schema from the ANSI view, or ``{}``.

    Measured on EBI's public RNAcentral PostgreSQL (316 tables, a role that
    may not read pg_collation): SQLAlchemy reflection returned no tables at
    all after 235 s; this returns every column in one query.
    """
    dialect = getattr(getattr(bind, "dialect", None), "name", None)
    if dialect not in _INFO_SCHEMA_DIALECTS:
        return {}
    from sqlalchemy import text

    where = "table_schema = :s" if schema else "table_schema = current_schema()"
    if dialect in ("mysql", "mariadb") and not schema:
        where = "table_schema = DATABASE()"
    elif dialect == "mssql" and not schema:
        where = "table_schema = SCHEMA_NAME()"
    sql = text("SELECT table_name, column_name, data_type, is_nullable, character_maximum_length, "
               "numeric_precision, numeric_scale FROM information_schema.columns WHERE " + where +
               " ORDER BY table_name, ordinal_position")
    out = {}
    try:
        conn_cm = bind.connect() if hasattr(bind, "connect") else None
        with (conn_cm if conn_cm is not None else _NullContext(bind)) as conn:
            rows = conn.execute(sql, {"s": schema} if schema else {}).fetchall()
    except Exception:
        return {}
    for table, col, dtype, nullable, length, precision, scale in rows:
        kind = str(dtype or "").upper()
        if length and length > 0 and "CHAR" in kind:
            kind = f"{kind}({length})"
        elif kind in ("NUMERIC", "DECIMAL") and precision:
            kind = f"{kind}({precision},{scale or 0})"
        out.setdefault(table, []).append({"name": col, "type": kind, "nullable": str(nullable).upper() != "NO",
                                          "comment": None})
    return out


def hides_typed_columns(bind) -> bool:
    """SQL Server leaves out of sys.types -- and so out of SQLAlchemy's column query -- a user-defined type the
    login has no permission on, and the columns of that type with it."""
    return getattr(getattr(bind, "dialect", None), "name", None) == "mssql"


def ansi_view_definitions(bind, schema):
    """``{view: definition}`` for one schema in one query, or ``{}``.

    One query per view before: 20 of AdventureWorks' 89 on SQL Server. A view
    missing here (PostgreSQL leaves the column NULL unless you own the view)
    is still read on its own by the caller. SQL Server's standard view cuts
    definitions at 4,000 characters, so it is read from sys.sql_modules.
    """
    dialect = getattr(getattr(bind, "dialect", None), "name", None)
    if dialect not in _INFO_SCHEMA_DIALECTS:
        return {}
    from sqlalchemy import text

    if dialect == "mssql":
        sql = ("SELECT v.name, m.definition FROM sys.views v JOIN sys.sql_modules m ON m.object_id = v.object_id "
               "JOIN sys.schemas s ON s.schema_id = v.schema_id WHERE s.name = " +
               (":s" if schema else "SCHEMA_NAME()"))
    else:
        cur = {"mysql": "DATABASE()", "mariadb": "DATABASE()"}.get(dialect, "current_schema()")
        sql = ("SELECT table_name, view_definition FROM information_schema.views WHERE table_schema = " +
               (":s" if schema else cur))
    try:
        conn_cm = bind.connect() if hasattr(bind, "connect") else None
        with (conn_cm if conn_cm is not None else _NullContext(bind)) as conn:
            rows = conn.execute(text(sql), {"s": schema} if schema else {}).fetchall()
    except Exception:
        return {}
    return {name: d for name, d in rows if d}


class _NullContext:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, *exc):
        return False



from . import oracle as _oracle  # noqa: E402,F401  (registers its hooks)
from . import postgresql as _postgresql  # noqa: E402,F401  (same)
from . import mssql as _mssql  # noqa: E402,F401  (same)
