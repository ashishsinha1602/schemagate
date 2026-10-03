# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Catalog configuration that lives outside your code.

A JSON file with up to five blocks; every block is optional::

    {"restrict":        {"hr_compensation": ["payroll"]},
     "restrict_column": {"employees": {"salary": ["hr"],
                                       "national_id": ["hr", "compliance"]}},
     "hint":     {"invoice_draft": "drafts only, not revenue"},
     "describe": {"v_stock_shortfall": "Items below their reorder level."},
     "groups":   {"sources": [{"type": "entra", "tenant": "...", "client_id": "...",
                               "client_secret": "${ENTRA_CLIENT_SECRET}"}],
                  "map": {"Finance Analysts": "finance"}}}

``groups`` is not catalog state: it says where a caller's roles come from
(see ``schemagate.groups``) and is read by the CLI and the MCP server when
they build a Principal. ``apply`` leaves it alone.

``describe`` is where descriptions from ``schemagate describe`` land, so a
catalog described once -- with an API key, or by pasting the prompt into a
free chat window -- stays described for the CLI, the Studio and the MCP
server. Hints always outrank descriptions.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, Mapping, Optional

from .catalog import Catalog

KEYS = ("restrict", "restrict_column", "hint", "describe", "groups")


def load(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    p = pathlib.Path(path)
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: catalog config must be a JSON object")
    unknown = [k for k in data if k not in KEYS]
    if unknown:
        raise ValueError(
            f"{path}: unknown block(s) {', '.join(map(repr, sorted(unknown)))}; "
            f"expected any of {', '.join(KEYS)}")
    return data


def apply(cat: Catalog, config: Mapping[str, Any]) -> None:
    """Apply every catalog block in ``config`` to ``cat``.

    ``restrict`` and ``restrict_column`` raise ``KeyError`` for a table or
    column that is not in the catalog, matching ``Catalog``'s own behaviour:
    an ACL typo that reports success is a restriction that silently is not
    there.
    """
    for table, roles in (config.get("restrict") or {}).items():
        cat.restrict(table, list(roles))
    for table, text in (config.get("hint") or {}).items():
        cat.hint(table, str(text))
    desc = config.get("describe") or {}
    if desc:
        cat.describe(desc, only_missing=False)
    # Last, so a description written above cannot be generated against a
    # column this block is about to withhold.
    for table, columns in (config.get("restrict_column") or {}).items():
        if not isinstance(columns, Mapping):
            raise ValueError(
                f"restrict_column[{table!r}] must be an object mapping "
                f"column name to a list of roles")
        for column, roles in columns.items():
            cat.restrict_column(table, column, list(roles))


def groups_from(config: Mapping[str, Any], default_url: Optional[str] = None):
    """The ``groups`` block as a ``schemagate.groups.Groups`` resolver, or
    ``None`` when there is none -- which means the caller's own roles are
    trusted, as before the block existed."""
    from .groups import from_config
    return from_config(config.get("groups"), default_url=default_url)


def merge_descriptions(path: str, descriptions: Mapping[str, str]) -> int:
    """Write ``descriptions`` into the ``describe`` block of ``path``,
    creating the file if needed and keeping every other block. Returns the
    number of entries written."""
    data = load(path)
    block = dict(data.get("describe") or {})
    n = 0
    for k, v in descriptions.items():
        if isinstance(v, str) and v.strip():
            block[str(k)] = v.strip()
            n += 1
    data["describe"] = block
    pathlib.Path(path).write_text(json.dumps(data, indent=2, sort_keys=True,
                                             ensure_ascii=False) + "\n", "utf-8")
    return n
