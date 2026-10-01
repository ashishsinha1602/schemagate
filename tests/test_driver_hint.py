"""A missing database driver says which extra to install.

`pip install schemagate` is SQLAlchemy only, so the first Oracle connect on a
fresh install used to end in a long SQLAlchemy traceback whose last line was
`No module named 'oracledb'`. True, and no help to someone who has just run
the install line from the README.
"""
import sys

import pytest

from schemagate.cli import main
from schemagate.introspect import engine_from_url, missing_driver_hint

ORACLE_URL = "oracle+oracledb://u:p@localhost:1521/?service_name=x"


@pytest.fixture
def no_oracledb(monkeypatch):
    # None in sys.modules makes `import oracledb` raise ImportError(name='oracledb'),
    # which is what a fresh install without the extra sees
    monkeypatch.setitem(sys.modules, "oracledb", None)


def test_the_hint_names_the_extra():
    e = ModuleNotFoundError("No module named 'psycopg'", name="psycopg")
    assert missing_driver_hint(e) == ("the psycopg driver is not installed: "
                                      "pip install 'schemagate[postgres]'")


def test_an_unrelated_import_error_gets_no_hint():
    assert missing_driver_hint(ModuleNotFoundError("x", name="numpy")) is None
    assert missing_driver_hint(ValueError("oracledb")) is None


def test_engine_from_url_raises_the_hint(no_oracledb):
    with pytest.raises(ImportError, match=r"pip install 'schemagate\[oracle\]'"):
        engine_from_url(ORACLE_URL)


def test_the_cli_prints_the_hint_instead_of_a_traceback(no_oracledb, capsys):
    assert main(["select", "overdue invoices", "--url", ORACLE_URL]) == 2
    err = capsys.readouterr().err
    assert "pip install 'schemagate[oracle]'" in err
    assert "Traceback" not in err
