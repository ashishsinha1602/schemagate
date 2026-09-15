"""Record a real answer for every question the demo offers, on every schema.

The page selects tables in the browser and then stops: a static page cannot
call a model, and an API key in a public page is a key anyone can spend. So
the whole pipeline is run once, here -- select with schemagate, write SQL with
a real model, execute it, keep the rows -- and the result ships with the page.
The demo then finishes a question for anybody who clicks, with no key and no
server, and every statement and every row on it was produced by this pipeline.

Recorded, not faked, and the page says so.

All six schemas, not one. The first version of this recorded only `commerce`,
so five sixths of the suggested questions led to "no answer was recorded for
that wording" -- a button that does nothing, which is worse than no button.
The other five ship as DDL with no rows, so studio/seed_fixtures.py fills them
first.

    python studio/build_answers.py                 # everything
    python studio/build_answers.py clinical        # one schema

Needs ANTHROPIC_API_KEY. ~98 questions, a few seconds each.
"""
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent      # studio/
SG = HERE.parent                                    # the repo root
sys.path[:0] = [str(SG / "src"), str(SG / "tests"), str(HERE)]

from seed_fixtures import seed                               # noqa: E402
from schemagate import Catalog, Principal                    # noqa: E402
from schemagate.answer import UnsafeSQL, generate_sql        # noqa: E402
from schemagate.ai.providers import AnthropicProvider        # noqa: E402

MODEL = os.environ.get("SG_MODEL", "claude-opus-5")
OUT = HERE / "answers.json"
MAX_ROWS = 8            # enough to look real, small enough to ship in the page


def _ddl_for(key):
    """The DDL and any attached schemas for one demo database."""
    if key == "commerce":
        from schemagate import demo_schema as ds
        return ds.DDL, ds.SEED, []
    mods = {"clinical": "schema_fixture_health", "warehouse": "schema_fixture_warehouse",
            "finance": "schema_fixture_finance", "telemetry": "schema_fixture_telemetry",
            "hostile": "schema_fixture_complex"}
    if key not in mods:
        return None, None, []
    mod = __import__(mods[key])
    return mod.DDL, None, list(getattr(mod, "ATTACHED_SCHEMAS", []))


def build_db(key, path):
    """A SQLite file with this schema and rows in it."""
    ddl, canned, attached = _ddl_for(key)
    if ddl is None:
        return None
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    for s in attached:
        con.execute("ATTACH DATABASE ? AS %s" % s, (str(path.with_name(path.stem + "_" + s + ".db")),))
    # The complex fixture is one statement per line-group, not a single script.
    for stmt in ddl.split(";\n"):
        if stmt.strip():
            try:
                con.execute(stmt)
            except sqlite3.Error:
                pass
    con.commit()
    if canned:                      # commerce ships its own deterministic rows
        con.executescript(canned)
        con.commit()
    else:
        for s in ["main"] + attached:
            seed(con, s)
    return con


def run_sql(con, sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchmany(MAX_ROWS + 1)
    return cols, [list(r) for r in rows[:MAX_ROWS]], len(rows) > MAX_ROWS


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set"); return 1

    schemas = json.loads((HERE / "schemas.json").read_text("utf-8"))
    only = sys.argv[1:] or list(schemas)
    # Start clean when rebuilding everything; keep only other schemas'
    # entries when rebuilding one, and never keep flat (unscoped) keys.
    out = {}
    if OUT.is_file() and sys.argv[1:]:
        prev = json.loads(OUT.read_text("utf-8"))["answers"]
        out = {k: v for k, v in prev.items()
               if "::" in k and k.split("::", 1)[0] not in only}
    prov = AnthropicProvider(model=MODEL)
    tmp = pathlib.Path(tempfile.gettempdir())
    total = ok = 0

    for key in only:
        spec = schemas.get(key)
        if not spec:
            print("  no such schema: %s" % key); continue
        con = build_db(key, tmp / ("sg_demo_%s.db" % key))
        if con is None:
            print("  %s: no fixture, skipped" % key); continue
        nrows = sum(r[0] for r in con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"))
        url = "sqlite:///" + (tmp / ("sg_demo_%s.db" % key)).as_posix()
        cat = Catalog().bootstrap(url, sample_values=True)
        for t, h in (spec.get("hints") or {}).items():
            try:
                cat.hint(t, h)
            except Exception:                                # noqa: BLE001
                pass
        for t, roles in (spec.get("restrict") or {}).items():
            try:
                cat.restrict(t, roles)
            except Exception:                                # noqa: BLE001
                pass
        print("\n%s: %d objects, %d tables" % (key, len(list(cat.objects())), nrows))

        jobs = [(q, ()) for q in spec.get("questions", [])]
        if key == "commerce":            # the intro's own question, both ways
            jobs += [("salary by employee", ("payroll",)), ("salary by employee", ())]

        for i, (q, roles) in enumerate(jobs, 1):
            total += 1
            t0 = time.time()
            who = Principal("okta:analyst", roles=set(roles))
            sel = cat.select(q, top_k=8, principal=who)
            # Keyed by schema as well as question. Two schemas ask "paid
            # amount per claim line" and "members with chronic conditions"
            # in exactly those words, and a flat key meant whichever ran last
            # won -- so one schema's page would show the other schema's rows.
            rec_key = key + "::" + q
            if roles:
                rec_key += " |roles=" + ",".join(sorted(roles))
            try:
                sql = generate_sql(prov, q, sel.prompt_fragment(), dialect="SQLite")
            except UnsafeSQL as e:
                out[rec_key] = {"schema": key, "error": "refused", "detail": str(e)[:160],
                                "tables": [o["name"] for o in sel.object_list]}
                print("  %2d/%d REFUSED  %s" % (i, len(jobs), q[:44])); continue
            except Exception as e:                           # noqa: BLE001
                out[rec_key] = {"error": type(e).__name__, "detail": str(e)[:160]}
                print("  %2d/%d ERROR    %s  %s" % (i, len(jobs), q[:44], type(e).__name__)); continue
            try:
                cols, rows, more = run_sql(con, sql)
            except Exception as e:                           # noqa: BLE001
                out[rec_key] = {"schema": key, "sql": sql, "error": "sql_failed",
                                "detail": str(e).splitlines()[0][:160],
                                "tables": [o["name"] for o in sel.object_list]}
                print("  %2d/%d SQLFAIL  %s  %s" % (i, len(jobs), q[:44],
                                                    str(e).splitlines()[0][:34])); continue
            ok += 1
            out[rec_key] = {"schema": key, "sql": sql, "columns": cols, "rows": rows,
                            "more": more, "tables": [o["name"] for o in sel.object_list],
                            "ms": int(1000 * (time.time() - t0))}
            print("  %2d/%d ok       %-44s %dx%d" % (i, len(jobs), q[:44], len(cols), len(rows)))
        con.close()

    OUT.write_text(json.dumps({"model": MODEL, "dialect": "SQLite",
                               "generated": time.strftime("%Y-%m-%d"),
                               "answers": out}, indent=1), "utf-8")
    print("\n  %d/%d answered with rows -> %s (%d KB)"
          % (ok, total, OUT.name, OUT.stat().st_size // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
