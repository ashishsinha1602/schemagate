"""optimizer_tools: the agent's own model rewrites, these tools prove it. Same scope as run_query."""
import pytest

pytest.importorskip("langchain_core")

from sqlalchemy import create_engine, text  # noqa: E402

from schemagate import Catalog, Principal  # noqa: E402
from schemagate.integrations.langchain import optimizer_tools  # noqa: E402


@pytest.fixture()
def setup(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'lc.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, amount INTEGER)"))
        c.execute(text("CREATE TABLE payroll (id INTEGER PRIMARY KEY, salary INTEGER)"))
        c.execute(text("INSERT INTO orders (amount) VALUES (:a)"), [{"a": i % 13} for i in range(200)])
    cat = Catalog().bootstrap(str(eng.url))
    cat.restrict("payroll", ["hr"])
    return eng, cat


def _tools(eng, cat, who=None):
    return {t.name: t for t in optimizer_tools(eng, catalog=cat, principal=who)}


def test_two_tools(setup):
    eng, cat = setup
    assert set(_tools(eng, cat)) == {"explain_query", "compare_queries"}


def test_compare_identical_and_different(setup):
    eng, cat = setup
    t = _tools(eng, cat)["compare_queries"]
    same = t.invoke({"original": "SELECT id FROM orders", "candidate": "SELECT id FROM orders WHERE id > 0"})
    assert same["identical"] is True
    diff = t.invoke({"original": "SELECT id FROM orders", "candidate": "SELECT id FROM orders WHERE id > 5"})
    assert diff["identical"] is False


def test_hidden_table_is_refused_without_the_role(setup):
    eng, cat = setup
    t = _tools(eng, cat)["compare_queries"]
    out = t.invoke({"original": "SELECT id FROM orders", "candidate": "SELECT id FROM payroll"})
    assert "not available to this caller" in out["error"]
    ok = _tools(eng, cat, Principal("okta:h", roles={"hr"}))["compare_queries"].invoke(
        {"original": "SELECT id FROM payroll", "candidate": "SELECT id FROM payroll WHERE id > 0"})
    assert ok["identical"] is True


def test_writes_are_refused(setup):
    eng, cat = setup
    out = _tools(eng, cat)["explain_query"].invoke({"sql": "DELETE FROM orders"})
    assert "error" in out
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM orders")).scalar() == 200


def test_explain_returns_a_plan(setup):
    eng, cat = setup
    assert _tools(eng, cat)["explain_query"].invoke({"sql": "SELECT * FROM orders WHERE id = 3"})["plan"]
