"""Joins inferred from column names, with and without declared primary keys."""
from schemagate import Catalog
from schemagate.models import Column, ObjectDoc


def catalog_of(*docs):
    cat = Catalog()
    for d in docs:
        cat.add(d)
    return cat


def edges(cat):
    return {(d.name, fk.columns[0], fk.ref_table, fk.ref_columns[0])
            for d in cat.objects() for fk in d.foreign_keys}


def test_declared_primary_key_is_the_target():
    cat = catalog_of(
        ObjectDoc(name="customers", columns=[Column("id", "INTEGER", pk=True), Column("name", "TEXT")]),
        ObjectDoc(name="orders", columns=[Column("id", "INTEGER", pk=True), Column("customer_id", "INTEGER")]))
    assert cat.infer_foreign_keys() == 1
    assert edges(cat) == {("orders", "customer_id", "customers", "id")}


def test_warehouse_without_primary_keys_joins_on_the_same_named_column():
    # BEAVER's dw declares no primary key anywhere; before, this inferred nothing
    cat = catalog_of(
        ObjectDoc(name="TIP_SUBJECT_OFFERED", columns=[Column("TIP_SUBJECT_OFFERED_KEY", "VARCHAR"),
                                                        Column("TERM_CODE", "VARCHAR")]),
        ObjectDoc(name="TIP_DETAIL", columns=[Column("TIP_SUBJECT_OFFERED_KEY", "VARCHAR"),
                                               Column("ISBN", "VARCHAR")]))
    assert cat.infer_foreign_keys() == 1
    assert edges(cat) == {("TIP_DETAIL", "TIP_SUBJECT_OFFERED_KEY", "TIP_SUBJECT_OFFERED",
                           "TIP_SUBJECT_OFFERED_KEY")}
    assert all(fk.inferred for d in cat.objects() for fk in d.foreign_keys)


def test_no_primary_key_and_no_same_named_column_adds_nothing():
    cat = catalog_of(
        ObjectDoc(name="customers", columns=[Column("ident", "INTEGER"), Column("name", "TEXT")]),
        ObjectDoc(name="orders", columns=[Column("customer_id", "INTEGER")]))
    assert cat.infer_foreign_keys() == 0


def test_composite_primary_key_is_still_left_alone():
    cat = catalog_of(
        ObjectDoc(name="customers", columns=[Column("id", "INTEGER", pk=True),
                                             Column("customer_id", "INTEGER", pk=True)]),
        ObjectDoc(name="orders", columns=[Column("customer_id", "INTEGER")]))
    assert cat.infer_foreign_keys() == 0


def test_ambiguous_target_is_still_left_alone():
    cat = catalog_of(
        ObjectDoc(name="crm_customer", columns=[Column("customer_key", "INTEGER")]),
        ObjectDoc(name="dim_customer", columns=[Column("customer_key", "INTEGER")]),
        ObjectDoc(name="sales", columns=[Column("customer_key", "INTEGER")]))
    assert cat.infer_foreign_keys() == 0
