# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""The `schemagate-mcp` command: its options, and how it fails when it cannot start.

The end-to-end check (a wheel installed in a clean environment, started through
the console script and driven over stdio by an MCP client) is run before each
release; this file pins the behaviour that does not need a network or a build.
"""
import pytest

from schemagate import __version__
from schemagate import mcp_server


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        mcp_server.main(["--version"])
    assert e.value.code == 0
    assert capsys.readouterr().out.strip() == f"schemagate {__version__}"


def test_url_and_config_override_the_environment(monkeypatch):
    monkeypatch.setenv("SCHEMAGATE_DATABASE_URL", "postgresql://from-env/db")
    monkeypatch.delenv("SCHEMAGATE_CATALOG_CONFIG", raising=False)
    seen = {}

    def stop(*_a, **_k):
        import os
        seen["url"] = os.environ.get("SCHEMAGATE_DATABASE_URL")
        seen["config"] = os.environ.get("SCHEMAGATE_CATALOG_CONFIG")
        raise SystemExit(0)

    monkeypatch.setattr(mcp_server, "build_catalog", stop)
    monkeypatch.setattr(mcp_server, "_server_class", lambda: object)
    with pytest.raises(SystemExit):
        mcp_server.main(["--url", "demo", "--config", "roles.json"])
    assert seen == {"url": "demo", "config": "roles.json"}


def test_without_options_the_environment_is_used(monkeypatch):
    monkeypatch.setenv("SCHEMAGATE_DATABASE_URL", "postgresql://from-env/db")
    seen = {}

    def stop(*_a, **_k):
        import os
        seen["url"] = os.environ.get("SCHEMAGATE_DATABASE_URL")
        raise SystemExit(0)

    monkeypatch.setattr(mcp_server, "build_catalog", stop)
    monkeypatch.setattr(mcp_server, "_server_class", lambda: object)
    with pytest.raises(SystemExit):
        mcp_server.main([])
    assert seen["url"] == "postgresql://from-env/db"


def test_a_missing_mcp_extra_is_one_clear_line_before_any_database_work(monkeypatch):
    called = []
    monkeypatch.setattr(mcp_server, "build_catalog", lambda *a, **k: called.append(1))

    def missing():
        raise ImportError("pip install 'schemagate[mcp]' to run the MCP server")

    monkeypatch.setattr(mcp_server, "_server_class", missing)
    with pytest.raises(SystemExit) as e:
        mcp_server.main(["--url", "demo"])
    assert "pip install 'schemagate[mcp]'" in str(e.value.code)
    assert called == [], "the database must not be touched when the server cannot run"


def test_the_console_script_is_declared():
    import pathlib
    import re
    text = (pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    scripts = text.split("[project.scripts]", 1)[1].split("\n[", 1)[0]       # tomllib is 3.11+; CI runs 3.9
    assert re.search(r'^schemagate-mcp\s*=\s*"schemagate\.mcp_server:main"\s*$', scripts, re.M)
