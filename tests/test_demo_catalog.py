"""The demo means something as a library, not only from the CLI.

`Catalog().bootstrap(create_demo_db())` carried no restriction at all: the
`hr_compensation -> payroll` rule lived in `schemagate demo`, the MCP server
and the Studio, each applying it on its own. A library user doing the
obvious thing saw byte-identical output for any principal and for none, and
concluded identity scoping did nothing. `demo_catalog()` is the demo the way
every entry point shows it.
"""
from __future__ import annotations

from schemagate import Principal
from schemagate.demo_schema import RESTRICT, demo_catalog

Q = "salary and pay grade by employee"


def _names(cat, principal):
    return {getattr(o, "name", o).split(".")[-1]
            for o in cat.select(Q, top_k=10, principal=principal).objects}


def test_the_restriction_ships_with_the_demo():
    cat = demo_catalog()
    doc = next(d for d in cat._docs.values() if d.name == "hr_compensation")
    assert doc.roles == RESTRICT["hr_compensation"] == ["payroll"]
    assert cat._demo_url.startswith("sqlite:///")


def test_a_principal_with_and_without_the_role_see_different_things():
    cat = demo_catalog()
    payroll = _names(cat, Principal("okta:jdoe", roles=frozenset({"payroll"})))
    ops = _names(cat, Principal("okta:mbrown", roles=frozenset({"ops"})))
    anon = _names(cat, None)
    assert "hr_compensation" in payroll
    assert "hr_compensation" not in ops and "hr_compensation" not in anon
    assert ops != payroll, "the whole point: a principal changes the answer"


def test_the_three_entry_points_do_not_carry_their_own_copy():
    """One rule, one place. A copy in an entry point is a copy that drifts."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "schemagate"
    for mod in ("cli.py", "mcp_server.py", "studio.py"):
        text = (src / mod).read_text("utf-8")
        assert 'cat.restrict("hr_compensation", ["payroll"])' not in text, mod
        assert "demo_catalog" in text, mod
