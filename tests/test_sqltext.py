"""Strings and comments are read the way the database reads them, by every check.

The checks used to remove `-- ...` and `/* ... */` with one regular expression and then empty
'...' with another. A `--` or `/*` inside a string literal was taken for a comment, and the rest of
the line -- a second statement, a function that runs its text argument as a query -- was never
scanned by `check_read_only` or `run_query`'s scope check. Strings that other dialects quote
differently (MySQL backslashes, PostgreSQL dollar quotes, Oracle q'[...]') had the same gap.
"""
import pytest
from sqlalchemy import create_engine

from schemagate import Catalog, Principal
from schemagate.answer import UnsafeSQL, check_read_only
from schemagate.demo_schema import create_demo_db
from schemagate.scope import check_scope
from schemagate.sqltext import SQLTextError, scan_text, segments


@pytest.fixture(scope="module")
def cat():
    c = Catalog(name="t").bootstrap(create_engine(create_demo_db()))
    c.restrict("hr_compensation", ["payroll"])
    return c


ANA = Principal("app:ana", roles=frozenset({"sales"}))

REFUSED = [
    ("postgresql", "SELECT '--' AS a, query_to_xml('select * from hr_compensation', true, false, '') AS x"),
    ("postgresql", "SELECT '--' AS a; UPDATE crm_customer SET status = 'x'"),
    ("mssql", "SELECT '--' AS a; UPDATE crm_customer SET status = 'x'"),
    ("oracle", "SELECT '--' AS a, DBMS_XMLGEN.GETXML('SELECT * FROM hr_compensation') AS x FROM crm_customer"),
    ("sqlite", "SELECT '--' AS a, name FROM pragma_table_info('hr_compensation')"),
    ("", "SELECT '/*' AS a, query_to_xml('select * from hr_compensation', true, false, '') AS x, '*/' AS b"),
    ("mysql", "SELECT 'a\\'' AS x; DELETE FROM crm_customer -- '"),
    ("postgresql", "SELECT E'a\\'' AS x; DELETE FROM crm_customer -- '"),
    ("postgresql", "SELECT $$--$$ AS a; DELETE FROM crm_customer"),
    ("postgresql", "SELECT $q$ ' $q$ AS a; DELETE FROM crm_customer -- '"),
    ("oracle", "SELECT q'[--]' AS a, DBMS_XMLGEN.GETXML('SELECT * FROM hr_compensation') AS x FROM dual"),
    ("mysql", "SELECT 1 /*! ; DELETE FROM crm_customer */"),
    ("mysql", "SELECT 1 # '\n; DELETE FROM crm_customer -- '"),
    ("", "SELECT 'unterminated FROM hr_compensation"),
    ("", "SELECT 1 /* never closed"),
]


@pytest.mark.parametrize("dialect,sql", REFUSED)
def test_text_hidden_behind_a_quote_or_comment_marker_is_still_checked(cat, dialect, sql):
    try:
        out = check_read_only(sql, dialect)
    except UnsafeSQL:
        return
    assert check_scope(cat, out, ANA, dialect), f"accepted: {sql}"


@pytest.mark.parametrize("dialect,sql", [d for d in REFUSED if d[0]])
def test_an_unknown_dialect_is_checked_every_way(cat, dialect, sql):
    """With no dialect given, every reading is checked, so each case is refused there too."""
    try:
        out = check_read_only(sql)
    except UnsafeSQL:
        return
    assert check_scope(cat, out, ANA, ""), f"accepted with no dialect: {sql}"


ALLOWED = [
    ("postgresql", "SELECT id, 'it''s -- fine' AS note FROM crm_customer -- a comment"),
    ("mysql", "SELECT id FROM crm_customer WHERE status = 'a--b' /* why */"),
    ("mysql", "SELECT id, 3--1 AS four FROM crm_customer"),
    ("sqlite", "SELECT COUNT(*) AS n FROM crm_customer"),
    ("oracle", "SELECT id FROM crm_customer WHERE ROWNUM <= 5"),
    ("", "SELECT \"id\" FROM crm_customer WHERE status <> '/*'"),
    ("mssql", "SELECT TOP 5 [id] FROM [crm_customer] -- [not a name"),
]


@pytest.mark.parametrize("dialect,sql", ALLOWED)
def test_ordinary_queries_with_markers_inside_strings_still_run(cat, dialect, sql):
    out = check_read_only(sql, dialect)
    assert check_scope(cat, out, ANA, dialect) is None


def test_segments_follow_each_dialects_quoting():
    assert [s.kind for s in segments("SELECT '--' AS a -- c", "ansi")] == ["code", "string", "code", "comment"]
    assert scan_text("SELECT 'a\\'' AS x", "mysql") == "SELECT '' AS x"
    with pytest.raises(SQLTextError):          # standard SQL: 'a\'' opens a string that never closes
        scan_text("SELECT 'a\\'' AS x", "ansi")
    assert scan_text("SELECT $t$ -- $t$ AS a", "postgres") == "SELECT '' AS a"
    assert scan_text("SELECT q'{it's}' FROM dual", "oracle") == "SELECT '' FROM dual"
    assert scan_text("SELECT 1 /* a /* b */ c */ AS x", "postgres") == "SELECT 1   AS x"


def test_a_bare_name_shared_by_two_schemas_restricts_both():
    """`restrict('employees')` used to restrict the first match and leave the other open."""
    from schemagate.models import Column, ObjectDoc
    c = Catalog(name="two")
    for schema in ("hr", "sales"):
        c.add(ObjectDoc(name="employees", schema=schema, kind="TABLE",
                        columns=[Column(name="id", type="INTEGER"), Column(name="salary", type="INTEGER")]))
    c.index()
    c.restrict("employees", ["payroll"])
    assert all(d.roles == ["payroll"] for d in c.objects())
    c2 = Catalog(name="two-cols")
    for schema in ("hr", "sales"):
        c2.add(ObjectDoc(name="employees", schema=schema, kind="TABLE",
                         columns=[Column(name="id", type="INTEGER"), Column(name="salary", type="INTEGER")]))
    c2.index()
    c2.restrict_column("employees", "salary", ["payroll"])
    assert all(col.roles == ["payroll"] for d in c2.objects() for col in d.columns if col.name == "salary")


def test_a_mysql_executable_comment_is_refused_outright():
    with pytest.raises(UnsafeSQL):
        check_read_only("SELECT 1 /*!50000 , (SELECT 1) */")
