"""SQL Server: what the Inspector cannot tell us.

Same three hooks as the other two modules, and the same reasons.

* ``get_schema_names()`` returns the server's schemas alongside the user's.
  ``sys`` and ``INFORMATION_SCHEMA`` are hundreds of objects nobody asks
  questions about, and every database also carries nine empty schemas created
  for the fixed database roles -- ``db_owner``, ``db_datareader`` and the rest.
  ``dbo`` is emphatically NOT internal: it is where most SQL Server databases
  keep everything, exactly as ``public`` is on PostgreSQL. Getting that
  backwards would empty the catalog.

* SQLAlchemy reports a type it has no class for as NULL. On SQL Server that is
  ``hierarchyid``, ``geometry`` and ``geography``, ``sql_variant``, and any
  CLR or alias type the database defines -- and an alias type is the common
  one, because ``CREATE TYPE dbo.AccountNumber FROM nvarchar(20)`` is ordinary
  practice. A column whose type reads NULL in the prompt tells the model
  nothing.

* An alias type that *does* resolve resolves to its base, so ``AccountNumber``
  arrives as ``NVARCHAR(20)`` and the name the user would write is lost.
  ``sys.types`` keeps both, so the prompt can carry the name and the base.

Exercised against SQL Server 2022 (16.0.4295.3) by
``tests/test_dialect_mssql_live.py``, which the ``mssql`` workflow runs on
every push against a service container -- the alias type that reflection
resolves away, the two types SQLAlchemy renders as NULL, and ``max_length``
being bytes rather than characters, all of which are invisible to a unit test.
``schemagate certify`` passes its ten checks on the same server.

``FILL_UNKNOWN_TYPES`` is still called through ``fill_unknown_types``, which
swallows exceptions, so a query that goes wrong on a version this has not seen
degrades to the behaviour before this module existed rather than breaking
reflection.
"""
from __future__ import annotations

from typing import Any, Dict, List, MutableMapping, Optional, Set
from weakref import WeakKeyDictionary

from . import FILL_UNKNOWN_TYPES, INTERNAL_SCHEMA, MAINTAINED_SCHEMAS

#: The server's own, by exact name. `dbo` is absent deliberately and must stay
#: absent -- it is the default schema for user objects, so treating it as
#: internal would hide almost every table in a typical database.
_INTERNAL_EXACT = {"sys", "information_schema", "guest"}

#: Every database is created with one schema per fixed database role. They are
#: empty, they are not the user's, and they are the same nine names in every
#: SQL Server database ever made.
_FIXED_ROLE_SCHEMAS = {
    "db_owner", "db_accessadmin", "db_securityadmin", "db_ddladmin",
    "db_backupoperator", "db_datareader", "db_datawriter",
    "db_denydatareader", "db_denydatawriter",
}


def looks_internal(schema: str) -> bool:
    low = schema.lower()
    return low in _INTERNAL_EXACT or low in _FIXED_ROLE_SCHEMAS


#: The fixed-role schemas occupy a reserved principal id range, so they can be
#: found by identity rather than by matching the nine names -- which also
#: catches a server whose collation or localisation names them differently.
_MAINTAINED_SQL = """
    SELECT name
      FROM sys.schemas
     WHERE name IN ('sys', 'INFORMATION_SCHEMA', 'guest')
        OR (principal_id >= 16384 AND principal_id <= 16393)
"""


def maintained_schemas(engine) -> Set[str]:
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(_MAINTAINED_SQL).fetchall()
    return {r[0] for r in rows}


#: One catalog query per engine, keyed weakly on the engine object.
#:
#: `id(engine)` would be wrong here for the reason the other two modules
#: record: CPython reuses the id of a collected object, so a later engine can
#: land on the same key and be handed the previous database's column types
#: without issuing a query. A weak key cannot outlive the engine it describes.
_TYPE_CACHE: "MutableMapping[Any, Dict[tuple, str]]" = WeakKeyDictionary()

#: `t.name` is what the user would write; `b.name` is what it is made of, so
#: an alias type can be rendered as both. `max_length` is bytes, so an
#: n-prefixed type reports twice its character length -- `_render` halves it,
#: and -1 means MAX.
#:
#: No percent sign anywhere in this query, for the reason the PostgreSQL
#: module documents: `exec_driver_sql` hands the string to the driver
#: unchanged and several drivers read `%` as a placeholder.
_TYPES_SQL = """
    SELECT s.name, o.name, c.name,
           t.name, t.is_user_defined,
           b.name,
           c.max_length, c.precision, c.scale
      FROM sys.columns c
      JOIN sys.objects o ON o.object_id = c.object_id
      JOIN sys.schemas s ON s.schema_id = o.schema_id
      JOIN sys.types   t ON t.user_type_id = c.user_type_id
      LEFT JOIN sys.types b ON b.user_type_id = t.system_type_id
                           AND b.is_user_defined = 0
     WHERE o.type IN ('U', 'V')
"""

_SIZED = {"varchar", "nvarchar", "char", "nchar", "varbinary", "binary"}
_PRECISION = {"decimal", "numeric"}


def _render(type_name: str, is_udt, base_name, max_length, precision, scale) -> str:
    """The type as the user would write it in DDL."""
    name = str(type_name)
    low = name.lower()

    def sized(n: str, length) -> str:
        if length is None:
            return n
        if int(length) == -1:
            return f"{n}(MAX)"
        # max_length is bytes; the n-prefixed types store two per character.
        chars = int(length) // 2 if n.lower().startswith("n") else int(length)
        return f"{n}({chars})"

    if is_udt and base_name:
        # Keep the name the schema declares and say what it is underneath,
        # because only one of the two is useful on its own.
        base = str(base_name)
        low_base = base.lower()
        if low_base in _SIZED:
            base = sized(base, max_length)
        elif low_base in _PRECISION and precision is not None:
            base = f"{base}({precision},{scale or 0})"
        return f"{name} ({base})"
    if low in _SIZED:
        return sized(name, max_length)
    if low in _PRECISION and precision is not None:
        return f"{name}({precision},{scale or 0})"
    return name


def _catalog_types(engine) -> "Dict[tuple, str]":
    cached = _TYPE_CACHE.get(engine)
    if cached is not None:
        return cached
    out: "Dict[tuple, str]" = {}
    with engine.connect() as conn:
        for row in conn.exec_driver_sql(_TYPES_SQL):
            schema, table, column, tname, is_udt, base, length, prec, scale = row
            out[(str(schema), str(table), str(column))] = _render(
                tname, is_udt, base, length, prec, scale)
    _TYPE_CACHE[engine] = out
    return out


def unknown_types(engine, schema: Optional[str],
                  table: str, columns: List[dict]) -> None:
    """Give a name to the columns SQLAlchemy could not render.

    Two cases, mirroring the PostgreSQL module rather than the Oracle one:

    * a type SQLAlchemy has no class for reads NULL -- ``hierarchyid``,
      ``geometry``, ``geography``, ``sql_variant``, CLR types.
    * an alias type resolves to its base, so ``dbo.AccountNumber`` arrives as
      ``NVARCHAR(20)``. That is not wrong, which is why it cannot be detected
      from the reflected value alone -- only the catalog knows the column was
      declared with a name of its own.

    So, like PostgreSQL and unlike Oracle, this asks the catalog even when
    nothing reads NULL, and rewrites only what it can improve.
    """
    if not columns:
        return
    known = _catalog_types(engine)
    nsp = schema or "dbo"
    for col in columns:
        rendered = known.get((nsp, table, col.get("name")))
        if not rendered:
            continue
        current = str(col.get("type") or "").upper()
        # A user-defined type is rendered "Name (BASE)"; take it whenever the
        # catalog knows a name the reflection lost, or when nothing was read.
        if current in ("NULL", "NULLTYPE") or "(" in rendered and " (" in rendered:
            col["type"] = rendered


MAINTAINED_SCHEMAS["mssql"] = maintained_schemas
INTERNAL_SCHEMA["mssql"] = looks_internal
FILL_UNKNOWN_TYPES["mssql"] = unknown_types
