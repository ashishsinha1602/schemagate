"""LlamaIndex adapter, exercised against the real llama-index-core package."""
import pytest

pytest.importorskip("llama_index.core")

from schemagate import Principal  # noqa: E402
from schemagate.integrations.llamaindex import SchemagateRetriever, prompt_fragment  # noqa: E402


@pytest.fixture
def retriever(cat):
    cat.restrict("hr_compensation", ["payroll"])
    return SchemagateRetriever(cat, top_k=4)


def test_is_a_real_llamaindex_retriever(retriever):
    from llama_index.core.retrievers import BaseRetriever
    assert isinstance(retriever, BaseRetriever)


def test_retrieve_returns_nodes_with_ddl_and_metadata(retriever):
    nodes = retriever.retrieve("revenue by month")
    assert nodes
    assert "main.v_monthly_revenue" in {n.node.metadata["name"] for n in nodes}
    for n in nodes:
        assert n.node.get_content().startswith(("TABLE", "VIEW", "--"))
        assert {"name", "kind", "reason", "columns"} <= set(n.node.metadata)
        assert isinstance(n.score, float)


def test_top_k_is_honoured_before_expansion(cat):
    assert len(SchemagateRetriever(cat, top_k=2, expand_fks=False).retrieve("revenue")) <= 2


def test_anonymous_retriever_fails_closed(retriever):
    names = {n.node.metadata["name"] for n in retriever.retrieve("salary by employee")}
    assert "main.hr_compensation" not in names
    assert "hr_compensation" not in prompt_fragment(retriever.retrieve("salary by employee"))


def test_bound_principal_sees_what_it_may(retriever):
    hr = retriever.with_principal(Principal("okta:hr", roles={"payroll"}))
    assert "main.hr_compensation" in {n.node.metadata["name"] for n in hr.retrieve("salary by employee")}
    assert retriever.principal is None
    assert hr.catalog is retriever.catalog


def test_restricted_column_follows_the_bound_principal(cat):
    """The DDL and the column count are rendered for the retriever's caller, not for an anonymous one."""
    cat.restrict_column("hr_employee", "employee_number", ["payroll"])
    anon = SchemagateRetriever(cat, top_k=4)
    hr = anon.with_principal(Principal("okta:hr", roles={"payroll"}))

    def employee(r):
        return next(n.node for n in r.retrieve("employees by department")
                    if n.node.metadata["name"] == "main.hr_employee")

    assert "employee_number" not in employee(anon).get_content()
    assert "employee_number" in employee(hr).get_content()
    assert employee(hr).metadata["columns"] == employee(anon).metadata["columns"] + 1


def test_prompt_fragment_round_trips(retriever):
    fragment = prompt_fragment(retriever.retrieve("stock per warehouse"))
    assert "inv_stock_level" in fragment
    assert fragment.count("(") == fragment.count(")")


def test_async_retrieve_works(retriever):
    import asyncio
    nodes = asyncio.run(retriever.aretrieve("late shipments by carrier"))
    assert "ship_shipment" in prompt_fragment(nodes)
