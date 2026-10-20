# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Per-dialect rules in the SQL prompt: Oracle gets the rules its first queries broke; others are unchanged."""
from schemagate.answer import DIALECT_RULES, SYSTEM, generate_sql, sql_prompt


class Capture:
    def __init__(self):
        self.system = None

    def complete(self, system, prompt, max_tokens=1024):
        self.system = system
        return "SELECT 1 FROM DUAL"


def test_oracle_gets_its_rules_under_any_spelling():
    for name in ("oracle", "Oracle", "ORACLE", "oracle+oracledb"):
        p = Capture()
        generate_sql(p, "how many accounts", "CREATE TABLE account (id NUMBER)", dialect=name)
        assert DIALECT_RULES["oracle"] in p.system, name
        assert "never write AS before a table alias" in p.system
        assert 't."DATE"' in p.system


def test_other_dialects_and_no_dialect_are_byte_for_byte_unchanged():
    for name in ("sqlite", "postgresql", "mysql", "mssql"):
        p = Capture()
        generate_sql(p, "q", "CREATE TABLE t (id INT)", dialect=name)
        assert p.system == SYSTEM + f" Target dialect: {name}."
    p = Capture()
    generate_sql(p, "q", "CREATE TABLE t (id INT)")
    assert p.system == SYSTEM


def test_the_paste_prompt_carries_the_same_rules():
    assert DIALECT_RULES["oracle"] in sql_prompt("q", "CREATE TABLE t (id NUMBER)", dialect="oracle")
    assert "Oracle rules" not in sql_prompt("q", "CREATE TABLE t (id INT)", dialect="sqlite")
