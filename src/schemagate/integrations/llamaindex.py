# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""LlamaIndex retriever over an schemagate catalog.

Use it wherever LlamaIndex takes a retriever. Each selected object comes back
as one ``NodeWithScore`` whose text is its DDL and whose metadata carries the
name, kind, score and selection reason.

    from schemagate import Catalog, Principal
    from schemagate.integrations.llamaindex import SchemagateRetriever

    cat = Catalog().bootstrap("postgresql://localhost/app")
    retriever = SchemagateRetriever(cat, top_k=6,
                                    principal=Principal("okta:jdoe", roles={"finance"}))
    nodes = retriever.retrieve("revenue by month")

The principal is fixed at construction, as in the LangChain retriever: a
query engine cannot forget to pass it. Build one retriever per caller; they
are cheap, and ``with_principal`` shares the catalog.

``pip install 'schemagate[llamaindex]'``.
"""
from __future__ import annotations

from typing import Any, List, Optional

try:
    from llama_index.core.retrievers import BaseRetriever
    from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
except ImportError as e:  # pragma: no cover - import guard
    raise ImportError(
        "pip install 'schemagate[llamaindex]' to use this SchemagateRetriever") from e

from ..catalog import Catalog
from ..identity import Principal


class SchemagateRetriever(BaseRetriever):
    """Identity-scoped schema retriever for LlamaIndex."""

    def __init__(self, catalog: Catalog, principal: Optional[Principal] = None, top_k: int = 6,
                 expand_fks: bool = True, max_columns: int = 40, **kwargs: Any) -> None:
        self.catalog = catalog
        self.principal = principal
        self.top_k = top_k
        self.expand_fks = expand_fks
        self.max_columns = max_columns
        super().__init__(**kwargs)

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        sel = self.catalog.select(query_bundle.query_str, top_k=self.top_k,
                                  principal=self.principal, expand_fks=self.expand_fks)
        return [
            NodeWithScore(
                node=TextNode(
                    id_=hit.doc.qname,
                    text=hit.doc.render_ddl(self.max_columns),
                    metadata={
                        "name": hit.doc.qname,
                        "kind": hit.doc.kind,
                        "reason": hit.reason,
                        "columns": len(hit.doc.columns),
                    },
                ),
                score=hit.score,
            )
            for hit in sel.hits
        ]

    def with_principal(self, principal: Optional[Principal]) -> "SchemagateRetriever":
        """A copy bound to a different caller. Catalog and settings shared."""
        return SchemagateRetriever(self.catalog, principal=principal, top_k=self.top_k,
                                   expand_fks=self.expand_fks, max_columns=self.max_columns)


def prompt_fragment(nodes: List[NodeWithScore]) -> str:
    """Join retrieved nodes back into one DDL block for a prompt."""
    return "\n\n".join(n.node.get_content() for n in nodes)


__all__: List[Any] = ["SchemagateRetriever", "prompt_fragment"]
