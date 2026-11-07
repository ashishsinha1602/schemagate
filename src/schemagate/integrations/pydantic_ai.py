# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Pydantic AI capability over an schemagate catalog.

Gives a text-to-SQL agent one tool, ``select_schema(question)``, that returns only the tables the
question needs and the caller may read.

    from pydantic_ai import Agent
    from schemagate import Catalog, Principal
    from schemagate.integrations.pydantic_ai import SchemagateCapability

    cat = Catalog().bootstrap("postgresql://localhost/app")
    agent = Agent("anthropic:claude-haiku-4-5", capabilities=[
        SchemagateCapability(cat, principal=Principal("okta:jdoe", roles={"finance"}))])

``pip install 'schemagate[pydantic-ai]'``.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import KW_ONLY, dataclass
from typing import Any, Optional, Union

try:
    from pydantic_ai import FunctionToolset, RunContext
    from pydantic_ai.capabilities.abstract import AbstractCapability
    from pydantic_ai.exceptions import UserError
except ImportError as e:  # pragma: no cover - import guard
    raise ImportError(
        "pip install 'schemagate[pydantic-ai]' to use this SchemagateCapability") from e

from ..catalog import Catalog
from ..identity import Principal

#: Who is asking: a fixed caller, a function of the run (usually reading `ctx.deps`), or nobody.
PrincipalSource = Union[Principal, Callable[[RunContext[Any]], Optional[Principal]], None]

_INSTRUCTIONS = (
    "Before writing SQL, call select_schema with the user's question and write SQL only against "
    "the tables and columns it returns. Do not guess at tables it did not return. If what it "
    "returns cannot answer the question, say so rather than approximating from other columns."
)

#: The same words whether nothing matched or nothing is visible, so that a caller cannot tell a
#: table that does not exist from one they may not read.
_NOTHING_VISIBLE = "No tables are available to answer this question."


@dataclass
class SchemagateCapability(AbstractCapability[Any]):
    """Registers `select_schema`, which returns only the tables a question needs and the caller may read.

    The selection runs offline (BM25 plus a small embedder), with no model call. The tool takes a
    question and nothing else, so the model cannot choose who it is asking as: the caller comes
    from `principal`, which the application sets.

    This limits what the model sees. It does not run SQL, and it is not a substitute for permissions
    in the database.

    Args:
        catalog: The schemagate catalogue to select from, such as
            `Catalog().bootstrap("postgresql://...")`.
        principal: The caller. Either a `Principal`, or a function taking the `RunContext` and
            returning one, for agents that serve many users. With `None`, only tables with no
            role restriction are visible.
        top_k: How many tables to rank in. Tables they join to are added on top of this.
        expand_inward: Of the best-ranked tables, how many to consider adding when they join into
            the selection. See `Catalog.select`. Off by default.
        max_columns: How many columns to render per table.
    """

    catalog: Catalog
    _: KW_ONLY
    principal: PrincipalSource = None
    top_k: int = 6
    expand_inward: int = 0
    max_columns: int = 40

    def __post_init__(self) -> None:
        if self.top_k < 1:
            raise ValueError(f"top_k must be at least 1, got {self.top_k}")

    def get_instructions(self) -> str:
        return _INSTRUCTIONS

    def get_toolset(self) -> FunctionToolset[Any]:
        capability = self

        def select_schema(ctx: RunContext[Any], question: str) -> str:
            """Return the tables and columns needed to answer a question, as SQL DDL.

            Args:
                question: The user's question, in their own words.
            """
            return capability._select(ctx, question)

        toolset: FunctionToolset[Any] = FunctionToolset(id="schemagate")
        toolset.add_function(select_schema)
        return toolset

    def _resolve_principal(self, ctx: RunContext[Any]) -> Optional[Principal]:
        who = self.principal(ctx) if callable(self.principal) else self.principal
        if who is not None and not isinstance(who, Principal):
            # Refuse rather than select with a caller nobody can reason about.
            raise UserError(f"principal must resolve to a schemagate.Principal or None, got {type(who).__name__}")
        return who

    def _select(self, ctx: RunContext[Any], question: str) -> str:
        selection = self.catalog.select(
            question,
            top_k=self.top_k,
            principal=self._resolve_principal(ctx),
            expand_inward=self.expand_inward,
        )
        if not selection.table_names:
            return _NOTHING_VISIBLE
        return selection.prompt_fragment(max_columns=self.max_columns)

    @classmethod
    def from_spec(
        cls,
        database_url: Optional[str] = None,
        *,
        restrict: Optional[Mapping[str, Iterable[str]]] = None,
        subject: Optional[str] = None,
        roles: Optional[Iterable[str]] = None,
        top_k: int = 6,
        expand_inward: int = 0,
        max_columns: int = 40,
    ) -> SchemagateCapability:
        """Build from an agent spec, where only plain values can be written.

        Args:
            database_url: A SQLAlchemy URL, or `demo` for the bundled schema. Leave it out and set
                `SCHEMAGATE_DATABASE_URL` to keep credentials out of the spec file.
            restrict: Table name to the roles that may read it.
            subject: Who the agent runs as. A namespaced name such as `okta:jdoe`. Defaults to `spec:agent` when `roles` is set.
            roles: The caller's roles.
        """
        url = database_url or os.environ.get("SCHEMAGATE_DATABASE_URL")
        if not url:
            raise UserError("SchemagateCapability needs database_url, or SCHEMAGATE_DATABASE_URL in the environment")
        if url == "demo":
            from ..demo_schema import demo_catalog

            catalog = demo_catalog()
        else:
            catalog = Catalog().bootstrap(url)
        for table, table_roles in (restrict or {}).items():
            catalog.restrict(table, list(table_roles))
        principal = None
        if subject is not None or roles is not None:
            principal = Principal(subject or "spec:agent", roles=frozenset(roles or ()))
        return cls(catalog, principal=principal, top_k=top_k, expand_inward=expand_inward, max_columns=max_columns)
