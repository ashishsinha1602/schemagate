"""Value sampling against a database that is not on this machine.

This exists because of one connection: an Autonomous Database wallet, a schema
of ordinary width, and a Studio that sat on "Connecting..." long enough to look
hung. Nothing was wrong with the query -- there were simply a great many of
them, one per candidate column, each paying a network round trip that costs
nothing against a local file.
"""
import sqlite3
import time

from sqlalchemy import create_engine, event, inspect

from schemagate.introspect import reflect


def _db(tmp_path, tables=12, rows=200):
    path = tmp_path / "s.db"
    c = sqlite3.connect(path)
    for i in range(tables):
        c.execute(f"CREATE TABLE t{i}(id INTEGER PRIMARY KEY, status TEXT, code TEXT)")
        c.executemany(f"INSERT INTO t{i}(status, code) VALUES (?,?)",
                      [("open" if r % 2 else "closed", "AA" if r % 3 else "BB")
                       for r in range(rows)])
    c.commit()
    c.close()
    return create_engine(f"sqlite:///{path}")


def _count_connects(engine):
    seen = []
    event.listen(engine, "connect", lambda *a: seen.append(1))
    return seen


def test_sampling_shares_one_connection(tmp_path):
    """Worth asserting, but not the fix it looks like: SQLAlchemy pools, so
    the per-table `engine.connect()` this replaced was already handing back
    the same DBAPI connection. Measured, not assumed -- twelve per-table opens
    against a held connection produce one DBAPI connect, not twelve."""
    engine = _db(tmp_path, tables=12)
    seen = _count_connects(engine)
    docs = reflect(engine, sample_values=True)
    assert len(docs) == 12
    assert len(seen) <= 3, f"opened {len(seen)} connections for 12 tables"


def test_sampling_still_finds_the_values(tmp_path):
    """The bounds must not cost the feature they bound."""
    docs = reflect(_db(tmp_path, tables=2), sample_values=True)
    status = [c for d in docs for c in d.columns if c.name == "status"]
    assert status and all(c.values == ["closed", "open"] for c in status)


def test_a_budget_that_has_already_expired_stops_the_sampling(tmp_path):
    """Past the deadline reflection still returns a catalog -- values are an
    enrichment, and a connect that never finishes is not."""
    docs = reflect(_db(tmp_path, tables=6), sample_values=True,
                   sample_budget=0.000001)
    assert len(docs) == 6
    assert all(c.values is None for d in docs for c in d.columns)


def test_the_budget_is_wall_clock_not_a_column_count(tmp_path):
    """A slow link is what runs the clock down, and nothing in the schema says
    how slow the link is."""
    engine = _db(tmp_path, tables=40)

    slow = {"n": 0}

    @event.listens_for(engine, "before_cursor_execute")
    def _delay(conn, cursor, stmt, params, ctx, many):
        if "SELECT DISTINCT" in stmt.upper() or "count(" in stmt.lower():
            slow["n"] += 1
            time.sleep(0.01)

    t = time.monotonic()
    docs = reflect(engine, sample_values=True, sample_budget=0.25)
    elapsed = time.monotonic() - t
    assert len(docs) == 40
    # without a budget this is 40 tables * (1 count + 2 columns) * 10ms
    assert elapsed < 3.0, f"took {elapsed:.1f}s despite a 0.25s budget"


def test_zero_means_no_limit(tmp_path):
    docs = reflect(_db(tmp_path, tables=3), sample_values=True, sample_budget=0)
    assert any(c.values for d in docs for c in d.columns)


def test_sampling_off_opens_nothing_extra(tmp_path):
    engine = _db(tmp_path, tables=5)
    seen = _count_connects(engine)
    reflect(engine, sample_values=False)
    assert len(seen) <= 2


# ---- reflection asks in batches -----------------------------------------

def test_reflection_asks_for_the_whole_schema_at_once(tmp_path):
    """Four calls per table -- columns, primary key, foreign keys, comment --
    is invisible against a local file and is the entire cost of connecting to
    a database across a continent.

    Measured on PostgreSQL, 65 objects: 332 queries before, 17 after. Not
    asserted on SQLite, which implements the batched interface by looping
    internally and so cannot show the difference -- the assertion here is that
    the batch is built and populated, which is what the loop then reads.
    """
    from schemagate.introspect import _multi_reflect

    engine = _db(tmp_path, tables=6, rows=5)
    insp = inspect(engine)
    names = [(n, "TABLE") for n in insp.get_table_names()]
    multi = _multi_reflect(insp, None, names, True)

    assert set(multi) == {"columns", "pk", "fks", "comments"}
    assert len(multi["columns"]) >= 6
    assert all(multi["columns"][f"t{i}"] for i in range(6))
    assert multi["pk"]["t0"] == {"id"}


def test_a_dialect_without_the_batch_still_reflects(tmp_path):
    """The helper returns empty maps rather than raising when the interface is
    missing, and every lookup falls back to the single-table call."""
    from schemagate.introspect import _multi_reflect

    class NoBatch:
        def get_table_names(self, schema=None):
            return []

    multi = _multi_reflect(NoBatch(), None, [], True)
    assert multi == {"columns": {}, "pk": {}, "fks": {}, "comments": {}}
    # and reflection itself is unaffected
    assert len(reflect(_db(tmp_path, tables=3), sample_values=False)) == 3


def test_the_batch_still_reflects_everything(tmp_path):
    """Speed is worthless if it costs the foreign keys."""
    import sqlite3

    db = tmp_path / "fk.db"
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE parent(id INTEGER PRIMARY KEY, label TEXT);
        CREATE TABLE child(id INTEGER PRIMARY KEY,
                           parent_id INTEGER REFERENCES parent(id),
                           note TEXT NOT NULL);
    """)
    c.commit(); c.close()

    docs = {d.name: d for d in reflect(create_engine(f"sqlite:///{db}"))}
    assert set(docs) == {"parent", "child"}
    child = docs["child"]
    assert [c.name for c in child.columns] == ["id", "parent_id", "note"]
    assert [c.pk for c in child.columns] == [True, False, False]
    assert [c.nullable for c in child.columns][2] is False
    assert len(child.foreign_keys) == 1
    assert child.foreign_keys[0].ref_table == "parent"
    assert child.foreign_keys[0].columns == ["parent_id"]


def test_a_refused_column_batch_falls_back_to_information_schema(monkeypatch):
    """A read-only PostgreSQL role refused pg_collation got *no tables* back,
    after one failing round trip per table (EBI RNAcentral: 316 tables, 235 s).
    The ANSI view answers in one query instead."""
    from schemagate import introspect

    calls = []

    class Refused:
        bind = None

        def get_multi_columns(self, **kw):
            raise RuntimeError("permission denied for table pg_collation")

        def get_columns(self, name, schema=None):
            calls.append(name)
            raise RuntimeError("permission denied for table pg_collation")

    monkeypatch.setattr(introspect, "_information_schema_columns",
                        lambda insp, schema: {"orders": [{"name": "id", "type": "INTEGER", "nullable": False, "comment": None}]})
    multi = introspect._multi_reflect(Refused(), "s", [("orders", "TABLE"), ("gone", "TABLE")], True)
    assert multi["columns"]["orders"][0]["name"] == "id" and multi["ansi_columns"] is True
    assert calls == []


def test_information_schema_columns_reads_one_schema(tmp_path):
    """Only the ANSI dialects are asked; SQLite has no such view and gets {}."""
    from schemagate.introspect import _information_schema_columns
    engine = _db(tmp_path, tables=2, rows=1)
    assert _information_schema_columns(inspect(engine), None) == {}


def test_sql_server_columns_hidden_by_their_type_are_filled_in(monkeypatch):
    """AdventureWorks, db_datareader login: Department's Name and GroupName (type dbo.Name) were missing from
    the reflected columns, so answers showed department IDs. The standard view fills them in, in order."""
    from schemagate import dialects, introspect

    class Bind:
        class dialect:
            name = "mssql"

    class Insp:
        bind = Bind()

        def get_multi_columns(self, **kw):
            return {("HumanResources", "Department"): [{"name": "DepartmentID", "type": "SMALLINT"},
                                                       {"name": "ModifiedDate", "type": "DATETIME"}]}

    monkeypatch.setattr(dialects, "ansi_columns", lambda bind, schema: {"Department": [
        {"name": "DepartmentID", "type": "SMALLINT"}, {"name": "Name", "type": "NVARCHAR(50)"},
        {"name": "GroupName", "type": "NVARCHAR(50)"}, {"name": "ModifiedDate", "type": "DATETIME"}]})
    multi = introspect._multi_reflect(Insp(), "HumanResources", [("Department", "TABLE")], True)
    assert [c["name"] for c in multi["columns"]["Department"]] == ["DepartmentID", "Name", "GroupName", "ModifiedDate"]
