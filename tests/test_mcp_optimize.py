"""explain_query, compare_queries and optimize_query: the same caller scope as run_query, and no writes."""
import pytest

from schemagate import mcp_server
from schemagate import optimize as opt
from schemagate.ai.providers import CallableProvider


@pytest.fixture
def runnable(cat, db_url, monkeypatch):
    cat.restrict("hr_compensation", ["payroll"])
    mcp_server.build_catalog(catalog=cat)
    import sqlite3
    c = sqlite3.connect(db_url.replace("sqlite:///", ""))
    c.executemany("INSERT OR IGNORE INTO crm_customer (id, segment, status) VALUES (?, ?, ?)",
                  [(i, "smb" if i % 2 else "ent", "active") for i in range(1, 51)])
    c.commit()
    c.close()
    monkeypatch.setattr(mcp_server, "_URL", db_url, raising=False)
    monkeypatch.setattr(mcp_server, "_ENGINE", None, raising=False)
    return cat


ALL = "SELECT id FROM crm_customer"
SAME = "SELECT id FROM crm_customer WHERE id IS NOT NULL"


def test_tools_are_registered_and_take_identity():
    for name in ("explain_query", "compare_queries", "optimize_query"):
        assert name in mcp_server.TOOL_DESCRIPTIONS
        assert name in mcp_server.IDENTITY_TOOLS


def test_explain_returns_a_plan(runnable):
    out = mcp_server.explain_query(ALL)
    assert "error" not in out, out
    assert out["plan"]


def test_explain_refuses_a_hidden_table(runnable):
    out = mcp_server.explain_query("SELECT * FROM hr_compensation")
    assert "not available to this caller" in out["error"]


def test_compare_identical(runnable):
    out = mcp_server.compare_queries(ALL, SAME)
    assert out["identical"] is True and out["new_literals"] == []


def test_compare_different(runnable):
    out = mcp_server.compare_queries(ALL, "SELECT id FROM crm_customer WHERE id < 0")
    assert out["identical"] is False


def test_compare_refuses_a_hidden_table_in_the_candidate(runnable):
    out = mcp_server.compare_queries(ALL, "SELECT c.id FROM crm_customer c JOIN hr_compensation h ON 1=0")
    assert "not available to this caller" in out["error"]


def test_compare_refuses_a_write(runnable):
    out = mcp_server.compare_queries(ALL, "DELETE FROM crm_customer")
    assert out["error"].startswith("refused")


def test_compare_flags_new_constants(runnable):
    out = mcp_server.compare_queries(ALL, "SELECT id FROM crm_customer WHERE id < 987654321")
    assert out["new_literals"] == ["987654321"] and "warning" in out


def test_optimize_without_a_model_says_how_to_do_it_yourself(runnable, monkeypatch):
    monkeypatch.setattr(mcp_server, "_server_provider", lambda: None)
    out = mcp_server.optimize_query(ALL)
    assert out["optimized"] is None and "compare_queries" in out["next"]


def test_optimize_never_picks_a_rewrite_that_reads_a_hidden_table(runnable, monkeypatch):
    sneaky = "SELECT c.id FROM crm_customer c LEFT JOIN hr_compensation h ON 1=0"
    monkeypatch.setattr(mcp_server, "_server_provider",
                        lambda: CallableProvider(lambda s, p: f"```sql\n{sneaky}\n```"))
    monkeypatch.setattr(opt, "measure_ms", lambda e, sql, runs=2, timeout=None: 1.0 if "hr_" in sql else 50.0)
    out = mcp_server.optimize_query(ALL)
    assert out["improved"] is False
    assert out["attempts"][0]["error"].startswith("refused")


def test_optimize_returns_a_verified_faster_rewrite(runnable, monkeypatch):
    monkeypatch.setattr(mcp_server, "_server_provider",
                        lambda: CallableProvider(lambda s, p: f"```sql\n{SAME}\n```"))
    monkeypatch.setattr(opt, "measure_ms", lambda e, sql, runs=2, timeout=None: 5.0 if "NOT NULL" in sql else 50.0)
    out = mcp_server.optimize_query(ALL)
    assert out["improved"] is True and out["sql"] == SAME and out["speedup"] == 10.0
    assert "review" in out["note"]


def test_optimize_sends_only_visible_ddl_to_the_model(runnable, monkeypatch):
    seen = []
    monkeypatch.setattr(mcp_server, "_server_provider",
                        lambda: CallableProvider(lambda s, p: seen.append(p) or "no rewrite"))
    monkeypatch.setattr(opt, "measure_ms", lambda e, sql, runs=2, timeout=None: 50.0)
    mcp_server.optimize_query(ALL)
    assert seen and "crm_customer" in seen[0] and "hr_compensation" not in seen[0]
