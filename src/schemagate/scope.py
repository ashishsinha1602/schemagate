# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""The scope check ``run_query`` enforces, usable on any catalog and any database.

``check_scope(catalog, sql, principal, dialect)`` returns None when ``sql`` reads
only objects and columns ``principal`` may see, and the refusal message
otherwise. It is the same function the MCP server's ``run_query`` runs, so
there is one rule and every caller uses it.

The difference is where the dialect comes from. ``run_query`` reads it from the
server's own connection, which is right for one database per process. A
process that answers for several databases -- a hosted service, a multi-tenant
app, a test -- passes each database's dialect here instead, so the SQL parser
reads PostgreSQL as PostgreSQL and T-SQL as T-SQL.

It fails closed: a statement that cannot be parsed, or that names something the
catalog does not know, is refused. It does not check that the statement is a
read. Run ``schemagate.answer.check_read_only`` first; ``run_query`` does both.

    from schemagate import Catalog, Principal
    from schemagate.answer import check_read_only
    from schemagate.scope import check_scope

    sql = check_read_only(model_sql)
    denied = check_scope(catalog, sql, Principal("ana", roles={"sales"}), "postgresql")
    if denied:
        ...  # do not run it
"""
from __future__ import annotations

from typing import Optional

from .catalog import Catalog
from .identity import Principal

__all__ = ["check_scope"]


def check_scope(catalog: Catalog, sql: str, principal: Optional[Principal] = None,
                dialect: str = "") -> Optional[str]:
    """None if ``principal`` may run ``sql`` against ``catalog``, else why not.

    ``dialect`` is the SQLAlchemy dialect name (``postgresql``, ``mysql``,
    ``mssql``, ``oracle``, ``sqlite``); empty means the parser's generic SQL.
    With no principal only unrestricted objects and columns are allowed.
    """
    from .mcp_server import _check_scope
    return _check_scope(catalog, sql, principal, dialect=dialect or "")
