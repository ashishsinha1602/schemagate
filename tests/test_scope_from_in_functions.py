"""A FROM inside EXTRACT, SUBSTRING, TRIM and OVERLAY, or after IS [NOT] DISTINCT, takes a value, not a table.

Read as a table, `EXTRACT(YEAR FROM po.raised_on)` was refused as "not available to this caller: po.raised_on",
on every dialect: every "per year" question a model answered the standard way failed on PostgreSQL and Oracle.
A real table inside those calls -- a subquery -- is still read and still checked.
"""
import pytest
from sqlalchemy import create_engine

from schemagate import Catalog, Principal
from schemagate.demo_schema import create_demo_db
from schemagate.scope import check_scope

DIALECTS = ("postgresql", "oracle", "mysql", "mssql", "sqlite", "")
ANALYST = Principal("app:ana", roles=frozenset({"sales"}))


@pytest.fixture(scope="module")
def cat():
    c = Catalog(name="t").bootstrap(create_engine(create_demo_db()))
    c.restrict("hr_compensation", ["payroll"])
    return c


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("sql", [
    "SELECT EXTRACT(YEAR FROM po.raised_on) AS y, SUM(po.total_net) FROM sup_purchase_order po "
    "GROUP BY EXTRACT(YEAR FROM po.raised_on)",
    "SELECT EXTRACT(YEAR FROM raised_on), COUNT(*) FROM sup_purchase_order GROUP BY EXTRACT(YEAR FROM raised_on)",
    "SELECT extract ( month from e.hired_on ) m FROM hr_employee e",
    "SELECT SUBSTRING(tracking_number FROM 1 FOR 3) FROM ship_shipment",
    "SELECT TRIM(LEADING '0' FROM tracking_number) FROM ship_shipment",
    "SELECT COUNT(*) FROM sup_purchase_order WHERE status IS DISTINCT FROM 'cancelled'",
    "SELECT COUNT(*) FROM sup_purchase_order WHERE status is not distinct from 'open'",
    "SELECT COUNT(*) FROM sup_purchase_order WHERE status IS DISTINCT FROM NULL",
])
def test_a_value_from_is_not_a_table(cat, sql, dialect):
    assert check_scope(cat, sql, ANALYST, dialect) is None


@pytest.mark.parametrize("dialect", DIALECTS)
def test_a_hidden_table_inside_those_calls_is_still_refused(cat, dialect):
    for sql in [
        "SELECT EXTRACT(YEAR FROM (SELECT MAX(effective_from) FROM hr_compensation)) FROM crm_customer",
        "SELECT TRIM(BOTH FROM (SELECT MAX(currency) FROM hr_compensation)) FROM crm_customer",
        "SELECT EXTRACT(YEAR FROM hc.effective_from) FROM hr_compensation hc",
        "SELECT id FROM crm_customer WHERE id IS DISTINCT FROM (SELECT MAX(id_employee) FROM hr_compensation)",
    ]:
        assert "not available to this caller" in (check_scope(cat, sql, ANALYST, dialect) or ""), (dialect, sql)
