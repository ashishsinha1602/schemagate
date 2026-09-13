import pytest
from schemagate import Catalog, HashingEmbedder

def test_reflects_everything(cat):
    assert len(cat._docs) == 42
    kinds = {d.kind for d in cat._docs.values()}
    assert kinds == {"TABLE", "VIEW"}

def test_reflects_foreign_keys(cat):
    ol = cat._docs["main.sales_order_line"]
    refs = {fk.ref_table for fk in ol.foreign_keys}
    assert {"sales_order", "cat_product"} <= refs

def test_self_referencing_fk_survives(cat):
    assert any(fk.ref_table == "hr_employee"
               for fk in cat._docs["main.hr_employee"].foreign_keys)

def test_view_definition_is_indexed(cat):
    """reorder_point appears only inside the view SQL, not its output columns."""
    txt = cat._docs["main.v_stock_shortfall"].embed_text().lower()
    assert "reorder" in txt
    assert "reorder_point" not in {c.name for c in
                                   cat._docs["main.v_stock_shortfall"].columns}

def test_fk_expansion_adds_unnamed_join_tables(cat):
    sel = cat.select("discount per line", top_k=3)
    assert any(h.reason == "fk" for h in sel.hits)

def test_decoy_is_outranked(cat):
    """billing_invoice is real revenue; sales_invoice_draft is a decoy."""
    sel = cat.select("unpaid invoices over 90 days", top_k=4, expand_fks=False)
    names = [d.name for d in sel.objects]
    assert names[0] == "billing_invoice"

def test_top_k_is_respected_before_expansion(cat):
    sel = cat.select("revenue", top_k=3, expand_fks=False)
    assert len(sel) <= 3

def test_pin_forces_inclusion(cat):
    sel = cat.select("headcount", top_k=3, pin=["core_country"], expand_fks=False)
    assert "core_country" in {d.name for d in sel.objects}
    assert sel.hits[0].reason == "pinned"

def test_hint_overrides_and_unknown_raises(cat):
    cat.hint("billing_payment", "cash receipts")
    assert cat._docs["main.billing_payment"].hint == "cash receipts"
    with pytest.raises(KeyError):
        cat.hint("no_such_table", "x")

def test_object_list_shape_for_select_ai(cat):
    ol = cat.select("revenue by month", top_k=2, expand_fks=False).object_list
    assert all(set(e) <= {"name", "owner"} and "name" in e for e in ol)

def test_prompt_fragment_is_valid_ddl_ish(cat):
    frag = cat.select("stock per warehouse", top_k=3).prompt_fragment()
    assert "inv_stock_level" in frag and "(" in frag and ")" in frag

def test_empty_catalog_returns_empty_selection():
    sel = Catalog().select("anything")
    assert len(sel) == 0 and sel.total_objects == 0

def test_selection_is_deterministic(cat):
    a = cat.select("late shipments by carrier").table_names
    b = cat.select("late shipments by carrier").table_names
    assert a == b

def test_embedder_is_deterministic_across_instances():
    t = ["v_monthly_revenue total net", "hr_department cost centre"]
    assert HashingEmbedder(dim=256).embed(t) == HashingEmbedder(dim=256).embed(t)

def test_embeddings_are_unit_norm():
    v = HashingEmbedder().embed(["billing_invoice total_gross"])[0]
    assert abs(sum(x * x for x in v) - 1.0) < 1e-9

def test_handles_empty_and_unicode_text():
    e = HashingEmbedder()
    assert len(e.embed([""])[0]) == e.dim
    assert len(e.embed(["facturación mensual 月次売上"])[0]) == e.dim


# --- date-partitioned families -------------------------------------------

def _dated(cat, stem, n, schema="ga"):
    from schemagate import Column, ObjectDoc
    for i in range(1, n + 1):
        cat.add(ObjectDoc(name="%s%08d" % (stem, 20200100 + i), schema=schema,
                          kind="TABLE",
                          columns=[Column("user_id", "STRING", True, None, False)]))


def test_a_table_split_per_day_collapses_to_one():
    """92 daily tables are one table to anyone using them.

    They differ only by a date, which nothing lexical or vector can reason
    about, so held apart they behave as 92 near-identical documents crowding
    out everything else. Measured on Spider 2.0: a question about January
    selected twelve tables from November.
    """
    from schemagate import Catalog, Column, ObjectDoc
    cat = Catalog()
    _dated(cat, "events_", 92)
    cat.add(ObjectDoc(name="customers", schema="ga", kind="TABLE",
                      columns=[Column("id", "INT64", False, None, True)]))
    assert len(cat) == 93
    removed = cat.collapse_partitions()
    cat.index()
    assert removed == 91
    names = {d.name for d in cat.objects()}
    # the separator stays in the stem: BigQuery's wildcard is `events_*`
    assert names == {"events_*", "customers"}
    doc = next(d for d in cat.objects() if d.name == "events_*")
    assert "92 of them" in (doc.description or "")


def test_the_surviving_partition_keeps_the_widest_columns():
    """A schema that grew a column mid-year must still advertise it."""
    from schemagate import Catalog, Column, ObjectDoc
    cat = Catalog()
    for i, ncols in ((1, 1), (2, 1), (3, 3)):
        cat.add(ObjectDoc(
            name="log_2024010%d" % i, schema="s", kind="TABLE",
            columns=[Column("c%d" % k, "TEXT", True, None, False)
                     for k in range(ncols)]))
    cat.collapse_partitions()
    doc = next(iter(cat.objects()))
    assert len(doc.columns) == 3


def test_two_annual_snapshots_are_not_a_partition_set():
    """Two tables ending in a year may be things someone wants told apart."""
    from schemagate import Catalog, Column, ObjectDoc
    cat = Catalog()
    for y in (2023, 2024):
        cat.add(ObjectDoc(name="snapshot_%d" % y, schema="s", kind="TABLE",
                          columns=[Column("id", "INT", False, None, True)]))
    assert cat.collapse_partitions() == 0
    assert len(cat) == 2


def test_collapsing_puts_the_family_back_in_reach():
    """The point of it: the family can be selected at all."""
    from schemagate import Catalog, Column, ObjectDoc
    cat = Catalog()
    _dated(cat, "events_", 40)
    for nm in ("customers", "orders", "products", "invoices"):
        cat.add(ObjectDoc(name=nm, schema="ga", kind="TABLE",
                          columns=[Column("id", "INT64", False, None, True)]))
    cat.collapse_partitions()
    cat.index()
    picked = cat.select("user engagement events", top_k=3).table_names
    assert any(n.endswith("events_*") for n in picked), picked
