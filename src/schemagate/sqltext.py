# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Read SQL text the way the database will: where strings, quoted names and comments start and end.

Every safety check here looks at the statement with string literals emptied and comments removed,
so that a word inside a string is not mistaken for SQL and SQL hidden in a comment is not missed.
That only works if "inside a string" and "inside a comment" mean what they mean to the database.
Two regular expressions applied one after the other do not: stripping `--` first treats the `--`
in `'--'` as a comment and erases the rest of the line from every check, and blanking `'...'`
with SQL-standard quote rules mis-reads MySQL's `'it\\'s'`, PostgreSQL's `$$...$$` and `E'...'`,
and Oracle's `q'[...]'` -- each of which lets text the check thinks is a string run as code.

So this module scans left to right once, with the rules of a named dialect. When the dialect is
unknown, callers check every dialect's reading and refuse if any of them finds a problem: whichever
reading is the database's, it has been checked.

MySQL's `/*! ... */` is not a comment to MySQL -- it runs what is inside -- so it is refused
outright rather than read either way.
"""
from __future__ import annotations

import functools
import re
from typing import List, NamedTuple, Tuple

#: Readings to check when the dialect is not known.
ALL_MODES = ("ansi", "mysql", "postgres", "oracle")

_MODE_OF = {"postgresql": "postgres", "postgres": "postgres", "mysql": "mysql", "mariadb": "mysql",
            "oracle": "oracle", "mssql": "ansi", "tsql": "ansi", "sqlite": "ansi", "snowflake": "ansi",
            "bigquery": "mysql", "duckdb": "postgres", "": ""}


class SQLTextError(ValueError):
    """The text cannot be read safely (an unterminated string or comment, an executable comment)."""


class Segment(NamedTuple):
    kind: str        # code | string | ident | comment
    text: str        # exactly as written, quotes included
    start: int       # offset in the original text


def modes_for(dialect: str) -> Tuple[str, ...]:
    """The readings to check for a SQLAlchemy dialect name; all of them when it is not known.

    PostgreSQL is also read with backslash escapes in plain strings: a server running with
    standard_conforming_strings off reads them that way, and the check cannot see the setting."""
    m = _MODE_OF.get((dialect or "").lower(), None)
    if m == "postgres":
        return ("postgres", "mysql")
    return (m,) if m else ALL_MODES


_DOLLAR = re.compile(r"\$([A-Za-z_]\w*)?\$")
_Q_PAIRS = {"[": "]", "{": "}", "(": ")", "<": ">"}


#: The characters where a string, quoted name or comment can begin. Everything between two of them
#: is plain code, so the scanner jumps from one to the next instead of looking at every character.
#: (Oracle's q'...' and PostgreSQL's E'...' are recognised at their quote, by looking one back.)
_INTERESTING = re.compile(r"""['"`\[$#/-]""")


def segments(sql: str, mode: str = "ansi") -> List[Segment]:
    """Split ``sql`` into code, string, quoted-name and comment segments, read as ``mode`` would.

    Cached: every check reads the same statement, so it is scanned once per reading."""
    return list(_segments(sql, mode))


@functools.lru_cache(maxsize=512)
def _segments(sql: str, mode: str) -> Tuple[Segment, ...]:
    out: List[Segment] = []
    n, i, code_start = len(sql), 0, 0

    def flush(upto: int) -> None:
        if upto > code_start:
            out.append(Segment("code", sql[code_start:upto], code_start))

    while i < n:
        m = _INTERESTING.search(sql, i)
        if m is None:
            break
        i = m.start()
        c = sql[i]
        two = sql[i:i + 2]
        # -- comments ---------------------------------------------------------------
        # MySQL only reads `--` as a comment when whitespace (or the end) follows: `1--1` is 1 - -1.
        mysql_dash = mode == "mysql" and two == "--" and (i + 2 >= n or sql[i + 2] in " \t\r\n\f\v")
        if (two == "--" and mode != "mysql") or mysql_dash or (mode == "mysql" and c == "#"):
            flush(i)
            j = sql.find("\n", i)
            j = n if j < 0 else j
            out.append(Segment("comment", sql[i:j], i))
            i = code_start = j
            continue
        if two == "/*":
            if sql.startswith("/*!", i) or sql.startswith("/*M!", i):
                raise SQLTextError("contains a MySQL executable comment (/*! ... */), which runs its contents")
            flush(i)
            if mode == "postgres":            # PostgreSQL nests block comments
                depth, j = 1, i + 2
                while j < n and depth:
                    if sql.startswith("/*", j):
                        depth, j = depth + 1, j + 2
                    elif sql.startswith("*/", j):
                        depth, j = depth - 1, j + 2
                    else:
                        j += 1
                if depth:
                    raise SQLTextError("unterminated comment")
            else:
                k = sql.find("*/", i + 2)
                if k < 0:
                    raise SQLTextError("unterminated comment")
                j = k + 2
            out.append(Segment("comment", sql[i:j], i))
            i = code_start = j
            continue
        # -- Oracle q'X...X' ---------------------------------------------------------
        if mode == "oracle" and c == "'" and i > 0 and sql[i - 1] in "qQ" and i + 1 < n \
                and (i == 1 or not (sql[i - 2].isalnum() or sql[i - 2] == "_")):
            opener = sql[i + 1]
            closer = _Q_PAIRS.get(opener, opener) + "'"
            k = sql.find(closer, i + 2)
            if k < 0:
                raise SQLTextError("unterminated string")
            flush(i - 1)
            out.append(Segment("string", sql[i - 1:k + 2], i - 1))
            i = code_start = k + 2
            continue
        # -- PostgreSQL $tag$...$tag$ -------------------------------------------------
        if mode == "postgres" and c == "$" and (i == 0 or not (sql[i - 1].isalnum() or sql[i - 1] == "_")):
            m = _DOLLAR.match(sql, i)
            if m:
                k = sql.find(m.group(0), m.end())
                if k < 0:
                    raise SQLTextError("unterminated string")
                flush(i)
                end = k + len(m.group(0))
                out.append(Segment("string", sql[i:end], i))
                i = code_start = end
                continue
        # -- strings -------------------------------------------------------------------
        if c == "'" or (mode == "mysql" and c == '"'):
            backslash = mode == "mysql" or (
                mode == "postgres" and i > 0 and sql[i - 1] in "eE"
                and (i == 1 or not (sql[i - 2].isalnum() or sql[i - 2] == "_")))
            start = i - 1 if (mode == "postgres" and backslash) else i
            j = i + 1
            while True:
                if j >= n:
                    raise SQLTextError("unterminated string")
                ch = sql[j]
                if backslash and ch == "\\":
                    j += 2
                    continue
                if ch == c:
                    if sql[j + 1:j + 2] == c:   # doubled quote: still inside
                        j += 2
                        continue
                    break
                j += 1
            flush(start)
            out.append(Segment("string", sql[start:j + 1], start))
            i = code_start = j + 1
            continue
        # -- quoted names -----------------------------------------------------------------
        close = {'"': '"', "`": "`"}.get(c) if not (mode == "mysql" and c == '"') else None
        if mode == "ansi" and c == "[":
            close = "]"
        if close and (c != "`" or mode in ("mysql", "ansi")):
            j = i + 1
            while True:
                if j >= n:
                    raise SQLTextError("unterminated quoted name")
                if sql[j] == close:
                    if sql[j + 1:j + 2] == close:
                        j += 2
                        continue
                    break
                j += 1
            flush(i)
            out.append(Segment("ident", sql[i:j + 1], i))
            i = code_start = j + 1
            continue
        i += 1
    flush(n)
    return tuple(out)


@functools.lru_cache(maxsize=1024)
def scan_text(sql: str, mode: str = "ansi", string_as: str = "''") -> str:
    """The statement with comments replaced by a space and each string literal by ``string_as``.

    Quoted names are kept: they are names, and the checks need them. Cached like `segments`."""
    parts = []
    for s in _segments(sql, mode):
        if s.kind == "comment":
            parts.append(" ")
        elif s.kind == "string":
            parts.append(s.text if string_as is None else string_as if string_as != "pad" else " " * len(s.text))
        else:
            parts.append(s.text)
    return "".join(parts)


_SQLGLOT_READ = {"postgresql": "postgres", "postgres": "postgres", "mssql": "tsql", "tsql": "tsql",
                 "mysql": "mysql", "mariadb": "mysql", "oracle": "oracle", "sqlite": "sqlite"}


def statement_count(sql: str, dialect: str = "") -> int:
    """How many statements a real SQL parser reads in ``sql`` (1 without sqlglot or when it cannot parse).

    A second statement is also refused by the text checks, which see every `;` outside strings and
    comments; this is the same rule from a parser that knows each dialect's grammar. A statement the
    parser cannot read is left to the checks that refuse unparseable SQL."""
    try:
        import sqlglot
    except ImportError:
        return 1
    try:
        trees = sqlglot.parse(sql, read=_SQLGLOT_READ.get((dialect or "").lower()))
    except Exception:                                    # noqa: BLE001 -- any parse failure
        return 1
    return len([t for t in trees if t is not None])


def string_contents(seg_text: str) -> str:
    """The value of a string segment, quotes and the common escapes undone."""
    t = seg_text
    if t[:1] in "eE" and t[1:2] == "'":
        t = t[1:]
    if t[:2] in ("q'", "Q'"):
        return t[3:-2]
    m = _DOLLAR.match(t)
    if m:
        return t[len(m.group(0)):-len(m.group(0))]
    q = t[0]
    return t[1:-1].replace(q + q, q).replace("\\" + q, q)
