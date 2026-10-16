# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Two startup errors that used to send people the wrong way, found by a clean-install check.

- On Python 3.9 the `mcp` extra installs without the MCP SDK (which needs 3.10+), so
  "pip install 'schemagate[mcp]'" was advice the user had already followed.
- A malformed --url printed a SQLAlchemy traceback instead of one line.
"""
import builtins
import sys

import pytest

from schemagate import cli
from schemagate import mcp_server as M


def _no_mcp(monkeypatch):
    real = builtins.__import__

    def fake(name, *a, **k):
        if name.startswith("mcp"):
            raise ImportError(f"No module named {name!r}")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)


def test_on_python_3_9_the_mcp_error_names_the_python_version(monkeypatch):
    _no_mcp(monkeypatch)
    monkeypatch.setattr(sys, "version_info", (3, 9, 25, "final", 0))
    with pytest.raises(ImportError, match="needs Python 3.10 or newer"):
        M._server_class()


def test_on_a_supported_python_the_mcp_error_says_to_install_the_extra(monkeypatch):
    _no_mcp(monkeypatch)
    monkeypatch.setattr(sys, "version_info", (3, 12, 0, "final", 0))
    with pytest.raises(ImportError, match=r"pip install 'schemagate\[mcp\]'"):
        M._server_class()


@pytest.mark.parametrize("url", ["demo", "not a url", "postgres//missing-colon"])
def test_a_malformed_url_is_one_line_not_a_traceback(capsys, url):
    rc = cli.main(["select", "--url", url, "which customers owe us money"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "is not a database URL" in err and "schemagate demo" in err
    assert "Traceback" not in err
