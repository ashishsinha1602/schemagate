# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""A sentence after the query is dropped; anything that might be SQL is not.

Measured: in the Spider-ACL audit, 2 of 8,128 answered queries failed only because the model
wrote an explanation after the SQL. Dropping a tail cannot hide a write (the cut text is never
run), but a tail that names a statement or a forbidden word must still be rejected loudly.
"""
import pytest

from schemagate.answer import UnsafeSQL, check_read_only


@pytest.mark.parametrize("reply", [
    "SELECT name FROM customers WHERE region = 'EU'\n\nThis returns every customer in the EU region.",
    "SELECT name FROM customers WHERE region = 'EU';\n\nThis returns every customer in the EU region.",
    "SELECT name FROM customers WHERE region = 'EU'; This returns every customer in the EU region.",
    "Here is the query:\nSELECT name FROM customers WHERE region = 'EU'\n\nNote that names are not unique here.",
])
def test_an_explanation_after_the_query_is_dropped(reply):
    assert check_read_only(reply) == "SELECT name FROM customers WHERE region = 'EU'"


def test_the_two_real_replies_from_the_spider_acl_audit():
    """Both from Claude Sonnet 5.5 on Spider-ACL (line breaks restored; the log flattened them)."""
    after = ("SELECT name FROM people WHERE hair = 'Black' AND address IS NOT NULL\n\n"
             "Case sensitivity: SQLite's `=` on TEXT is case-sensitive, and the common value for this "
             "dataset is 'Black', so I used that.")
    assert check_read_only(after) == "SELECT name FROM people WHERE hair = 'Black' AND address IS NOT NULL"
    before = ("There is no name column shown, so I should use only the columns that are available.\n"
              "SELECT hg.team_id, hg.attendance FROM home_game hg WHERE hg.year = 1980 "
              "ORDER BY hg.attendance ASC LIMIT 1")
    assert check_read_only(before).startswith("SELECT hg.team_id")


def test_a_cte_split_by_a_blank_line_is_kept_whole():
    sql = ("WITH a AS (SELECT 1 AS x),\n\nb AS (SELECT x FROM a)\nSELECT x FROM b")
    assert check_read_only(sql) == sql


def test_a_query_continued_after_a_blank_line_is_kept_whole():
    sql = "SELECT name, region\nFROM customers\n\nWHERE region = 'EU'\nORDER BY name"
    assert check_read_only(sql) == sql


def test_case_when_with_a_bind_variable_after_a_blank_line_stays_sql():
    sql = "SELECT id,\n\nCASE WHEN :limit > 0 THEN amount ELSE 0 END AS capped FROM orders"
    assert check_read_only(sql) == sql


def test_a_semicolon_inside_a_string_is_not_a_break():
    sql = "SELECT 'a; this is just text in the literal' AS note FROM t"
    assert check_read_only(sql) == sql


@pytest.mark.parametrize("reply, why", [
    ("SELECT 1;\nDELETE FROM customers", "more than one statement|DELETE"),
    ("SELECT 1\n\nThen we delete the old rows from customers to tidy up.", "DELETE"),
    ("SELECT 1; SELECT 2", "more than one statement"),
    ("SELECT 1;\n\nSELECT name FROM customers WHERE secret = 1", "more than one statement"),
])
def test_a_tail_that_might_be_sql_is_still_rejected(reply, why):
    with pytest.raises(UnsafeSQL, match=why):
        check_read_only(reply)


def test_a_reply_without_a_tail_is_unchanged():
    sql = "SELECT COUNT(*) FROM orders WHERE status = 'shipped'"
    assert check_read_only(sql) == sql
    assert check_read_only(sql + ";") == sql
