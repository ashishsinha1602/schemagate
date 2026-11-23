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
    # SQLite (the BIRD gate's dialect) keeps the exact prompt; PostgreSQL, MySQL and SQL Server get their own
    # rules since 2026-11-22 (a 5-engine eval: GROUP BY 1, date substrings and integer division were the misses)
    p = Capture()
    generate_sql(p, "q", "CREATE TABLE t (id INT)", dialect="sqlite")
    assert p.system == SYSTEM + " Target dialect: sqlite."
    for name in ("postgresql", "mysql", "mssql"):
        p = Capture()
        generate_sql(p, "q", "CREATE TABLE t (id INT)", dialect=name)
        assert p.system == SYSTEM + f" Target dialect: {name}.\n" + DIALECT_RULES[name]
    p = Capture()
    generate_sql(p, "q", "CREATE TABLE t (id INT)")
    assert p.system == SYSTEM


def test_the_paste_prompt_carries_the_same_rules():
    assert DIALECT_RULES["oracle"] in sql_prompt("q", "CREATE TABLE t (id NUMBER)", dialect="oracle")
    assert "Oracle rules" not in sql_prompt("q", "CREATE TABLE t (id INT)", dialect="sqlite")
