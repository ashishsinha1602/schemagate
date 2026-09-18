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
    args = [a.get("value") for a in d["packages"][0].get("packageArguments", [])]
    assert "schemagate.mcp_server" in args, args
    assert (ROOT / "src" / "schemagate" / "mcp_server.py").is_file()


# The registry renamed every field to camelCase on 2025-09-16 and said so in
# its changelog: "All existing server.json files must be updated." This file
# sat on the 2025-07-09 schema with snake_case keys for five schema versions,
# which means a publish would have failed validation the whole time -- and
# nothing here would have noticed, because the version test above passed.

_SNAKE = ("registry_type", "runtime_hint", "package_arguments",
          "environment_variables", "is_required", "is_secret")


def test_the_schema_is_a_current_dated_version():
    d = json.loads(SERVER.read_text("utf-8"))
    m = re.search(r"/schemas/(\d{4}-\d{2}-\d{2})/server\.schema\.json$",
                  d.get("$schema", ""))
    assert m, f"$schema is not a dated registry schema: {d.get('$schema')!r}"
    assert m.group(1) >= "2025-09-16", (
        f"schema {m.group(1)} predates the camelCase migration")


def test_no_snake_case_field_names_remain():
    text = SERVER.read_text("utf-8")
    stale = [k for k in _SNAKE if f'"{k}"' in text]
    assert not stale, f"pre-2025-09-16 field names still present: {stale}"


def test_every_package_declares_a_transport():
    """Every current example in the registry's own docs carries one, and a
    local stdio server without it is not something a client can launch."""
    d = json.loads(SERVER.read_text("utf-8"))
    for pkg in d.get("packages", []):
        assert pkg.get("transport", {}).get("type"), \
            f"packages[{pkg.get('identifier')!r}] has no transport"


SCHEMA_FIXTURE = ROOT / "tests" / "fixtures" / "mcp-server.schema.2025-12-11.json"


def test_it_validates_against_the_registry_schema_it_names():
    """The whole file, against the actual schema, offline.

    The key-name checks above catch the migration that was missed; this
    catches everything else the registry would reject -- the description
    cap of 100 characters was found this way, not by reading the docs. The
    schema is vendored so CI needs no network, and pinned to the version the
    document claims, so the copy cannot quietly drift from the claim.
    """
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_FIXTURE.read_text("utf-8"))
    doc = json.loads(SERVER.read_text("utf-8"))
    assert schema.get("$id") == doc.get("$schema"), (
        "vendored schema %s is not the one server.json claims, %s"
        % (schema.get("$id"), doc.get("$schema")))
    # Chosen from the schema's own $schema (it declares draft-07), not
    # hard-coded: a validator of the wrong draft resolves keywords
    # differently and can pass a document the registry would reject.
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    errors = ["%s: %s" % ("/".join(map(str, e.path)) or "<root>", e.message[:120])
              for e in validator.iter_errors(doc)]
    assert not errors, "server.json would be rejected by the registry:\n  " + "\n  ".join(errors)
