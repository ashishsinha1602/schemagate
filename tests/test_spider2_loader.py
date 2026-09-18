"""The Spider 2.0-lite loader reads the schema JSON as it is shaped.

Found by sampling the raw files, not by reading a README (there is none):
`description` is a per-column list aligned to `nested_column_names` when the
table has nested fields, else to `column_names`. The loader used to join
that list into a paragraph and store it as the table's description, and
built columns from `column_names` only -- so a nested table lost the columns
the gold SQL reads, and every table lost its column text. Neither produced
an error.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "benchmarks"))

spider2 = pytest.importorskip("spider2")


def _write(tmp: Path, name: str, doc: dict) -> None:
    (tmp / f"{name}.json").write_text(json.dumps(doc), "utf-8")


@pytest.fixture
def db(tmp_path: Path) -> Path:
    d = tmp_path / "bigquery" / "some_db" / "proj.dataset"
    d.mkdir(parents=True)
    _write(d, "plain", {
        "table_name": "plain",
        "column_names": ["id", "name", "city"],
        "column_types": ["INT64", "STRING", "STRING"],
        "description": ["Unique row id", None, "Billing city"],
        "sample_rows": [],
    })
    _write(d, "nested", {
        "table_name": "nested",
        "column_names": ["id", "address"],
        "column_types": ["INT64", "RECORD"],
        "nested_column_names": ["id", "address.street", "address.zip"],
        "nested_column_types": ["INT64", "STRING", "STRING"],
        "description": ["Unique row id", "Street line", "Postal code"],
        "sample_rows": [],
    })
    return d.parent


def _by_name(docs):
    return {d.name: d for d in docs}


def test_descriptions_land_on_the_column_they_describe(db):
    t = _by_name(spider2.load_db(db))["plain"]
    assert [c.name for c in t.columns] == ["id", "name", "city"]
    assert [c.comment for c in t.columns] == ["Unique row id", None, "Billing city"]


def test_nothing_is_joined_into_a_table_description(db):
    for t in spider2.load_db(db):
        assert t.description is None


def test_nested_tables_use_the_flattened_column_list(db):
    t = _by_name(spider2.load_db(db))["nested"]
    assert [c.name for c in t.columns] == ["id", "address.street", "address.zip"]
    assert [c.type for c in t.columns] == ["INT64", "STRING", "STRING"]
    assert [c.comment for c in t.columns] == ["Unique row id", "Street line", "Postal code"]


def test_a_short_description_list_does_not_raise(tmp_path):
    d = tmp_path / "db" / "ds"
    d.mkdir(parents=True)
    _write(d, "t", {"table_name": "t", "column_names": ["a", "b"],
                    "column_types": ["INT64", "INT64"], "description": ["only a"]})
    t = spider2.load_db(d.parent)[0]
    assert [c.comment for c in t.columns] == ["only a", None]


def test_a_string_description_is_still_a_table_description(tmp_path):
    """Not seen in the data, but the old reading of the key stays valid."""
    d = tmp_path / "db" / "ds"
    d.mkdir(parents=True)
    _write(d, "t", {"table_name": "t", "column_names": ["a"],
                    "column_types": ["INT64"], "description": "Whole table"})
    t = spider2.load_db(d.parent)[0]
    assert t.description == "Whole table"
    assert t.columns[0].comment is None
