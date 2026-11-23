"""GHSA-2h6p-vmrf-3c76: the read-only check accepted SELECT ... INTO.

`SELECT * FROM users INTO OUTFILE '/tmp/out.txt'` and `SELECT 'x' INTO DUMPFILE '/tmp/x'` write a file on a
MySQL/MariaDB server whose login has the FILE privilege; `SELECT * INTO new_t FROM t` creates a table on
PostgreSQL and SQL Server. All were accepted as reads. The word in a string or a comment is not a clause.
"""
import pytest

from schemagate.answer import UnsafeSQL, check_read_only

WRITES = [
    "SELECT * FROM users INTO OUTFILE '/tmp/out.txt'",
    "SELECT 'x' INTO DUMPFILE '/tmp/x'",
    "SELECT * INTO OUTFILE '/tmp/y' FROM users",
    "select * from users into outfile '/tmp/z' fields terminated by ','",
    "SELECT id INTO @v FROM users",
    "SELECT * INTO new_users FROM users",
    "WITH t AS (SELECT 1 AS a) SELECT a INTO copy_t FROM t",
    "SELECT * FROM users\nINTO\nOUTFILE '/tmp/w'",
]
READS = [
    "SELECT 'into outfile' AS label FROM users",
    "SELECT * FROM users /* INTO OUTFILE */",
    "SELECT * FROM users -- into dumpfile\n",
    "SELECT intolerance, point_into FROM t",
    "SELECT name FROM users WHERE note = 'goes INTO the box'",
]


@pytest.mark.parametrize("dialect", ["mysql", "mariadb", "postgresql", "mssql", "oracle", "sqlite", ""])
@pytest.mark.parametrize("sql", WRITES)
def test_select_into_is_refused(sql, dialect):
    with pytest.raises(UnsafeSQL):
        check_read_only(sql, dialect)


@pytest.mark.parametrize("dialect", ["mysql", "postgresql", "mssql", ""])
@pytest.mark.parametrize("sql", READS)
def test_the_word_in_a_string_a_comment_or_a_longer_name_is_still_a_read(sql, dialect):
    assert check_read_only(sql, dialect)
