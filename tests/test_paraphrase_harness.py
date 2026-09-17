"""The eval harness has to reflect every schema it claims to.

`build()` opened a bare sqlite3 connection and ran the DDL through
executescript. `schema_fixture_complex` declares three ATTACHed schemas and
puts four objects in them, so the first qualified CREATE raised

    sqlite3.OperationalError: unknown database "billing"

and killed the run after the per-schema rows and before TUNE / HELD OUT /
OVERALL -- so the held-out aggregate, the only number in the harness worth
reading, had never been printed.

The obvious repair is worse than the bug. ATTACH ':memory:' makes the DDL
succeed and the databases are then dropped when that connection closes, while
bootstrap opens a new one. Measured on this checkout: **256 objects instead of
260, every one in `main`, none named `account`, and no error raised.** The
three tables called `account` in three different schemas are the whole reason
the fixture exists -- the harness would have gone on printing a number with
its hardest case quietly removed.

These assert the shape that failure destroys.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

run_paraphrase_eval = pytest.importorskip(
    "run_paraphrase_eval", reason="eval harness not in this tree")
import schema_fixture_complex as complex_                    # noqa: E402


@pytest.fixture(scope="module")
def complex_catalog():
    return run_paraphrase_eval.build("complex")


def test_every_declared_schema_is_indexed(complex_catalog):
    """ATTACHED_SCHEMAS is the fixture's own declaration of what it holds."""
    seen = {d.schema for d in complex_catalog.objects()}
    for schema in complex_.ATTACHED_SCHEMAS:
        assert schema in seen, (
            "%r declared in ATTACHED_SCHEMAS but nothing from it was indexed; "
            "seen: %s" % (schema, sorted(x for x in seen if x)))


def test_the_attached_objects_are_actually_there(complex_catalog):
    by_schema = Counter(d.schema for d in complex_catalog.objects())
    assert by_schema["main"] == 256, by_schema
    assert by_schema["billing"] == 2, by_schema
    assert by_schema["crm"] == 1, by_schema
    assert by_schema["sec"] == 1, by_schema
    assert sum(by_schema.values()) == 260, by_schema


def test_three_tables_are_named_account(complex_catalog):
    """The point of the fixture: one bare name, three schemas, one of them
    restricted. Lose these and the hard case is gone but the score is not."""
    accounts = [d for d in complex_catalog.objects()
                if d.name.split(".")[-1] == "account"]
    assert len(accounts) >= 3, [d.name for d in complex_catalog.objects()][:10]
    assert len({d.schema for d in accounts}) >= 3, \
        "expected `account` in three distinct schemas, got %s" % (
            sorted(d.schema for d in accounts),)


def test_the_view_over_the_attached_schema_survives(complex_catalog):
    assert any(d.name.endswith("v_at_risk_accounts")
               for d in complex_catalog.objects())


def test_main_reports_an_aggregate(capsys):
    """It died before this line for as long as the harness has existed."""
    run_paraphrase_eval.main(show_misses=())
    out = capsys.readouterr().out
    for line in ("TUNE", "HELD OUT", "OVERALL"):
        assert line in out, out[-400:]


def test_it_says_which_embedder_produced_the_numbers(capsys):
    """Same questions, same fixtures: 58.6% overall on the hashed vectoriser
    and 82.8% with sentence-transformers. A figure without the embedder beside
    it is not reproducible."""
    run_paraphrase_eval.main(show_misses=())
    out = capsys.readouterr().out
    assert out.startswith("embedder: "), out[:120]
    assert out.splitlines()[0].split("embedder: ", 1)[1].strip(), "no embedder named"
