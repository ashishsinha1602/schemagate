"""Measure business-language recall on every schema. Prints a table + misses."""
from __future__ import annotations
import os
import sys
import tempfile

import sqlalchemy as sa
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from schemagate import Catalog
import paraphrase_eval as EV

import schema_fixture_health as health
import schema_fixture_warehouse as warehouse
import schema_fixture_finance as finance
import schema_fixture_telemetry as telemetry
import schema_fixture_complex as complex_
from schemagate import demo_schema as commerce

MODS = {"commerce": commerce, "health": health, "warehouse": warehouse,
        "finance": finance, "telemetry": telemetry, "complex": complex_}


def _engine(ddl, attached):
    """A SQLite engine with `attached` extra schemas on every connection.

    Files, not ':memory:'. ATTACH is per-connection and an in-memory database
    dies with the connection that made it, so the weights of this fixture --
    three tables all called `account`, in three schemas -- were being created
    and then silently dropped before bootstrap ever looked. Measured: 256
    objects instead of 260, all in `main`, none named `account`, and no error
    raised. Statement-by-statement rather than executescript, because the
    ATTACHes have to be in place before the first qualified CREATE runs.

    Same shape as tests/test_complex_schema.py::_build_sqlite, deliberately:
    two builders for one fixture is how they drift.
    """
    base = tempfile.mkdtemp()
    eng = sa.create_engine("sqlite:///" + os.path.join(base, "main.db"))

    if attached:
        @sa.event.listens_for(eng, "connect")
        def _attach(dbapi_connection, _record):
            for schema in attached:
                dbapi_connection.execute(
                    f"ATTACH DATABASE '{os.path.join(base, schema)}.db' AS {schema}")

    with eng.begin() as conn:
        for statement in ddl.split(";\n"):
            if statement.strip():
                conn.exec_driver_sql(statement)
    return eng


def build(name, use_hints=True, use_desc=False):
    m = MODS[name]
    attached = list(getattr(m, "ATTACHED_SCHEMAS", []))
    eng = _engine(m.DDL, attached)
    cat = Catalog(name=name).bootstrap(eng, schemas=["main"] + attached if attached else None)
    if use_hints:
        for t, h in getattr(m, "HINTS", {}).items():
            try: cat.hint(t, h)
            except Exception: pass
    if use_desc:
        # This parameter existed and did nothing. Anyone who passed
        # use_desc=True got a catalog with no descriptions on it and would
        # have concluded the AI catalogue was not worth much -- the opposite
        # of what tests/test_business_language.py measures with the same
        # fixtures (56% on identifiers alone, 92% with descriptions).
        path = os.path.join(HERE, "descriptions", f"{name}.json")
        if os.path.exists(path):
            import json
            with open(path, encoding="utf-8") as fh:
                cat.describe(json.load(fh), only_missing=False)
    cat.index()
    return cat


def score(cat, questions, top_k=6, show=False):
    hits, misses = 0, []
    for q, gold in questions:
        got = {n.split(".")[-1] for n in cat.select(q, top_k=top_k).table_names}
        if gold & got:
            hits += 1
        else:
            misses.append((q, sorted(gold), sorted(got)[:6]))
    if show:
        for q, gold, got in misses:
            print(f"    MISS  {q!r}\n          want {gold}\n          got  {got}")
    return hits, len(questions), misses


def _embedder_name():
    """Whichever one a Catalog would actually pick here."""
    try:
        return Catalog(name="_probe").embedder.name
    except Exception:                                        # noqa: BLE001
        return "unknown"


def main(show_misses=("commerce", "health")):
    # Which embedder, said out loud. The same questions score 58.6% overall on
    # the hashed vectoriser that `pip install schemagate` gives you and 82.8%
    # with sentence-transformers installed -- so a number from this harness
    # means nothing without knowing which of the two produced it.
    print(f"embedder: {_embedder_name()}"
          f"   (SCHEMAGATE_AUTO_EMBEDDER=0 forces the built-in hashed one)")
    print(f"{'schema':<12}{'set':<9}{'recall@6':>10}   {'hit/total':>10}")
    print("-" * 46)
    tot_h = tot_n = 0
    per = {}
    for name, qs in EV.ALL.items():
        cat = build(name)
        kind = "TUNE" if name in EV.TUNE else "HELDOUT"
        h, n, misses = score(cat, qs, show=(name in show_misses))
        per[name] = (h, n, misses)
        tot_h += h; tot_n += n
        print(f"{name:<12}{kind:<9}{h/n*100:9.1f}%   {h:>4}/{n:<5}")
    print("-" * 46)
    th = sum(per[k][0] for k in EV.TUNE); tn = sum(per[k][1] for k in EV.TUNE)
    hh = sum(per[k][0] for k in EV.HELDOUT); hn = sum(per[k][1] for k in EV.HELDOUT)
    print(f"{'TUNE':<21}{th/tn*100:9.1f}%   {th:>4}/{tn:<5}")
    print(f"{'HELD OUT':<21}{hh/hn*100:9.1f}%   {hh:>4}/{hn:<5}")
    print(f"{'OVERALL':<21}{tot_h/tot_n*100:9.1f}%   {tot_h:>4}/{tot_n:<5}")
    return per


if __name__ == "__main__":
    main()
