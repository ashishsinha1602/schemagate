"""schemagate.optimize on SQLite: same-rows checks, safety, and how the loop picks a rewrite.

Timing on a small SQLite file is noise, so the loop tests fix the timings
(`measure_ms` is patched) and test the decisions, not the stopwatch.
"""
import pytest
from sqlalchemy import create_engine, text

from schemagate import optimize as opt
from schemagate.ai.providers import CallableProvider
from schemagate.answer import UnsafeSQL

SLOW = ("SELECT o.id, o.customer, o.amount FROM orders o "
        "WHERE o.amount = (SELECT MAX(o2.amount) FROM orders o2 WHERE o2.customer = o.customer)")
FAST = ("SELECT o.id, o.customer, o.amount FROM orders o JOIN "
        "(SELECT customer, MAX(amount) AS m FROM orders GROUP BY customer) x "
        "ON x.customer = o.customer AND o.amount = x.m")
WRONG = "SELECT o.id, o.customer, o.amount FROM orders o WHERE o.amount > 50"


@pytest.fixture()
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'shop.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer TEXT, amount INTEGER)"))
        c.execute(text("CREATE TABLE secrets (id INTEGER PRIMARY KEY, note TEXT)"))
        c.execute(text("INSERT INTO orders (customer, amount) VALUES (:c, :a)"),
                  [{"c": f"c{i % 37}", "a": (i * 7919) % 101} for i in range(1500)])
    return eng


def _count(engine):
    with engine.connect() as c:
        return c.execute(text("SELECT count(*) FROM orders")).scalar()


# ---- same rows? ------------------------------------------------------------

def test_identical_rewrite_is_identical(engine):
    c = opt.compare(engine, SLOW, FAST, runs=1)
    assert c.identical and c.original_rows == c.candidate_rows > 0
    assert c.timing == "wall-clock" and c.speedup is not None


def test_different_rows_are_caught(engine):
    c = opt.compare(engine, SLOW, WRONG, runs=1)
    assert not c.identical
    assert c.candidate_ms is None            # a wrong answer is not timed


def test_same_count_different_rows_is_caught(engine):
    c = opt.compare(engine, "SELECT id FROM orders WHERE id <= 10", "SELECT id FROM orders WHERE id > 1490")
    assert not c.identical and c.reason == "same row count, different rows"


def test_order_matters_only_when_the_original_orders(engine):
    asc = "SELECT id FROM orders WHERE id <= 20 ORDER BY id"
    desc = "SELECT id FROM orders WHERE id <= 20 ORDER BY id DESC"
    assert not opt.compare(engine, asc, desc).identical
    unordered = "SELECT id FROM orders WHERE id <= 20"
    assert opt.compare(engine, unordered, desc).identical


def test_order_by_inside_a_subquery_is_not_top_level():
    assert not opt._has_top_level_order_by("SELECT * FROM (SELECT id FROM t ORDER BY id LIMIT 5) x")
    assert opt._has_top_level_order_by("SELECT id FROM t ORDER BY id")
    assert not opt._has_top_level_order_by("SELECT 'order by' AS s FROM t -- order by\n")


# ---- safety ----------------------------------------------------------------

@pytest.mark.parametrize("bad", ["DELETE FROM orders", "SELECT 1; DELETE FROM orders",
                                 "UPDATE orders SET amount = 0"])
def test_writes_are_refused_and_nothing_changes(engine, bad):
    before = _count(engine)
    with pytest.raises(UnsafeSQL):
        opt.compare(engine, SLOW, bad)
    with pytest.raises(UnsafeSQL):
        opt.fingerprint(engine, bad)
    assert _count(engine) == before


def test_new_literals_are_flagged():
    assert opt.new_literals("SELECT * FROM t WHERE a > 5", "SELECT * FROM t WHERE a > 5 AND id < 6000033") == ["6000033"]
    assert opt.new_literals("SELECT * FROM t", "SELECT * FROM t LIMIT 1") == []          # 0 and 1 are fine
    assert opt.new_literals("SELECT * FROM t1", "SELECT * FROM t1 x") == []              # names are not values
    assert opt.new_literals("SELECT * FROM t", "SELECT * FROM t WHERE d >= '2024-01-01'") == ["'2024-01-01'"]


# ---- the loop --------------------------------------------------------------

def _timings(monkeypatch, table):
    def fake(engine, sql, runs=2, timeout=None):
        for key, ms in table.items():
            if key in sql:
                return ms
        return 100.0
    monkeypatch.setattr(opt, "measure_ms", fake)


def _model(*replies):
    calls = []

    def fn(system, prompt):
        calls.append(prompt)
        return replies[min(len(calls) - 1, len(replies) - 1)]
    p = CallableProvider(fn, name="fake")
    p.calls = calls
    return p


def test_picks_the_faster_identical_rewrite(engine, monkeypatch):
    _timings(monkeypatch, {"JOIN": 10.0, "o2.customer": 100.0})
    r = opt.optimize(engine, SLOW, _model(f"```sql\n{FAST}\n```"), rounds=1)
    assert r.improved and r.sql == FAST and r.speedup == 10.0
    assert r.attempts[0].identical is True


def test_a_wrong_rewrite_is_never_chosen_however_fast(engine, monkeypatch):
    _timings(monkeypatch, {"> 50": 1.0, "o2.customer": 100.0})
    r = opt.optimize(engine, SLOW, _model(f"```sql\n{WRONG}\n```"), rounds=1)
    assert not r.improved and r.sql == SLOW and r.attempts[0].identical is False


def test_not_faster_enough_keeps_the_original(engine, monkeypatch):
    _timings(monkeypatch, {"JOIN": 95.0, "o2.customer": 100.0})
    r = opt.optimize(engine, SLOW, _model(f"```sql\n{FAST}\n```"), rounds=1)
    assert not r.improved and r.speedup == 1.0


def test_scope_check_refuses_a_candidate(engine, monkeypatch):
    _timings(monkeypatch, {"secrets": 1.0})
    sneaky = SLOW + " AND EXISTS (SELECT 1 FROM secrets)"
    r = opt.optimize(engine, SLOW, _model(f"```sql\n{sneaky}\n```"), rounds=1,
                     check=lambda s: "secrets is not visible to you" if "secrets" in s else None)
    assert not r.improved and r.attempts[0].error.startswith("refused")


def test_a_write_from_the_model_is_refused(engine, monkeypatch):
    _timings(monkeypatch, {})
    before = _count(engine)
    r = opt.optimize(engine, SLOW, _model("```sql\nDELETE FROM orders\n```"), rounds=1)
    assert not r.improved and r.attempts[0].error.startswith("refused")
    assert _count(engine) == before


def test_rewrite_with_data_constants_is_set_aside(engine, monkeypatch):
    split = FAST + " WHERE o.id < 100000"                # same rows today, a constant from nowhere
    _timings(monkeypatch, {"100000": 5.0, "o2.customer": 100.0})
    r = opt.optimize(engine, SLOW, _model(f"```sql\n{split}\n```"), rounds=1)
    assert not r.improved
    assert r.attempts[0].identical and r.attempts[0].new_literals == ["100000"]
    assert any("constants" in w for w in r.warnings)


def test_no_sql_in_the_reply_keeps_the_original(engine, monkeypatch):
    _timings(monkeypatch, {})
    r = opt.optimize(engine, SLOW, _model("I see no safe improvement."), rounds=3)
    assert not r.improved and r.attempts == []


def test_model_failure_returns_the_original_with_a_warning(engine, monkeypatch):
    _timings(monkeypatch, {})

    def boom(system, prompt):
        raise RuntimeError("rate limited")
    r = opt.optimize(engine, SLOW, CallableProvider(boom), rounds=2)
    assert not r.improved and any("model call failed" in w for w in r.warnings)


def test_later_rounds_see_earlier_attempts(engine, monkeypatch):
    _timings(monkeypatch, {"JOIN": 10.0, "o2.customer": 100.0})
    m = _model(f"```sql\n{WRONG}\n```", f"```sql\n{FAST}\n```")
    r = opt.optimize(engine, SLOW, m, rounds=2, target_speedup=100)
    assert r.improved and r.sql == FAST
    assert "rejected: different result" in m.calls[1]


def test_original_out_of_scope_is_refused(engine, monkeypatch):
    _timings(monkeypatch, {})
    with pytest.raises(UnsafeSQL):
        opt.optimize(engine, "SELECT * FROM secrets", _model(""), check=lambda s: "secrets is not visible")


# ---- the command line --------------------------------------------------------

def test_cli_prints_the_faster_rewrite(engine, monkeypatch, capsys):
    from schemagate import cli
    _timings(monkeypatch, {"JOIN": 10.0, "o2.customer": 100.0})
    monkeypatch.setattr(cli, "_provider_from_args", lambda name, model: _model(f"```sql\n{FAST}\n```"))
    code = cli.main(["optimize", SLOW, "--url", str(engine.url), "--provider", "anthropic", "--model", "x",
                     "--rounds", "1"])
    out = capsys.readouterr().out
    assert code == 0 and "10.0x faster" in out and FAST in out


def test_cli_exits_nonzero_when_nothing_is_faster(engine, monkeypatch, capsys):
    from schemagate import cli
    _timings(monkeypatch, {})
    monkeypatch.setattr(cli, "_provider_from_args", lambda name, model: _model("no rewrite"))
    code = cli.main(["optimize", SLOW, "--url", str(engine.url), "--provider", "anthropic", "--model", "x"])
    assert code == 1 and "original returned" in capsys.readouterr().out
