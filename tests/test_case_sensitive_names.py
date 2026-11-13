# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""A case-sensitive name reaches the model in the quotes SQL needs.

On Oracle, SQLAlchemy reports a table stored as FRPM and one created as "frpm" with the same
plain string, ``frpm``. Shown that, a model writes ``FROM frpm``; Oracle looks for FRPM and the
query fails. UniQL's Oracle data (1,534 BIRD questions) is loaded with the original quoted names,
so every table there broke this way. Reflection now records the spelling SQLAlchemy's own
preparer would use, and the DDL shows it. Other dialects are untouched.
"""
from types import SimpleNamespace

from sqlalchemy.dialects import oracle, postgresql, sqlite

from schemagate.introspect import _sql_spelling
from schemagate.models import Column, ForeignKey, ObjectDoc


def _spell(dialect):
    return _sql_spelling(SimpleNamespace(dialect=dialect))


def test_oracle_names_as_sql_must_write_them():
    d = oracle.dialect()
    spell = _spell(d)
    n = d.normalize_name
    assert spell(n("FRPM")) is None                      # stored upper case: plain frpm works
    assert spell(n("frpm")) == '"frpm"'                  # created in quotes: case-sensitive
    assert spell(n("CDSCode")) == '"CDSCode"'
    assert spell(n("Free Meal Count (K-12)")) == '"Free Meal Count (K-12)"'
    assert spell(n("DATE")) == '"DATE"'                  # reserved word, stored upper case
    assert spell(None) is None and spell("") is None


def test_other_dialects_unchanged():
    for d in (postgresql.dialect(), sqlite.dialect()):
        spell = _spell(d)
        for name in ("frpm", "CDSCode", "Free Meal Count (K-12)", "date"):
            assert spell(name) is None


def test_ddl_shows_the_quoted_spelling_and_keeps_the_name():
    doc = ObjectDoc(
        name="frpm", schema="california_schools",
        columns=[Column("CDSCode", "VARCHAR2(4000)", pk=True, sql_name='"CDSCode"'),
                 Column("County Name", "VARCHAR2(4000)", sql_name='"County Name"',
                        values=["Alameda", "ALAMEDA"]),
                 Column("cnt", "NUMBER")],
        foreign_keys=[ForeignKey(["CDSCode"], "schools", ["CDSCode"], ref_sql_name='"schools"')],
        extra={"sql_name": '"frpm"'})
    ddl = doc.render_ddl()
    assert 'TABLE california_schools."frpm" (' in ddl
    assert '"CDSCode" VARCHAR2(4000) PK' in ddl
    assert 'UPPER("County Name")' in ddl
    assert "\n  cnt NUMBER" in ddl
    assert '-- FK "frpm"("CDSCode") -> "schools"' in ddl
    # matching, scope checks and selection still use the plain name
    assert doc.qname == "california_schools.frpm"
    assert doc.columns[0].name == "CDSCode"


def test_ddl_without_spellings_is_exactly_as_before():
    doc = ObjectDoc(name="orders", columns=[Column("id", "INTEGER", pk=True)],
                    foreign_keys=[ForeignKey(["id"], "customers", ["id"])])
    assert doc.render_ddl() == "TABLE orders (\n  id INTEGER PK\n)\n-- FK orders(id) -> customers"
