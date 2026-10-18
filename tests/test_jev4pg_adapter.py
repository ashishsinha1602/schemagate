# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""schemagate in front of jev4pg's catalogue: each caller's datasets shrink to what they may read.

The dataset records below copy jev4pg's own shape (sdd/generic/catalog.py `Catalog.list`,
sdd/generic/source_catalog.py `describe_relationships`): columns, source_binding with its physical
column list and foreign keys, source_relationships and links. jev4pg itself is not imported.
"""
import copy

import pytest

from schemagate import Catalog, Column, ObjectDoc, Principal
from schemagate.integrations.jev4pg import ScopedCatalog, acting_as, scope_datasets

SALES = Principal("okta:sam", roles=frozenset({"sales"}))
HR = Principal("okta:hana", roles=frozenset({"sales", "hr", "payroll"}))


def _sg():
    cat = Catalog(name="t")
    cat.add(ObjectDoc(name="customers", schema="public", kind="table",
                      columns=[Column("id", "INT"), Column("name", "TEXT"), Column("ssn", "TEXT")]))
    cat.add(ObjectDoc(name="orders", schema="public", kind="table",
                      columns=[Column("id", "INT"), Column("customer_id", "INT"), Column("amount", "NUMERIC")]))
    cat.add(ObjectDoc(name="payroll", schema="public", kind="table",
                      columns=[Column("id", "INT"), Column("customer_id", "INT"), Column("salary", "NUMERIC")]))
    cat.restrict_column("customers", "ssn", roles=["hr"])
    cat.restrict("payroll", roles=["payroll"])
    cat.index()
    return cat


def _ds(id_, name, table, cols, fks=(), rels=(), links=()):
    return {"id": id_, "name": name, "schema_name": "public", "table_name": table,
            "columns": [{"name": c, "type": "text"} for c in cols],
            "source_binding": {"oid": id_, "columns": [{"name": c, "position": i} for i, c in enumerate(cols, 1)],
                               "foreign_keys": list(fks)},
            "source_relationships": list(rels), "links": list(links)}


def _datasets():
    return [
        _ds("c", "customers", "customers", ["id", "name", "ssn"]),
        _ds("o", "orders", "orders", ["id", "customer_id", "amount"],
            fks=[{"name": "fk_c", "source_columns": ["customer_id"]}],
            rels=[{"target_id": "c", "target_table": "customers", "source_columns": ["customer_id"],
                   "target_columns": ["id"]}],
            links=[{"target_id": "c", "source_column": "customer_id", "target_column": "id"}]),
        _ds("p", "payroll", "payroll", ["id", "customer_id", "salary"],
            rels=[{"target_id": "c", "target_table": "customers", "source_columns": ["customer_id"],
                   "target_columns": ["id"]}]),
        # a relationship TO a hidden table and one that joins on a hidden column
        _ds("x", "customer_notes", "customers", ["id", "name"],
            rels=[{"target_id": "p", "target_table": "payroll", "source_columns": ["id"], "target_columns": ["id"]}],
            links=[{"target_id": "c", "source_column": "id", "target_column": "ssn"}]),
        _ds("u", "mystery", "not_in_schemagate", ["a"]),
    ]


def _names(ds):
    return {d["name"]: [c["name"] for c in d["columns"]] for d in ds}


def test_a_caller_sees_only_tables_and_columns_they_may_read():
    out = _names(scope_datasets(_datasets(), _sg(), SALES))
    assert out == {"customers": ["id", "name"], "orders": ["id", "customer_id", "amount"],
                   "customer_notes": ["id", "name"]}


def test_withheld_names_do_not_survive_anywhere_in_the_record():
    text = repr(scope_datasets(_datasets(), _sg(), SALES))
    assert "ssn" not in text and "salary" not in text and "payroll" not in text


def test_relationships_to_hidden_tables_or_on_hidden_columns_are_dropped():
    out = {d["name"]: d for d in scope_datasets(_datasets(), _sg(), SALES)}
    assert out["orders"]["source_relationships"] and out["orders"]["links"]      # legitimate join kept
    assert out["customer_notes"]["source_relationships"] == []                  # pointed at payroll
    assert out["customer_notes"]["links"] == []                                 # joined on ssn


def test_a_caller_with_the_roles_sees_everything_schemagate_knows():
    out = _names(scope_datasets(_datasets(), _sg(), HR))
    assert out["customers"] == ["id", "name", "ssn"] and "payroll" in out
    assert "mystery" not in out                                                  # unknown: fail closed


def test_no_caller_means_anonymous_and_inputs_are_not_modified():
    data = _datasets()
    before = copy.deepcopy(data)
    out = _names(scope_datasets(data, _sg(), None))
    assert "payroll" not in out and "ssn" not in out["customers"]
    assert data == before


class FakeJevCatalog:
    """Stands in for sdd.generic.catalog.Catalog: same method names and call pattern."""

    db = "the-db"

    def list(self, tenant, *, connection=None):
        return _datasets()

    def model_catalog(self, tenant, selected=None, **_):
        # like jev4pg: reads self.list, then appends feature columns derived from a source column
        out = []
        for d in self.list(tenant):
            cols = d["columns"] + [{"name": f"{d['name']}_flag", "type": "boolean",
                                    "source_column": d["columns"][-1]["name"] if d["columns"] else "id"}]
            if d["name"] == "customers":
                cols.append({"name": "ssn_is_valid", "type": "boolean", "source_column": "ssn"})
            out.append({**d, "columns": cols})
        return out


def test_scoped_catalog_list_get_and_delegation():
    cat = ScopedCatalog(FakeJevCatalog(), _sg())
    with acting_as(SALES):
        assert set(_names(cat.list("t"))) == {"customers", "orders", "customer_notes"}
        assert cat.get("t", "orders")["id"] == "o"
        with pytest.raises(ValueError, match="Unknown or ambiguous"):
            cat.get("t", "payroll")
    assert cat.db == "the-db"


def test_model_catalog_runs_on_the_scoped_list_and_drops_features_on_hidden_columns():
    cat = ScopedCatalog(FakeJevCatalog(), _sg())
    with acting_as(SALES):
        mc = {d["name"]: [c["name"] for c in d["columns"]] for d in cat.model_catalog("t")}
    assert "payroll" not in mc
    assert "ssn_is_valid" not in mc["customers"] and "ssn" not in mc["customers"]
    assert "customers_flag" in mc["customers"]          # a feature on a visible column is kept
    with acting_as(HR):
        assert "ssn_is_valid" in {c["name"] for d in cat.model_catalog("t") if d["name"] == "customers"
                                  for c in d["columns"]}
