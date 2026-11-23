"""A table reached through a key with no name of its own pulls in the table that holds the name.

"Which 3 suppliers did we spend the most with" picked sup_purchase_order, reached sup_supplier through its key,
and stopped: sup_supplier holds a vendor number and a key to core_party, where the name is. Every database
answered with V-0408, V-0410, V-0403 instead of the suppliers' names.
"""
from schemagate import Principal
from schemagate.answer import _flavour
from schemagate.catalog import _names_something
from schemagate.demo_schema import demo_catalog

WHO = Principal("app:ana", roles=frozenset())
Q = "Which 3 suppliers did we spend the most with on purchase orders in 2025, not counting cancelled orders?"


def test_the_supplier_names_table_is_sent():
    names = [h.doc.name for h in demo_catalog().select(Q, top_k=6, principal=WHO).hits]
    assert "sup_supplier" in names and "core_party" in names


def test_the_extra_hop_never_brings_a_hidden_table():
    cat = demo_catalog()
    cat.restrict("core_party", ["hr"])
    names = [h.doc.name for h in cat.select(Q, top_k=6, principal=WHO).hits]
    assert "core_party" not in names


def test_only_a_nameless_table_hops_again():
    cat = demo_catalog()
    docs = {d.name: d for d in cat.objects()}
    assert not _names_something(docs["sup_supplier"])
    assert _names_something(docs["core_party"]) and _names_something(docs["cat_product"])


def test_each_engine_gets_its_own_rules():
    assert "LIMIT n" in _flavour("postgresql") and "ILIKE" in _flavour("postgresql+psycopg")
    assert "backticks" in _flavour("mysql") and "backticks" in _flavour("mariadb")
    assert "TOP (n)" in _flavour("mssql") and "never positions" in _flavour("mssql")
    assert "FETCH FIRST" in _flavour("oracle")
    assert _flavour("sqlite") == " Target dialect: sqlite."
