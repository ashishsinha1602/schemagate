"""A missing database driver says which extra to install.

`pip install schemagate` is SQLAlchemy only, so the first Oracle connect on a
fresh install used to end in a long SQLAlchemy traceback whose last line was
`No module named 'oracledb'`. True, and no help to someone who has just run
the install line from the README.
"""
import sys

import pytest

from schemagate.cli import main
from schemagate.connect import missing_driver_hint
from schemagate.introspect import engine_from_url

ORACLE_URL = "oracle+oracledb://u:p@localhost:1521/?service_name=x"


@pytest.fixture
def no_oracledb(monkeypatch):
    # None in sys.modules makes `import oracledb` raise ImportError(name='oracledb'),
    # which is what a fresh install without the extra sees
    monkeypatch.setitem(sys.modules, "oracledb", None)


def test_the_hint_names_the_extra():
    e = ModuleNotFoundError("No module named 'psycopg'", name="psycopg")
    assert missing_driver_hint(e) == ("driver not installed (psycopg) -- "
                                      "pip install 'schemagate[postgres]'")


def test_a_url_with_no_driver_named_still_gets_the_hint():
    """`postgresql://` makes SQLAlchemy import psycopg2, not psycopg."""
    e = ModuleNotFoundError("No module named 'psycopg2'", name="psycopg2")
    assert "schemagate[postgres]" in missing_driver_hint(e)


def test_an_unrelated_import_error_gets_no_hint():
    assert missing_driver_hint(ModuleNotFoundError("x", name="numpy")) is None
    assert missing_driver_hint(ValueError("oracledb")) is None


def test_engine_from_url_raises_the_hint(no_oracledb):
    with pytest.raises(ImportError, match=r"pip install 'schemagate\[oracle\]'") as e:
        engine_from_url(ORACLE_URL)
    # never a different class than Python raised: callers may catch the subclass
    assert e.value.name == "oracledb"


def test_a_real_missing_module_keeps_its_class(monkeypatch):
    def boom(*a, **k):
        raise ModuleNotFoundError("No module named 'psycopg'", name="psycopg")
    monkeypatch.setattr("sqlalchemy.create_engine", boom)
    with pytest.raises(ModuleNotFoundError, match=r"schemagate\[postgres\]"):
        engine_from_url("postgresql+psycopg://u:p@h/db")


def test_the_cli_prints_the_hint_instead_of_a_traceback(no_oracledb, capsys):
    assert main(["select", "overdue invoices", "--url", ORACLE_URL]) == 2
    err = capsys.readouterr().err
    assert "pip install 'schemagate[oracle]'" in err
    assert "Traceback" not in err


def test_running_sql_uses_the_connect_args_from_the_environment(tmp_path, monkeypatch):
    """`--answer` / `--sql` opened their own engine with plain create_engine,
    so an Autonomous Database wallet in SCHEMAGATE_CONNECT_ARGS reached the
    reflection but not the query: DPY-4001 "no credentials specified" right
    after the SQL had been written."""
    import sqlalchemy
    seen = []
    real = sqlalchemy.create_engine

    def spy(url, **kw):
        seen.append(kw.get("connect_args"))
        return real(url, **kw)

    monkeypatch.setattr(sqlalchemy, "create_engine", spy)
    monkeypatch.setenv("SCHEMAGATE_CONNECT_ARGS", '{"timeout": 7}')
    url = f"sqlite:///{tmp_path / 'x.db'}"
    assert main(["select", "--sql", "SELECT 1 AS one", "--url", url]) == 0
    assert {"timeout": 7} in seen
