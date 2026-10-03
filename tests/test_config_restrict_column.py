"""Column ACLs stated in a catalog config file.

Object-level rules could already live outside your code; column-level ones
could not, so the CLI, the Studio and the MCP server -- which all configure
themselves through ``config.load()`` / ``config.apply()`` -- could not apply
a column restriction at all. ``--config catalog.json`` gave you an
object-level policy, no column-level one, and no warning, because from the
file's point of view nothing was missing.
"""
import json

import pytest

from schemagate import Catalog, Principal
from schemagate import config as sgconfig
from schemagate.demo_schema import create_demo_db

TABLE = "main.hr_compensation"
SECRET = "annual_amount"

HR = Principal("okta:hr", roles={"hr"})
ANALYST = Principal("okta:analyst")


def cat():
    return Catalog().bootstrap(create_demo_db())


def write(tmp_path, obj):
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


def ddl_for(c, principal):
    doc = [d for d in c.objects() if d.qname == TABLE][0]
    return doc.render_ddl(principal=principal)


def test_the_block_reaches_the_catalog(tmp_path):
    """The whole point of the issue: a file-stated column ACL is applied."""
    c = cat()
    assert SECRET in ddl_for(c, ANALYST)          # open before
    path = write(tmp_path, {"restrict_column": {TABLE: {SECRET: ["hr"]}}})
    sgconfig.apply(c, sgconfig.load(path))
    assert SECRET not in ddl_for(c, ANALYST)      # withheld after
    assert SECRET in ddl_for(c, HR)               # role holder still sees it


def test_bare_table_name_works_like_the_other_blocks(tmp_path):
    c = cat()
    path = write(tmp_path, {"restrict_column": {"hr_compensation": {SECRET: ["hr"]}}})
    sgconfig.apply(c, sgconfig.load(path))
    assert SECRET not in ddl_for(c, ANALYST)


def test_several_columns_and_several_roles(tmp_path):
    c = cat()
    path = write(tmp_path, {"restrict_column": {
        TABLE: {SECRET: ["hr", "compliance"], "pay_grade": ["hr"]}}})
    sgconfig.apply(c, sgconfig.load(path))
    anon = ddl_for(c, ANALYST)
    assert SECRET not in anon and "pay_grade" not in anon
    assert SECRET in ddl_for(c, Principal("okta:x", roles={"compliance"}))


def test_a_typo_in_the_table_fails_loudly(tmp_path):
    """An ACL typo that reports success is a restriction that silently is not
    there. ``Catalog.restrict_column`` raises; the loader must not swallow it."""
    c = cat()
    path = write(tmp_path, {"restrict_column": {"nosuch_table": {SECRET: ["hr"]}}})
    with pytest.raises(KeyError):
        sgconfig.apply(c, sgconfig.load(path))


def test_a_typo_in_the_column_fails_loudly(tmp_path):
    c = cat()
    path = write(tmp_path, {"restrict_column": {TABLE: {"anual_amount": ["hr"]}}})
    with pytest.raises(KeyError):
        sgconfig.apply(c, sgconfig.load(path))


def test_a_misspelled_block_fails_loudly(tmp_path):
    """The failure the issue is really about: ``restrict_columns`` with an s
    used to be a no-op that looked like a policy."""
    path = write(tmp_path, {"restrict_columns": {TABLE: {SECRET: ["hr"]}}})
    with pytest.raises(ValueError, match="unknown block"):
        sgconfig.load(path)


def test_the_known_blocks_are_still_accepted(tmp_path):
    path = write(tmp_path, {"restrict": {}, "restrict_column": {},
                            "hint": {}, "describe": {}, "groups": {}})
    assert sgconfig.load(path) is not None


def test_a_non_object_value_says_so(tmp_path):
    c = cat()
    path = write(tmp_path, {"restrict_column": {TABLE: [SECRET]}})
    with pytest.raises(ValueError, match="column name"):
        sgconfig.apply(c, sgconfig.load(path))


def test_columns_are_restricted_after_describe(tmp_path):
    """Ordering: ``describe`` lands first, so a description is never generated
    against a column this block is about to withhold."""
    c = cat()
    path = write(tmp_path, {
        "describe": {TABLE: "Employee pay records."},
        "restrict_column": {TABLE: {SECRET: ["hr"]}}})
    sgconfig.apply(c, sgconfig.load(path))
    doc = [d for d in c.objects() if d.qname == TABLE][0]
    assert doc.description == "Employee pay records."
    assert SECRET not in ddl_for(c, ANALYST)


def test_a_config_without_the_block_is_unchanged(tmp_path):
    c = cat()
    path = write(tmp_path, {"restrict": {TABLE: ["payroll"]}})
    sgconfig.apply(c, sgconfig.load(path))
    assert SECRET in ddl_for(c, Principal("okta:x", roles={"payroll"}))
