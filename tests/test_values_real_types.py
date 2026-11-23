"""Category values on the column types real databases use.

`status VARCHAR(255)` is the default string column of most ORMs; a declared-width cap of 40 meant no value was
ever read on PostgreSQL, MySQL, SQL Server or Oracle schemas built that way (measured on all four, 2026-11-23:
0 columns, against 32 on the same data in SQLite). SQL Server reports `VARCHAR(255) COLLATE "..."`. And a Y/N
flag on a four-row lookup table was skipped as an identifier.
"""
import sqlite3

from sqlalchemy import create_engine

from schemagate import Catalog
from schemagate.introspect import _candidates


def _db(tmp_path):
    p = tmp_path / "t.sqlite"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE ticket (id INTEGER PRIMARY KEY, status VARCHAR(255), customer_name VARCHAR(255), "
              "note VARCHAR(4000), ref VARCHAR(255))")
    rows = [(i, ["open", "closed", "pending"][i % 3], f"Person {i}", "x" * 50, f"T-{i:05d}") for i in range(60)]
    c.executemany("INSERT INTO ticket VALUES (?, ?, ?, ?, ?)", rows)
    c.execute("CREATE TABLE ct (id INTEGER PRIMARY KEY, cd VARCHAR(255), actv_flg VARCHAR(255))")
    c.executemany("INSERT INTO ct VALUES (?, ?, ?)", [(1, "REV", "Y"), (2, "COGS", "Y"), (3, "OPEX", "Y"),
                                                      (4, "ADJ", "N")])
    c.commit()
    return create_engine(f"sqlite:///{p}")


def values(cat, table, column):
    return next(c.values for d in cat.objects() if d.name == table for c in d.columns if c.name == column)


def test_varchar_255_categories_are_read_and_names_ids_and_prose_are_not(tmp_path):
    cat = Catalog(name="t").bootstrap(_db(tmp_path), sample_values=True)
    assert values(cat, "ticket", "status") == ["closed", "open", "pending"]
    assert values(cat, "ticket", "customer_name") is None        # personal-looking name: never read
    assert values(cat, "ticket", "ref") is None                  # nearly unique: an identifier
    assert values(cat, "ticket", "note") is None                 # declared wide: prose


def test_a_flag_on_a_small_lookup_table_is_read_but_its_unique_codes_are_not(tmp_path):
    cat = Catalog(name="t").bootstrap(_db(tmp_path), sample_values=True)
    assert values(cat, "ct", "actv_flg") == ["N", "Y"]
    assert values(cat, "ct", "cd") is None                       # 4 distinct in 4 rows: still an identifier


def test_a_collation_after_the_type_does_not_rule_a_column_out():
    cols = [{"name": "status", "type": 'VARCHAR(255) COLLATE "SQL_Latin1_General_CP1_CI_AS"'},
            {"name": "state", "type": "VARCHAR(50) CHARACTER SET utf8mb4"},
            {"name": "body", "type": 'NVARCHAR(4000) COLLATE "Latin1_General_CI_AS"'}]
    assert _candidates(cols, set()) == ["status", "state"]
