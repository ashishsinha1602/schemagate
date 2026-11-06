"""A foreign key must not name a table the caller cannot see (GHSA-xp79-wpv4-qj59).

The object filter already hid a restricted table from selection, from FK
expansion and from `describe_object`. But a *visible* table with a foreign key
into it still printed `-- FK crm_customer(id_party) -> core_party` in its DDL,
and `describe_object` returned the same edge in `foreign_keys`. The name is the
disclosure: it tells the caller the table exists, and what joins to it.
"""
import pytest

from schemagate import Principal, mcp_server
from schemagate.demo_schema import demo_catalog

HIDDEN = "core_party"
ANALYST = Principal("okta:analyst", roles={"finance"})
OFFICER = Principal("okta:officer", roles={"compliance"})


@pytest.fixture
def cat():
    c = demo_catalog()
    c.restrict(HIDDEN, ["compliance"])
    return c


@pytest.fixture
def served(cat, monkeypatch):
    monkeypatch.delenv("SCHEMAGATE_AUDIT_LOG", raising=False)
    mcp_server.build_catalog(catalog=cat)
    return cat


def referrer(cat):
    """A visible table with a foreign key into the hidden one."""
    for d in cat.objects():
        if d.name != HIDDEN and any(fk.ref_table.lower() == HIDDEN for fk in d.foreign_keys):
            return d
    pytest.fail(f"the demo schema has no table referencing {HIDDEN}")


def test_describe_object_drops_the_edge_and_the_ddl_line(served):
    name = referrer(served).name
    out = mcp_server.describe_object(name, principal="okta:analyst", roles=["finance"])
    assert "error" not in out
    assert all(fk["references"].lower() != HIDDEN for fk in out["foreign_keys"])
    assert HIDDEN not in out["ddl"]


def test_describe_object_keeps_the_edge_for_the_role_holder(served):
    name = referrer(served).name
    out = mcp_server.describe_object(name, principal="okta:officer", roles=["compliance"])
    assert any(fk["references"].lower() == HIDDEN for fk in out["foreign_keys"])
    assert f"-> {HIDDEN}" in out["ddl"]


def test_other_foreign_keys_survive(served):
    """Only the edge into the hidden table goes; the rest of the DDL is unchanged."""
    d = referrer(served)
    others = [fk for fk in d.foreign_keys if fk.ref_table.lower() != HIDDEN]
    out = mcp_server.describe_object(d.name, principal="okta:analyst", roles=["finance"])
    assert len(out["foreign_keys"]) == len(others)


def test_selection_fragment_does_not_name_it(cat):
    d = referrer(cat)
    sel = cat.select(d.name.replace("_", " "), top_k=6, principal=ANALYST)
    assert d.qname in [o.qname for o in sel.objects]
    assert HIDDEN not in sel.prompt_fragment()
    shown = cat.select(d.name.replace("_", " "), top_k=6, principal=OFFICER)
    assert f"-> {HIDDEN}" in shown.prompt_fragment()


def test_select_schema_ddl_does_not_name_it(served):
    d = referrer(served)
    out = mcp_server.select_schema(d.name.replace("_", " "), top_k=6,
                                   principal="okta:analyst", roles=["finance"])
    assert d.qname in out["objects"]
    assert HIDDEN not in out["ddl"]


def test_langchain_retriever_does_not_name_it(cat):
    pytest.importorskip("langchain_core")
    from schemagate.integrations.langchain import SchemagateRetriever
    d = referrer(cat)
    docs = SchemagateRetriever(catalog=cat, principal=ANALYST).invoke(d.name.replace("_", " "))
    assert d.qname in [doc.metadata["name"] for doc in docs]
    assert all(HIDDEN not in doc.page_content for doc in docs)


def test_a_name_a_visible_object_shares_stays_visible(cat):
    """Two schemas can hold the same bare name; hiding one must not hide the other's edges."""
    seen = cat._ref_visible(ANALYST)
    assert not seen(HIDDEN) and not seen(f"main.{HIDDEN}")
    assert seen("not_in_the_catalog")
    assert seen(referrer(cat).name)
