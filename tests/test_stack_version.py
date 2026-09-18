"""The OCI stack's version pins must match the package's.

Same failure as server.json, in two more files. ``oci/stack/variables.tf``
pins the schemagate version an instance installs -- its own description says
"the zip and the PyPI release are cut together, so this is the version this
stack was actually tested against" -- and nothing in the release job bumped
it, so at the v0.1.55 tag it said 0.1.54. ``oci/stack/schema.yaml`` carries
the Resource Manager stack's version, which ``verify-release.sh`` reads to
decide what to verify; it said 0.1.17, thirty-eight releases behind, so the
verification script would have refused to run against the current release
at all.

Three places, all edited by hand, none checked. Now checked.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STACK = ROOT / "oci" / "stack"

pytestmark = pytest.mark.skipif(not STACK.is_dir(), reason="no oci/stack")


def _pyproject_version() -> str:
    m = re.search(r'^version = "([^"]+)"',
                  (ROOT / "pyproject.toml").read_text("utf-8"), re.M)
    assert m, "no version in pyproject.toml"
    return m.group(1)


def _variables_tf() -> str:
    return (STACK / "variables.tf").read_text("utf-8")


def test_the_pinned_default_matches_the_package():
    text = _variables_tf()
    block = re.search(r'variable "schemagate_version" \{(.*?)\n\}', text, re.S)
    assert block, "no schemagate_version variable in variables.tf"
    m = re.search(r'default\s*=\s*"([^"]*)"', block.group(1))
    assert m, "schemagate_version has no default"
    want = _pyproject_version()
    assert m.group(1) == want, (
        "oci/stack/variables.tf pins %s, package is %s -- the stack installs "
        "the wrong release" % (m.group(1), want))


def test_the_example_in_the_error_message_matches_too():
    """The second place in one file; the one that gets forgotten."""
    text = _variables_tf()
    block = re.search(r'variable "schemagate_version" \{(.*?)\n\}', text, re.S)
    assert block
    m = re.search(r'error_message\s*=\s*"Give a version like ([^,]+),', block.group(1))
    assert m, "the validation error_message no longer carries an example"
    want = _pyproject_version()
    assert m.group(1) == want, (
        "error_message example is %s, package is %s" % (m.group(1), want))


def test_the_resource_manager_schema_version_matches():
    """verify-release.sh reads this to decide which release to verify. At
    0.1.17 against a PyPI on 0.1.55 it refused to start."""
    text = (STACK / "schema.yaml").read_text("utf-8")
    m = re.search(r'^version:\s*"([^"]+)"', text, re.M)
    assert m, "no top-level version in schema.yaml"
    want = _pyproject_version()
    assert m.group(1) == want, (
        "oci/stack/schema.yaml says %s, package is %s" % (m.group(1), want))
