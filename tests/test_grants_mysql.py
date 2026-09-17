"""The MySQL grant reader, against a real server.

Skipped unless SCHEMAGATE_MYSQL_URL points at one, because the things worth
checking here are not things a fake can tell you: whether
`information_schema` is grant-filtered, which of three privilege levels a
given GRANT lands in, and which direction `mysql.role_edges` runs.

    docker run -d --name sgmysql -e MYSQL_ROOT_PASSWORD=pw -p 3307:3306 mysql:8
    SCHEMAGATE_MYSQL_URL=mysql+pymysql://root:pw@127.0.0.1:3307/app pytest tests/test_grants_mysql.py

The fixture is built and torn down by this module.
"""
from __future__ import annotations

import os

import pytest

URL = os.environ.get("SCHEMAGATE_MYSQL_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set SCHEMAGATE_MYSQL_URL")

sa = pytest.importorskip("sqlalchemy")

DDL = [
    "CREATE DATABASE IF NOT EXISTS sg_app",
    "CREATE DATABASE IF NOT EXISTS sg_other",
    "CREATE TABLE IF NOT EXISTS sg_app.orders (id INT PRIMARY KEY, total DECIMAL(10,2))",
    "CREATE TABLE IF NOT EXISTS sg_app.customers (id INT PRIMARY KEY, name VARCHAR(80))",
    "CREATE TABLE IF NOT EXISTS sg_app.salaries (id INT PRIMARY KEY, amount DECIMAL(10,2))",
    "CREATE TABLE IF NOT EXISTS sg_other.unrelated (id INT PRIMARY KEY)",
    "DROP ROLE IF EXISTS sg_role_orders",
    "CREATE ROLE sg_role_orders",
    "GRANT SELECT ON sg_app.orders TO sg_role_orders",
    "DROP USER IF EXISTS 'sg_reader'@'%'",
    "CREATE USER 'sg_reader'@'%' IDENTIFIED BY 'Sg_Reader_2026x'",
    "GRANT sg_role_orders TO 'sg_reader'@'%'",
    "SET DEFAULT ROLE ALL TO 'sg_reader'@'%'",
    "DROP USER IF EXISTS 'sg_direct'@'%'",
    "CREATE USER 'sg_direct'@'%' IDENTIFIED BY 'Sg_Direct_2026x'",
    "GRANT SELECT ON sg_app.orders TO 'sg_direct'@'%'",
    "DROP USER IF EXISTS 'sg_schema'@'%'",
    "CREATE USER 'sg_schema'@'%' IDENTIFIED BY 'Sg_Schema_2026x'",
    "GRANT SELECT ON sg_app.* TO 'sg_schema'@'%'",
    "DROP USER IF EXISTS 'sg_global'@'%'",
    "CREATE USER 'sg_global'@'%' IDENTIFIED BY 'Sg_Global_2026x'",
    "GRANT SELECT ON *.* TO 'sg_global'@'%'",
    "FLUSH PRIVILEGES",
]

TEARDOWN = [
    "DROP USER IF EXISTS 'sg_reader'@'%'",
    "DROP USER IF EXISTS 'sg_direct'@'%'",
    "DROP USER IF EXISTS 'sg_schema'@'%'",
    "DROP USER IF EXISTS 'sg_global'@'%'",
    "DROP ROLE IF EXISTS sg_role_orders",
    "DROP DATABASE IF EXISTS sg_app",
    "DROP DATABASE IF EXISTS sg_other",
]


@pytest.fixture(scope="module")
def admin():
    eng = sa.create_engine(URL)
    with eng.begin() as c:
        for stmt in DDL:
            # pymysql interpolates `%` through exec_driver_sql, and every
            # account here is 'name'@'%'.
            c.exec_driver_sql(stmt.replace("%", "%%"))
    yield eng
    with eng.begin() as c:
        for stmt in TEARDOWN:
            try:
                c.exec_driver_sql(stmt.replace("%", "%%"))
            except Exception:                                # noqa: BLE001
                pass
    eng.dispose()


def _url_as(user, password):
    tail = URL.split("@", 1)[1]
    host = tail.split("/", 1)[0]
    return "mysql+pymysql://%s:%s@%s/sg_app" % (user, password, host)


def _reader_url():
    """A user whose only SELECT arrives through a role."""
    return _url_as("sg_reader", "Sg_Reader_2026x")


def _direct_url():
    """A user granted SELECT on one table directly, not through a role."""
    return _url_as("sg_direct", "Sg_Direct_2026x")


def test_it_is_registered():
    from schemagate.grants import GRANT_READERS, ROLE_GRAPH_READERS
    assert "mysql" in GRANT_READERS
    assert "mysql" in ROLE_GRAPH_READERS


def test_table_level_grant_is_read(admin):
    from schemagate.grants import GRANT_READERS
    g = GRANT_READERS["mysql"](admin)
    assert any("sg_role_orders" in v for k, v in g.items()
               if k == ("sg_app", "orders")), g.get(("sg_app", "orders"))


def test_schema_level_grant_is_expanded_over_its_tables(admin):
    """GRANT SELECT ON sg_app.* has no per-table row anywhere; without the
    schema arm every table reachable only that way is reported unmatched."""
    from schemagate.grants import GRANT_READERS
    g = GRANT_READERS["mysql"](admin)
    for table in ("orders", "customers", "salaries"):
        assert "sg_schema" in g.get(("sg_app", table), set()), (table, g.get(("sg_app", table)))
    assert "sg_schema" not in g.get(("sg_other", "unrelated"), set()), \
        "a grant on sg_app.* must not reach sg_other"


def test_global_grant_is_expanded_everywhere(admin):
    from schemagate.grants import GRANT_READERS
    g = GRANT_READERS["mysql"](admin)
    for key in (("sg_app", "orders"), ("sg_other", "unrelated")):
        assert "sg_global" in g.get(key, set()), (key, g.get(key))


def test_no_system_schema_is_expanded(admin):
    """A global grant across mysql/performance_schema would bury the real
    objects under several hundred server tables."""
    from schemagate.grants import GRANT_READERS
    g = GRANT_READERS["mysql"](admin)
    assert not [k for k in g if k[0] in
                ("mysql", "information_schema", "performance_schema", "sys")], \
        sorted(k for k in g if k[0] == "mysql")[:5]


def test_role_graph_runs_granted_to_inheritor(admin):
    """`GRANT sg_role_orders TO sg_reader` means sg_reader inherits, so the
    map has to be {granted: {inheritors}}. Backwards is an over-grant, which
    is the direction that leaks."""
    from schemagate.grants import ROLE_GRAPH_READERS
    graph = ROLE_GRAPH_READERS["mysql"](admin)
    assert "sg_reader" in graph.get("sg_role_orders", set()), graph.get("sg_role_orders")
    assert "sg_role_orders" not in graph.get("sg_reader", set()), \
        "the graph is backwards: it maps the inheritor to the role it holds"


def test_role_graph_falls_back_without_mysql_schema_privileges(admin):
    """mysql.role_edges needs SELECT on the `mysql` schema, which an app user
    does not have. It must degrade to applicable_roles, not raise."""
    from schemagate.grants import ROLE_GRAPH_READERS
    eng = sa.create_engine(_reader_url())
    try:
        graph = ROLE_GRAPH_READERS["mysql"](eng)
    finally:
        eng.dispose()
    assert "sg_reader" in graph.get("sg_role_orders", set()), graph


def test_information_schema_is_grant_filtered(admin):
    """The premise of the whole reader. As the one-table user, the grant map
    can only name what that user may already see."""
    from schemagate.grants import GRANT_READERS
    eng = sa.create_engine(_direct_url())
    try:
        g = GRANT_READERS["mysql"](eng)
    finally:
        eng.dispose()
    seen = {k for k in g if k[0] in ("sg_app", "sg_other")}
    assert ("sg_app", "orders") in seen, seen
    assert ("sg_app", "salaries") not in seen, seen
    assert ("sg_other", "unrelated") not in seen, seen


def test_innodb_tables_is_not_used():
    """It is not grant-filtered -- it answers to PROCESS, a server-wide
    privilege unrelated to the data. Measured on 8.4.11: a user with SELECT on
    one table plus PROCESS lists every table in the instance out of
    innodb_tables. Reading it would make this reader the disclosure."""
    from schemagate import grants
    # The SQL, not the prose: this module documents *why* it avoids
    # INNODB_*, so grepping the whole source fails on its own explanation.
    sql = [v for n, v in vars(grants).items()
           if n.startswith("_MY") and isinstance(v, str)]
    assert sql, "no MySQL SQL constants found"
    for text in sql:
        assert "innodb" not in text.lower(), (
            "a MySQL query reads an INNODB_* view, which is not "
            "grant-filtered")


def test_an_object_with_no_grant_is_left_alone_not_restricted(admin):
    """"Silence is not a denial" -- the module's rule. A catalogue reflected
    wider than the grant map must keep its unmatched objects open and report
    them, never restrict them."""
    from schemagate import Catalog
    from schemagate.grants import restrict_from_grants

    cat = Catalog(name="mysql-unmatched").bootstrap(admin, schemas=["sg_app", "sg_other"])
    names = {d.name for d in cat.objects()}
    assert {"orders", "customers", "salaries", "unrelated"} <= names, names

    # Read the grants as the one-table user: the map names sg_app.orders only.
    reader = sa.create_engine(_reader_url())
    try:
        rep = restrict_from_grants(cat, reader, report=True)
    finally:
        reader.dispose()

    unmatched = set(rep.objects_unmatched)
    for name in ("salaries", "unrelated", "customers"):
        doc = next(d for d in cat.objects() if d.name == name)
        assert not doc.roles, (
            "%s had no grant row and was restricted to %r -- silence became a "
            "denial" % (name, doc.roles))
        assert any(name in u for u in unmatched), (name, sorted(unmatched))
    assert rep.objects_unmatched, str(rep)


def test_a_role_only_user_sees_no_grants_and_is_warned(admin):
    """MySQL does not show a user the grants it inherits through a role.

    Measured on 8.4.11 with the role active and CURRENT_ROLE() confirming it:
    table_privileges and schema_privileges both return zero rows. The map is
    then empty, nothing is restricted -- correct, silence is not a denial --
    and that is indistinguishable from a database needing no restriction
    unless the report says so.
    """
    from schemagate import Catalog
    from schemagate.grants import restrict_from_grants

    cat = Catalog(name="mysql-roleonly").bootstrap(admin, schemas=["sg_app"])
    before = {d.name: d.roles for d in cat.objects()}

    eng = sa.create_engine(_reader_url())
    try:
        rep = restrict_from_grants(cat, eng, report=True)
    finally:
        eng.dispose()

    assert rep.objects_restricted == 0, str(rep)
    for d in cat.objects():
        assert d.roles == before[d.name], (
            "%s changed despite an empty grant map" % d.name)
    assert any("inherits through a role" in w for w in rep.warnings), rep.warnings
