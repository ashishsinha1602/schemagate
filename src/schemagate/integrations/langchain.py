# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""LangChain retriever over an schemagate catalog.

Drop-in for any LangChain chain that takes a retriever. Each selected object
comes back as one ``Document`` whose ``page_content`` is its DDL and whose
metadata carries the name, kind, score and selection reason.

    from schemagate import Catalog, Principal
    from schemagate.integrations.langchain import SchemagateRetriever

    cat = Catalog().bootstrap("postgresql://localhost/app")
    retriever = SchemagateRetriever(catalog=cat, top_k=6,
                               principal=Principal("okta:jdoe", roles={"finance"}))
    docs = retriever.invoke("revenue by month")

The principal is fixed at construction on purpose. A retriever is usually
built once per request, and binding identity to it means a chain cannot
forget to pass it -- the same fail-closed stance as everywhere else in schemagate.
Build a new retriever per caller; they are cheap.

``pip install 'schemagate[langchain]'``.
"""
from __future__ import annotations

from typing import Any, List, Optional

try:
    from langchain_core.callbacks import CallbackManagerForRetrieverRun
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever
except ImportError as e:  # pragma: no cover - import guard
    raise ImportError(
        "pip install 'schemagate[langchain]' to use SchemagateRetriever") from e

from ..catalog import Catalog
from ..identity import Principal


class SchemagateRetriever(BaseRetriever):
    """Identity-scoped schema retriever for LangChain."""

    catalog: Catalog
    principal: Optional[Principal] = None
    top_k: int = 6
    expand_fks: bool = True
    max_columns: int = 40

    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(
        self, query: str, *, run_manager: Optional[CallbackManagerForRetrieverRun] = None,
        top_k: Optional[int] = None,
    ) -> List[Document]:
        """``top_k`` overrides the retriever's for one call: ``retriever.invoke(q, top_k=3)``."""
        sel = self.catalog.select(query, top_k=top_k or self.top_k,
                                  principal=self.principal,
                                  expand_fks=self.expand_fks)
        return [
            Document(
                page_content=hit.doc.render_ddl(self.max_columns, principal=self.principal,
                                                ref_visible=sel.ref_visible),
                metadata={
                    "name": hit.doc.qname,
                    "kind": hit.doc.kind,
                    "score": hit.score,
                    "reason": hit.reason,
                    "columns": len(hit.doc.visible_columns(self.principal)),
                },
            )
            for hit in sel.hits
        ]

    def with_principal(self, principal: Optional[Principal]) -> "SchemagateRetriever":
        """A copy bound to a different caller. Catalog and settings shared."""
        return self.model_copy(update={"principal": principal})


def prompt_fragment(documents: List[Document]) -> str:
    """Join retrieved documents back into one DDL block for a prompt."""
    return "\n\n".join(d.page_content for d in documents)


def optimizer_tools(engine: Any, catalog: Optional[Catalog] = None, principal: Optional[Principal] = None,
                    timeout: float = 60.0) -> List[Any]:
    """Two tools that let your agent make a slow query faster with its own model.

    ``explain_query`` shows the plan (real timings on PostgreSQL) and
    ``compare_queries`` checks a rewrite: same rows as the original, and how
    much faster. The agent writes the rewrite; these tools only prove it. Both
    are read-only and rolled back (see ``schemagate.optimize``). With
    ``catalog`` given, any SQL naming a table ``principal`` may not see is
    refused, the same check as the MCP server's ``run_query``::

        tools = optimizer_tools(engine, catalog=cat, principal=Principal("okta:jdoe"))
        agent = create_react_agent(llm, tools)
    """
    from langchain_core.tools import StructuredTool

    from .. import optimize as _opt
    from ..answer import UnsafeSQL, check_read_only

    dialect = getattr(getattr(engine, "dialect", None), "name", "") or ""

    def _gate(sql: str) -> str:
        sql = check_read_only(sql, dialect)
        if catalog is not None:
            from ..scope import check_scope
            denied = check_scope(catalog, sql, principal, dialect)
            if denied:
                raise UnsafeSQL(denied)
        return sql

    def explain_query(sql: str) -> Any:
        try:
            return {"plan": _opt.explain(engine, _gate(sql), timeout=timeout)}
        except Exception as e:                               # noqa: BLE001 -- the agent reads the reason
            return {"error": str(getattr(e, "orig", e)).strip().splitlines()[0][:400]}

    def compare_queries(original: str, candidate: str) -> Any:
        try:
            original, candidate = _gate(original), _gate(candidate)
            out = _opt.compare(engine, original, candidate, timeout=timeout).to_dict()
        except Exception as e:                               # noqa: BLE001
            return {"error": str(getattr(e, "orig", e)).strip().splitlines()[0][:400]}
        out["new_literals"] = _opt.new_literals(original, candidate)
        return out

    return [
        StructuredTool.from_function(
            explain_query, name="explain_query",
            description="Show the query plan for one read-only SQL query, with real row counts and timings "
                        "on PostgreSQL. Use it to see why a query is slow before rewriting it."),
        StructuredTool.from_function(
            compare_queries, name="compare_queries",
            description="Check a rewrite of a slow query: do 'original' and 'candidate' return exactly the "
                        "same rows, and how fast is each? Only use a candidate with identical=true. "
                        "'new_literals' lists constants the candidate adds; do not hard-code values from "
                        "the data, the rewrite must stay correct when the data changes."),
    ]


__all__: List[Any] = ["SchemagateRetriever", "prompt_fragment", "optimizer_tools"]
