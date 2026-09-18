"""Getting the SQL out of whatever the model wrapped around it.

`_strip_fences` used to strip a code fence only when the reply *began* with
one. Two ordinary model habits defeated that: a sentence of preamble before the
block, and a paragraph of second-guessing after it. Measured on eight complex
questions against a live 1,200-object database, three failed with
"not a SELECT: 'I'" while the model had written correct SQL a line below.

The risk in fixing it is obvious and is what most of this module tests: if
"skip the prose" ever skips a *statement*, a write could be hidden from the
checks that follow. So the prose prefix is dropped only when it contains no
statement separator and nothing forbidden.
"""
from __future__ import annotations

import pytest

from schemagate.answer import UnsafeSQL, _strip_fences, check_read_only


# ------------------------------------------------------------ extraction

def test_a_bare_statement_is_unchanged():
    assert _strip_fences("SELECT 1 FROM dual") == "SELECT 1 FROM dual"


def test_a_leading_fence_still_works():
    assert _strip_fences("```sql\nSELECT 1\n```") == "SELECT 1"


def test_prose_before_the_fence():
    reply = "I'll join the two tables:\n\n```sql\nSELECT 1\n```"
    assert _strip_fences(reply) == "SELECT 1"


def test_commentary_after_the_fence():
    """The one that actually bit: the model answers, then reconsiders."""
    reply = "```sql\nSELECT 1\n```\n\nWait, let me reconsider the join order."
    assert _strip_fences(reply) == "SELECT 1"


def test_prose_on_both_sides():
    reply = ("Here is the query.\n\n```sql\nSELECT a\nFROM t\n```\n"
             "This assumes every contact has a status.")
    assert _strip_fences(reply) == "SELECT a\nFROM t"


def test_an_unfenced_reply_with_a_preamble():
    reply = "I need to aggregate per contact.\nSELECT status FROM t"
    assert _strip_fences(reply) == "SELECT status FROM t"


def test_a_with_clause_counts_as_the_start():
    reply = "Using a CTE:\nWITH x AS (SELECT 1 FROM dual)\nSELECT * FROM x"
    assert _strip_fences(reply).startswith("WITH x AS")


def test_a_trailing_semicolon_still_goes():
    assert _strip_fences("```sql\nSELECT 1;\n```") == "SELECT 1"


def test_insufficient_survives_untouched():
    """`generate_sql` compares against this exact word to decide whether to
    retry, so it must not be mangled into something else."""
    assert _strip_fences("INSUFFICIENT") == "INSUFFICIENT"
    assert _strip_fences("  INSUFFICIENT  ") == "INSUFFICIENT"


# -------------------------------------------------------------- safety

def test_a_write_hidden_behind_prose_is_not_skipped_past():
    """The regression this fix could have introduced.

    If the text before the SELECT were treated as prose and dropped, the
    DELETE would vanish and the remaining SELECT would pass every check.
    """
    reply = "DELETE FROM t;\nSELECT 1 FROM dual"
    with pytest.raises(UnsafeSQL):
        check_read_only(reply)


def test_a_forbidden_word_in_the_prefix_keeps_the_prefix():
    reply = "DROP TABLE t\nSELECT 1"
    with pytest.raises(UnsafeSQL):
        check_read_only(reply)


def test_a_second_statement_after_the_select_is_still_caught():
    with pytest.raises(UnsafeSQL):
        check_read_only("```sql\nSELECT 1; DELETE FROM t\n```")


def test_a_write_inside_the_fence_is_still_caught():
    with pytest.raises(UnsafeSQL):
        check_read_only("Here you go:\n```sql\nDELETE FROM t\n```")


def test_prose_with_no_sql_at_all_is_still_rejected():
    with pytest.raises(UnsafeSQL):
        check_read_only("I cannot answer this from the tables given.")


def test_the_first_fenced_block_is_the_one_used_and_it_is_still_checked():
    """Taking the first block is not a way past the checks -- whatever comes
    back is validated in full."""
    with pytest.raises(UnsafeSQL):
        check_read_only("```sql\nUPDATE t SET a=1\n```\n```sql\nSELECT 1\n```")


def test_an_empty_fence_is_rejected_rather_than_passed_through():
    with pytest.raises(UnsafeSQL):
        check_read_only("```sql\n\n```")


# ---------------------------------------------------- end to end shapes

@pytest.mark.parametrize("reply", [
    "```sql\nSELECT c.status, COUNT(*) FROM contact c GROUP BY c.status\n```",
    "Sure.\n```\nSELECT c.status FROM contact c\n```\nLet me know.",
    "SELECT 1 FROM dual",
    "Thinking about it, the join is on id.\nSELECT 1 FROM dual",
])
def test_shapes_a_model_actually_replies_in_all_survive(reply):
    assert check_read_only(reply).lower().startswith(("select", "with"))
