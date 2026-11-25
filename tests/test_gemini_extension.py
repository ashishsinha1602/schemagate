# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""gemini-extension.json has to follow the package, like server.json does.

Google's gallery (geminicli.com/extensions) crawls the repository root for
this file and the Gemini CLI compares its ``version`` with the release tag
to decide whether an update exists. The two plugin manifests that were not
checked this way (plugins/schemagate at 1.15.5, copilot-plugin at 1.15.1)
drifted four minor versions behind PyPI; this one is pinned here so the
release check in publish.yml and this test both fail before it can.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "gemini-extension.json"

pytestmark = pytest.mark.skipif(not MANIFEST.is_file(), reason="no gemini-extension.json")


def _pyproject_version() -> str:
    m = re.search(r'^version = "([^"]+)"',
                  (ROOT / "pyproject.toml").read_text("utf-8"), re.M)
    assert m, "no version in pyproject.toml"
    return m.group(1)


def _doc() -> dict:
    return json.loads(MANIFEST.read_text("utf-8"))


def test_version_matches_the_package():
    assert _doc()["version"] == _pyproject_version()


def test_the_server_installs_the_same_version():
    """``uvx --from schemagate[...]==X`` must pin the version the manifest
    claims, or the gallery shows one number and installs another."""
    want = _pyproject_version()
    for name, server in _doc()["mcpServers"].items():
        args = server.get("args", [])
        pins = [a for a in args if a.startswith("schemagate[") or a.startswith("schemagate==")]
        assert pins, f"mcpServers[{name!r}] does not install schemagate: {args}"
        for pin in pins:
            assert pin.endswith("==" + want), f"{name}: {pin} is not pinned to {want}"
        assert "schemagate-mcp" in args, f"{name}: does not run the schemagate-mcp entry point"


def test_name_is_what_the_gallery_accepts():
    """Lowercase letters, digits and dashes; it must match the extension
    directory name the CLI creates."""
    assert re.fullmatch(r"[a-z0-9-]+", _doc()["name"])


def test_the_database_url_is_a_declared_setting_not_a_baked_in_value():
    """Extensions do not inherit the shell environment. The URL has to come
    from a ``settings`` entry so the CLI asks for it at install time and
    keeps it out of the manifest."""
    d = _doc()
    env_vars = {s["envVar"] for s in d.get("settings", [])}
    assert "SCHEMAGATE_DATABASE_URL" in env_vars
    for name, server in d["mcpServers"].items():
        assert "SCHEMAGATE_DATABASE_URL" not in server.get("env", {}), \
            f"{name}: the database URL is hard-coded in the manifest"
    url = next(s for s in d["settings"] if s["envVar"] == "SCHEMAGATE_DATABASE_URL")
    assert url.get("sensitive") is True, "a connection string carries a password"


def test_the_context_file_it_names_exists():
    d = _doc()
    assert (ROOT / d.get("contextFileName", "GEMINI.md")).is_file()
