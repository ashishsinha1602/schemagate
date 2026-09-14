"""Record a real answer for every question the demo offers.

The landing page selects tables in the browser and then stops: it says "no
model is called on this page", which is true and also means a visitor never
sees the thing working. They see a list of table names and are asked to
imagine the rest.

So run the whole pipeline for real, once, here -- select with schemagate,
write SQL with Claude, execute it against the bundled SQLite demo, keep the
rows -- and ship the result with the page. The demo then completes the loop
for anyone who clicks, with no key and no server, and every SQL statement and
every row on it is one this pipeline actually produced.

Recorded, not faked, and the page has to say so.
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
sys.path.insert(0, str(SG / "src"))

from schemagate import Catalog, Principal                   # noqa: E402
from schemagate import demo_schema as ds                    # noqa: E402
from schemagate.answer import UnsafeSQL, generate_sql       # noqa: E402
from schemagate.ai.providers import AnthropicProvider       # noqa: E402

MODEL = os.environ.get("SG_MODEL", "claude-opus-5")
OUT = HERE / "answers.json"
MAX_ROWS = 8            # enough to look real, small enough to ship in the page


DB = pathlib.Path(tempfile.gettempdir()) / "schemagate_demo_answers.db"


def build_db():
    """On disk, not in memory: reflection needs a SQLAlchemy engine, and an
    engine opens its own connection -- a `:memory:` database built on one
    connection is invisible to the next."""
    DB.unlink(missing_ok=True)
    con = sqlite3.connect(DB)
    con.executescript(ds.DDL)
    con.executescript(ds.SEED)
    con.commit()
    return con


def run_sql(con, sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchmany(MAX_ROWS + 1)
    more = len(rows) > MAX_ROWS
    return cols, [list(r) for r in rows[:MAX_ROWS]], more


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set"); return 1

    # One source of truth: demo_schema.py -> studio/schemas.json -> the page.
    # Read the same file the page is generated from, so a question cannot be
    # recorded that nobody is offered, and nothing here parses HTML.
    spec = json.loads((SG / "studio" / "schemas.json").read_text("utf-8"))["commerce"]
    questions = list(spec["questions"])

    con = build_db()
    n_rows = con.execute("SELECT COUNT(*) FROM sales_order").fetchone()[0]
    print("demo db: %d sales_order rows" % n_rows)

    # sample_values: the model wrote `status = 'captured'` for a column
    # whose only value is 'settled', and the query returned nothing. Showing
    # it the real values is the whole reason this option exists, so the demo
    # should be generated the way the docs tell people to run it.
    cat = Catalog().bootstrap("sqlite:///" + DB.as_posix(), sample_values=True)
    for t, h in (spec.get("hints") or {}).items():
        try:
            cat.hint(t, h)
        except Exception:                                    # noqa: BLE001
            pass
    print("catalogue: %d objects\n" % len(list(cat.objects())))

    # Restrict exactly as the page does, so a recording made here cannot show
    # rows the page would have withheld.
    for table, roles in (spec.get("restrict") or {}).items():
        try:
            cat.restrict(table, roles)
        except Exception:                                    # noqa: BLE001
            print("  ! restrict(%s) did not resolve" % table)

    # (question, roles) pairs. Roles matter for exactly one question -- the one
    # the intro tells people to ask -- and that question is the whole point of
    # the page, so it cannot be the one with no answer.
    jobs = [(q, ()) for q in questions]
    jobs.append(("salary by employee", ("payroll",)))
    jobs.append(("salary by employee", ()))

    prov = AnthropicProvider(model=MODEL)
    out, ok = {}, 0
    for i, (q, roles) in enumerate(jobs, 1):
        t0 = time.time()
        who = Principal("okta:analyst", roles=set(roles)) if roles is not None else None
        sel = cat.select(q, top_k=8, principal=who)
        key = q if not roles else q + " |roles=" + ",".join(sorted(roles))
        try:
            sql = generate_sql(prov, q, sel.prompt_fragment(), dialect="SQLite")
        except UnsafeSQL as e:
            print("  %2d/%d  REFUSED  %-46s %s" % (i, len(jobs), q[:46], str(e)[:30]))
            out[key] = {"error": "refused", "detail": str(e)[:160],
                      "tables": [o["name"] for o in sel.object_list]}
            continue
        except Exception as e:                               # noqa: BLE001
            print("  %2d/%d  ERROR    %-46s %s" % (i, len(jobs), q[:46], type(e).__name__))
            out[key] = {"error": type(e).__name__, "detail": str(e)[:160]}
            continue
        try:
            cols, rows, more = run_sql(con, sql)
        except Exception as e:                               # noqa: BLE001
            print("  %2d/%d  SQL FAIL %-46s %s" % (i, len(jobs), q[:46],
                                                   str(e).splitlines()[0][:34]))
            out[key] = {"sql": sql, "error": "sql_failed",
                      "detail": str(e).splitlines()[0][:160],
                      "tables": [o["name"] for o in sel.object_list]}
            continue
        ok += 1
        out[key] = {"sql": sql, "columns": cols, "rows": rows, "more": more,
                  "tables": [o["name"] for o in sel.object_list],
                  "ms": int(1000 * (time.time() - t0))}
        print("  %2d/%d  ok       %-46s %d cols x %d rows  %.0fs"
              % (i, len(jobs), q[:46], len(cols), len(rows), time.time() - t0))

    OUT.write_text(json.dumps({"model": MODEL, "dialect": "SQLite",
                               "generated": time.strftime("%Y-%m-%d"),
                               "answers": out}, indent=1), "utf-8")
    print("\n  %d/%d answered with rows -> %s (%d KB)"
          % (ok, len(jobs), OUT.name, OUT.stat().st_size // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
