"""server.json's version must match the package's.

It pinned 0.1.0 while PyPI was on 0.1.53 -- fifty-three releases -- because
nothing checked it and it is edited by hand, in two places inside one file.
An MCP client installing from the registry got the wrong package.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "server.json"

pytestmark = pytest.mark.skipif(not SERVER.is_file(), reason="no server.json")


def _pyproject_version() -> str:
    m = re.search(r'^version = "([^"]+)"',
                  (ROOT / "pyproject.toml").read_text("utf-8"), re.M)
    assert m, "no version in pyproject.toml"
    return m.group(1)


def test_server_json_version_matches_the_package():
    d = json.loads(SERVER.read_text("utf-8"))
    want = _pyproject_version()
    assert d["version"] == want, "server.json version is %s, package is %s" % (d["version"], want)


def test_every_package_entry_matches_too():
    """Two places in one file; the second is the one that gets forgotten."""
    d = json.loads(SERVER.read_text("utf-8"))
    want = _pyproject_version()
    for pkg in d.get("packages", []):
        assert pkg.get("version") == want, \
            "packages[%r] is %s, package is %s" % (pkg.get("identifier"), pkg.get("version"), want)


def test_it_points_at_the_module_that_exists():
    d = json.loads(SERVER.read_text("utf-8"))
    args = [a.get("value") for a in d["packages"][0].get("package_arguments", [])]
    assert "schemagate.mcp_server" in args, args
    assert (ROOT / "src" / "schemagate" / "mcp_server.py").is_file()
