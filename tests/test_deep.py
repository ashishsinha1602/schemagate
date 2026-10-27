"""deep_answer: the model works in steps, and every step's SQL goes through the caller's checks."""
import pytest

from schemagate import mcp_server
from schemagate.deep import ExploreCache, _parse, adaptive_answer, deep_answer


class Script:
    """Replies in order; records every prompt it was sent."""

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def complete(self, system, prompt, max_tokens=1024):
        self.prompts.append(prompt)
        return self.replies.pop(0) if self.replies else "INSUFFICIENT"


class FakeDB:
    """run(sql, limit): answers by substring, records what it was asked."""

    def __init__(self, table):
        self.table, self.ran = table, []

    def __call__(self, sql, limit):
        self.ran.append((sql, limit))
        for key, out in self.table.items():
            if key in sql:
                out = dict(out)
                rows = out.get("rows", [])
                out["truncated"] = len(rows) > limit
                out["rows"] = rows[:limit]
                return out
        return {"error": "no such table"}


DDL = "CREATE TABLE customer (id INT, country TEXT)"


# --- parsing ----------------------------------------------------------------------------------

@pytest.mark.parametrize("reply, kind, note, body", [
    ("EXPLORE: country codes\nSELECT DISTINCT country FROM customer", "EXPLORE", "country codes",
     "SELECT DISTINCT country FROM customer"),
    ("FINAL: SELECT 1", "FINAL", "", "SELECT 1"),
    ("**FINAL**: count\nSELECT count(*) FROM customer", "FINAL", "count", "SELECT count(*) FROM customer"),
    ("TABLES: orders", "TABLES", "orders", ""),
    ("SELECT id FROM customer", "FINAL", "", "SELECT id FROM customer"),
    ("INSUFFICIENT", "INSUFFICIENT", "", ""),
    ("I think we should look at it", "UNKNOWN", "", "I think we should look at it"),
])
def test_parse(reply, kind, note, body):
    assert _parse(reply) == (kind, note, body)


# --- the loop ---------------------------------------------------------------------------------

def test_plain_question_takes_one_call():
    model = Script("FINAL: all ids\nSELECT id FROM customer")
    db = FakeDB({"SELECT id": {"columns": ["id"], "rows": [[1], [2]]}})
    res = deep_answer(model, "ids", DDL, db)
    assert res.rows == [[1], [2]] and res.sql == "SELECT id FROM customer"
    assert len(res.steps) == 1 and res.error is None


def test_explore_shows_real_values_then_answers():
    model = Script("EXPLORE: how is Germany written\nSELECT DISTINCT country FROM customer",
                   "FINAL: German customers\nSELECT id FROM customer WHERE country = 'DE'")
    db = FakeDB({"DISTINCT country": {"columns": ["country"], "rows": [["DE"], ["FR"]]},
                 "'DE'": {"columns": ["id"], "rows": [[7]]}})
    res = deep_answer(model, "customers in Germany", DDL, db)
    assert res.rows == [[7]]
    # the second prompt carried the explored values
    assert "DE" in model.prompts[1] and "FR" in model.prompts[1]
    assert [s["kind"] for s in res.steps] == ["explore", "final"]


def test_explore_is_capped_at_preview_rows():
    model = Script("EXPLORE: look\nSELECT country FROM customer", "FINAL: x\nSELECT id FROM customer")
    db = FakeDB({"SELECT country": {"columns": ["country"], "rows": [[i] for i in range(50)]},
                 "SELECT id": {"columns": ["id"], "rows": [[1]]}})
    deep_answer(model, "q", DDL, db, preview_rows=5)
    assert db.ran[0][1] == 5
    assert "more not shown" in model.prompts[1]


def test_rejected_query_is_handed_back_with_the_message():
    model = Script("FINAL: x\nSELECT nme FROM customer", "FINAL: x\nSELECT id FROM customer")
    db = FakeDB({"nme": {"error": "no such column: nme"}, "SELECT id": {"columns": ["id"], "rows": [[1]]}})
    res = deep_answer(model, "q", DDL, db)
    assert "no such column: nme" in model.prompts[1]
    assert res.rows == [[1]] and res.steps[0]["outcome"] == "no such column: nme"


def test_a_refusal_from_run_is_not_retried_into_success_silently():
    """run() refusing a table (scope) is just a rejected step: the model sees the refusal, never the rows."""
    model = Script("FINAL: x\nSELECT * FROM secret", "INSUFFICIENT")
    db = FakeDB({"secret": {"error": "secret is not available to this caller"}})
    res = deep_answer(model, "q", DDL, db)
    assert res.sql is None and res.rows == []
    assert "not available to this caller" in model.prompts[1]


def test_empty_final_is_questioned_once_then_accepted():
    model = Script("FINAL: x\nSELECT id FROM customer WHERE country = 'Germany'",
                   "FINAL: x\nSELECT id FROM customer WHERE country = 'Germany'")
    db = FakeDB({"Germany": {"columns": ["id"], "rows": []}})
    res = deep_answer(model, "q", DDL, db)
    assert "returned no rows" in model.prompts[1]
    assert res.sql and res.rows == [] and res.error is None and len(res.steps) == 2


def test_a_zero_count_is_questioned_like_an_empty_result():
    model = Script("FINAL: x\nSELECT count(*) FROM customer WHERE country = 'Germany'",
                   "EXPLORE: values\nSELECT DISTINCT country FROM customer",
                   "FINAL: x\nSELECT count(*) FROM customer WHERE country = 'DE'")
    db = FakeDB({"'Germany'": {"columns": ["n"], "rows": [[0]]},
                 "DISTINCT": {"columns": ["country"], "rows": [["DE"]]},
                 "'DE'": {"columns": ["n"], "rows": [[4]]}})
    res = deep_answer(model, "how many in Germany", DDL, db)
    assert "only zero or NULL" in model.prompts[1] and res.rows == [[4]]


def test_tables_step_adds_only_what_more_tables_returns():
    model = Script("TABLES: orders", "FINAL: x\nSELECT id FROM orders")
    db = FakeDB({"orders": {"columns": ["id"], "rows": [[3]]}})
    res = deep_answer(model, "q", DDL, db, more_tables=lambda topic: "CREATE TABLE orders (id INT)")
    assert "CREATE TABLE orders" in model.prompts[1] and res.rows == [[3]]


def test_tables_step_without_more_tables_says_none():
    model = Script("TABLES: orders", "INSUFFICIENT")
    res = deep_answer(model, "q", DDL, FakeDB({}))
    assert "no further tables" in model.prompts[1] and res.error


def test_step_budget_is_a_hard_stop_then_one_plain_query():
    model = Script(*["EXPLORE: again\nSELECT id FROM customer"] * 3, "SELECT id FROM customer")
    db = FakeDB({"SELECT id": {"columns": ["id"], "rows": [[1]]}})
    res = deep_answer(model, "q", DDL, db, max_steps=3)
    assert len(model.prompts) == 4 and "last one" in model.prompts[2]
    # out of steps: one plain query, with what exploring found as notes, instead of no answer
    assert "What was learned" in model.prompts[3]
    assert res.rows == [[1]] and res.error is None and res.steps[-1]["note"].startswith("out of steps")


def test_out_of_steps_and_the_last_query_fails_reports_why():
    model = Script(*["EXPLORE: again\nSELECT id FROM customer"] * 2, "SELECT nope FROM customer")
    db = FakeDB({"SELECT id": {"columns": ["id"], "rows": [[1]]}, "nope": {"error": "no such column"}})
    res = deep_answer(model, "q", DDL, db, max_steps=2)
    assert res.sql is None and "2 model calls" in res.error


def test_insufficient_twice_ends_it():
    model = Script("INSUFFICIENT", "INSUFFICIENT")
    res = deep_answer(model, "q", DDL, FakeDB({}))
    assert res.error and res.sql is None and len(res.steps) == 2
    assert "Check again before giving up" in model.prompts[1]


def test_first_insufficient_is_questioned_and_a_final_wins():
    model = Script("INSUFFICIENT", "FINAL: x\nSELECT id FROM customer")
    res = deep_answer(model, "q", DDL, FakeDB({"SELECT id": {"columns": ["id"], "rows": [[1]]}}))
    assert res.rows == [[1]] and res.error is None
    assert [s["kind"] for s in res.steps] == ["insufficient", "final"]


def test_insufficient_on_the_last_call_is_not_questioned():
    res = deep_answer(Script("INSUFFICIENT"), "q", DDL, FakeDB({}), max_steps=1)
    assert res.error and len(res.steps) == 1


def test_adaptive_keeps_an_empty_first_answer_when_the_steps_find_nothing():
    # a count of 0 can be right; when deep mode gives up, the executed first query still answers
    model = Script("SELECT count(*) FROM customer WHERE country = 'XX'", "INSUFFICIENT", "INSUFFICIENT")
    db = FakeDB({"'XX'": {"columns": ["n"], "rows": [[0]]}})
    res = adaptive_answer(model, "how many in XX", DDL, db)
    assert res.rows == [[0]] and res.error is None and "'XX'" in res.sql
    assert [s["kind"] for s in res.steps] == ["plain", "insufficient", "insufficient"]


def test_adaptive_gives_no_answer_when_no_query_ever_ran():
    model = Script("SELECT a FROM customer", "SELECT b FROM customer", "SELECT c FROM customer",
                   "INSUFFICIENT", "INSUFFICIENT")
    db = FakeDB({"SELECT a": {"error": "e1"}, "SELECT b": {"error": "e2"}, "SELECT c": {"error": "e3"}})
    res = adaptive_answer(model, "q", DDL, db, repairs=2)
    assert res.sql is None and res.error


# --- the MCP tool -----------------------------------------------------------------------------

@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("SCHEMAGATE_DATABASE_URL", "demo")
    monkeypatch.setenv("SCHEMAGATE_AUTO_DESCRIBE", "0")
    monkeypatch.delenv("SCHEMAGATE_CATALOG_MAX_AGE", raising=False)
    monkeypatch.delenv("SCHEMAGATE_CATALOG_CONFIG", raising=False)
    monkeypatch.delenv("SCHEMAGATE_MCP_RERANK", raising=False)
    monkeypatch.delenv("SCHEMAGATE_MCP_SEMANTIC", raising=False)

    def start(model=None, on=True):
        if on:
            monkeypatch.setenv("SCHEMAGATE_MCP_DEEP", "1")
        else:
            monkeypatch.delenv("SCHEMAGATE_MCP_DEEP", raising=False)
        monkeypatch.setattr(mcp_server, "_server_provider", lambda: model)
        mcp_server.build_catalog()
    yield start
    mcp_server._STATE["deep"] = False


def test_off_by_default_and_says_why(server):
    server(Script(), on=False)
    out = mcp_server.deep_answer("invoice lines")
    assert "SCHEMAGATE_MCP_DEEP=1" in out["error"] and mcp_server.health()["deep"] is False


def test_explore_then_final_on_the_demo(server):
    model = Script("EXPLORE: what lines look like\nSELECT id, description FROM billing_invoice_line LIMIT 3",
                   "FINAL: line ids\nSELECT id FROM billing_invoice_line")
    server(model)
    out = mcp_server.deep_answer("invoice line ids", max_rows=5, mode="deep")
    assert "error" not in out, out
    assert out["columns"] == ["id"] and out["row_count"] == 5 and out["truncated"] is True
    assert [s["kind"] for s in out["steps"]] == ["explore", "final"]
    assert "rows from each of 1 exploring" in out["sent_to_model"]
    assert mcp_server.health()["deep"] is True
    assert not any(k.startswith("_") for k in out)


def test_a_withheld_table_never_reaches_the_model(server):
    """The exploring query is refused by run_query's scope check, so its rows are never in a prompt."""
    model = Script("EXPLORE: pay\nSELECT pay_grade FROM hr_compensation", "INSUFFICIENT")
    server(model)
    out = mcp_server.deep_answer("pay grades", principal="okta:sales", roles=["sales"], mode="deep")
    assert out["sql"] is None
    assert "not available to this caller" in out["steps"][0]["outcome"]
    assert "not available to this caller" in model.prompts[1]
    assert out["sent_to_model"] == "schema only"


def test_tables_step_cannot_add_a_withheld_table(server):
    model = Script("TABLES: compensation and pay grades", "INSUFFICIENT")
    server(model)
    out = mcp_server.deep_answer("invoice totals", principal="okta:sales", roles=["sales"], mode="deep")
    assert "hr_compensation" not in " ".join(out["objects"])
    assert "hr_compensation" not in " ".join(model.prompts).lower()


def test_writes_are_refused_at_every_step(server):
    model = Script("EXPLORE: tidy\nDELETE FROM billing_invoice_line", "INSUFFICIENT")
    server(model)
    out = mcp_server.deep_answer("invoice lines", mode="deep")
    assert out["steps"][0]["outcome"].startswith("refused")


@pytest.mark.parametrize("env", [{}, {"SCHEMAGATE_MCP_PROVIDER": "anthropic"}])
def test_deep_without_a_model_stops_the_server(monkeypatch, env):
    monkeypatch.setenv("SCHEMAGATE_DATABASE_URL", "demo")
    monkeypatch.setenv("SCHEMAGATE_MCP_DEEP", "1")
    monkeypatch.delenv("SCHEMAGATE_MCP_RERANK", raising=False)
    monkeypatch.delenv("SCHEMAGATE_MCP_SEMANTIC", raising=False)
    for k in ("SCHEMAGATE_MCP_PROVIDER", "SCHEMAGATE_MCP_MODEL"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(SystemExit, match="SCHEMAGATE_MCP_DEEP=1 needs a model"):
        mcp_server.build_catalog()
    mcp_server._STATE["deep"] = False


# --- adaptive mode ----------------------------------------------------------------------------

def test_adaptive_accepts_a_good_first_answer_in_one_call():
    model = Script("SELECT id FROM customer")
    db = FakeDB({"SELECT id": {"columns": ["id"], "rows": [[1]]}})
    res = adaptive_answer(model, "ids", DDL, db)
    assert res.rows == [[1]] and len(model.prompts) == 1 and res.steps[0]["kind"] == "plain"


def test_adaptive_escalates_a_zero_count_with_the_attempt_in_the_trace():
    model = Script("SELECT count(*) FROM customer WHERE country = 'Germany'",
                   "EXPLORE: values\nSELECT DISTINCT country FROM customer",
                   "FINAL: x\nSELECT count(*) FROM customer WHERE country = 'DE'")
    db = FakeDB({"'Germany'": {"columns": ["n"], "rows": [[0]]},
                 "DISTINCT": {"columns": ["country"], "rows": [["DE"]]},
                 "'DE'": {"columns": ["n"], "rows": [[4]]}})
    res = adaptive_answer(model, "how many in Germany", DDL, db)
    assert res.rows == [[4]]
    assert [s["kind"] for s in res.steps] == ["plain", "explore", "final"]
    assert "A first attempt" in model.prompts[1] and "'Germany'" in model.prompts[1]


def test_adaptive_escalates_a_rejected_query():
    model = Script("SELECT nme FROM customer", "FINAL: x\nSELECT id FROM customer")
    db = FakeDB({"nme": {"error": "no such column: nme"}, "SELECT id": {"columns": ["id"], "rows": [[1]]}})
    res = adaptive_answer(model, "ids", DDL, db)
    assert res.rows == [[1]] and "no such column: nme" in model.prompts[1]


# --- the exploration cache --------------------------------------------------------------------

def _exploring(run):
    from schemagate.deep import EXPLORING

    def r(sql, limit):
        tok = EXPLORING.set(True)
        try:
            return run(sql, limit)
        finally:
            EXPLORING.reset(tok)
    return r


def test_cache_serves_a_repeat_explore_without_running_it():
    db = FakeDB({"DISTINCT": {"columns": ["c"], "rows": [["DE"]]}})
    run = _exploring(ExploreCache().wrap(db, scope=("okta:a", ())))
    assert run("SELECT DISTINCT c FROM t", 10)["rows"] == [["DE"]]
    assert run("SELECT  DISTINCT c\nFROM t", 10)["rows"] == [["DE"]]      # whitespace does not matter
    assert len(db.ran) == 1


def test_cache_never_crosses_callers():
    db = FakeDB({"DISTINCT": {"columns": ["c"], "rows": [["DE"]]}})
    cache = ExploreCache()
    _exploring(cache.wrap(db, scope=("okta:a", ("payroll",))))("SELECT DISTINCT c FROM t", 10)
    _exploring(cache.wrap(db, scope=("okta:b", ())))("SELECT DISTINCT c FROM t", 10)
    assert len(db.ran) == 2


def test_cache_skips_errors_and_final_sized_reads():
    db = FakeDB({"bad": {"error": "nope"}, "SELECT id": {"columns": ["id"], "rows": [[1]]}})
    cache = ExploreCache()
    run = _exploring(cache.wrap(db, scope="s"))
    run("SELECT bad", 10); run("SELECT bad", 10)
    final = cache.wrap(db, scope="s")                       # not exploring: a final answer, any size
    final("SELECT id FROM t", 5); final("SELECT id FROM t", 5)
    assert len(db.ran) == 4


def test_cache_expires():
    db = FakeDB({"SELECT id": {"columns": ["id"], "rows": [[1]]}})
    run = _exploring(ExploreCache(ttl=0).wrap(db, scope="s"))
    run("SELECT id FROM t", 10); run("SELECT id FROM t", 10)
    assert len(db.ran) == 2


def test_mcp_adaptive_is_the_default(server):
    model = Script("SELECT id FROM billing_invoice_line")
    server(model)
    out = mcp_server.deep_answer("invoice line ids", max_rows=3)
    assert "error" not in out, out
    assert out["model_calls"] == 1 and out["steps"][0]["kind"] == "plain" and out["row_count"] == 3


# --- the exploring-read time limit -------------------------------------------------------------

RUNAWAY = ("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) "
           "SELECT count(*) FROM c")


def test_run_sql_timeout_stops_a_runaway_read_and_does_not_leak(tmp_path):
    import time
    import pytest as _pytest
    from sqlalchemy import create_engine
    from schemagate.answer import run_sql
    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}", pool_size=1, poolclass=None)
    t0 = time.monotonic()
    with _pytest.raises(Exception):
        run_sql(eng, RUNAWAY, timeout=0.5)
    assert time.monotonic() - t0 < 10
    # the same pooled connection, next call, no limit: a normal query still runs
    assert run_sql(eng, "SELECT 1")[1] == [(1,)]


def test_mcp_explore_reads_get_the_limit_and_finals_do_not(server, monkeypatch):
    import schemagate.answer as A
    seen, real = [], A.run_sql

    def spy(engine, sql, limit=50, timeout=None):
        seen.append((limit, timeout))
        return real(engine, sql, limit=limit)
    monkeypatch.setattr(A, "run_sql", spy)
    model = Script("EXPLORE: look\nSELECT id FROM billing_invoice_line LIMIT 2",
                   "FINAL: ids\nSELECT id FROM billing_invoice_line")
    server(model)
    out = mcp_server.deep_answer("invoice line ids", max_rows=5, mode="deep")
    assert "error" not in out, out
    assert seen[0][1] == mcp_server.EXPLORE_SECONDS and seen[-1][1] is None
    assert mcp_server._QUERY_TIMEOUT.get() is None


# --- repairs before and after the step loop ---------------------------------------------------

def test_adaptive_repairs_a_rejected_first_query_before_any_step_mode():
    model = Script("SELECT nme FROM customer", "SELECT id FROM customer")
    db = FakeDB({"nme": {"error": "no such column: nme"}, "SELECT id": {"columns": ["id"], "rows": [[1]]}})
    res = adaptive_answer(model, "ids", DDL, db)
    assert res.rows == [[1]] and [s["kind"] for s in res.steps] == ["plain", "repair"]
    assert "rejected by the database" in model.prompts[1] and "no such column: nme" in model.prompts[1]


def test_adaptive_enters_step_mode_only_after_repairs_are_spent():
    model = Script("SELECT a FROM customer", "SELECT b FROM customer", "SELECT c FROM customer",
                   "FINAL: x\nSELECT id FROM customer")
    db = FakeDB({"SELECT a": {"error": "e1"}, "SELECT b": {"error": "e2"}, "SELECT c": {"error": "e3"},
                 "SELECT id": {"columns": ["id"], "rows": [[1]]}})
    res = adaptive_answer(model, "ids", DDL, db, repairs=2)
    assert [s["kind"] for s in res.steps] == ["plain", "repair", "repair", "final"] and res.rows == [[1]]


def test_out_of_steps_query_is_repaired_too():
    model = Script("EXPLORE: look\nSELECT id FROM customer", "SELECT bad FROM customer", "SELECT id FROM customer")
    db = FakeDB({"SELECT id": {"columns": ["id"], "rows": [[1]]}, "bad": {"error": "no such column: bad"}})
    res = deep_answer(model, "q", DDL, db, max_steps=1)
    assert res.rows == [[1]] and [s["kind"] for s in res.steps] == ["explore", "final", "repair"]
