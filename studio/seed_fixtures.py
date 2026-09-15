"""Put plausible rows into the demo schemas that ship as DDL only.

Five of the six schemas on the demo page were structure with nothing in it,
so five sixths of the suggested questions had no answer to record and the
page said so, over and over. Nobody clicking "paid amount per claim line"
wants to be told the wording was not recognised.

Rather than write five seed files by hand and keep them in step with five
DDLs, this reads whatever the DDL declares and fills it in: tables in
foreign-key order, parents before children, keys drawn from the parents that
exist, and values chosen from the column's name rather than its type alone.
`paid_amount REAL` becomes money, `admitted_on TEXT` becomes a date,
`is_chronic INTEGER` becomes 0 or 1, and `payer_code TEXT` becomes something
that looks like a code. A column called `name` gets a name.

It is deterministic -- same seed, same database -- so a recorded answer keeps
matching the rows behind it, and a diff of answers.json shows real change
rather than a reshuffle.

The point is not realism for its own sake. An answer table full of `text_1`
and `2026-01-01` teaches a visitor nothing about whether the SQL was right,
and the demo exists to be read.
"""
from __future__ import annotations

import datetime as _dt
import random
import re
import sqlite3
from typing import Dict, List, Optional, Sequence, Tuple

#: Rows are dated relative to this, so "today" and "the last hour" in a
#: question have something to match. Fixed per run, not per row.
#:
#: UTC, deliberately. SQLite's `date('now')`, `datetime('now')` and
#: CURRENT_DATE are all UTC, and the generated SQL is full of them. Seeding in
#: local time put every row a day out whenever the two disagreed: the newest
#: row was 2026-09-14, `date('now')` was 2026-09-15, and "readings for today"
#: came back empty from a table that had just been filled.
_NOW = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None, microsecond=0)

#: Column-name words that mean "this holds a point in time". `bucket_start`,
#: `valid_from`, `effective_date` and `installed_at` all do, and only the last
#: contains anything obviously date-shaped -- the first version missed the rest
#: and wrote "Bucket Start 1" into a column a query then called date() on.
_DATEISH = {"date", "on", "at", "dt", "day", "ts", "time", "timestamp",
            "start", "end", "from", "to", "since", "until", "bucket", "period",
            "effective", "expiry", "expires", "due", "opened", "closed",
            "created", "updated", "modified", "issued", "posted", "birth",
            "dob", "installed", "removed", "hired", "terminated"}

#: Columns that mean "not finished yet" when they are NULL. A view that says
#: `WHERE removed_at IS NULL` is asking for the current row, and one that says
#: `WHERE paid_on IS NULL` is asking for the unpaid ones -- and a seeder that
#: fills every column answers both with nothing. Real tables are full of open
#: records; these are how you say so.
_OPEN_STATE = {"removed", "closed", "ended", "end", "deleted", "cancelled",
               "canceled", "paid", "settled", "resolved", "returned",
               "completed", "finished", "terminated", "to", "until",
               "expiry", "expires", "discharged", "shipped", "delivered"}

ROWS_DEFAULT = 60
#: Lookup/reference tables want few rows and real-looking codes; fact tables
#: want enough that a GROUP BY has something to group.
ROWS_BY_PREFIX = {"ref_": 8, "dim_": 14, "lkp_": 8, "stg_": 30, "fact_": 120,
                  "bridge_": 40, "v_": 0}

_FIRST = ["Ada", "Ben", "Carlos", "Dara", "Elif", "Farid", "Grace", "Hana",
          "Ivan", "Jun", "Kofi", "Lena", "Mateo", "Nadia", "Omar", "Priya",
          "Quinn", "Rosa", "Sven", "Tara", "Umar", "Vera", "Wei", "Yusuf"]
_LAST = ["Okafor", "Tanaka", "Sharma", "Vega", "Nowak", "Haddad", "Lindqvist",
         "Moreau", "Rossi", "Kowalski", "Silva", "Nakamura", "Owusu", "Petrov",
         "Ibrahim", "Larsen", "Costa", "Duarte", "Fischer", "Marchetti"]
_ORG = ["Acme Foods", "Borealis Ltd", "Cirrus GmbH", "Delta Retail",
        "Eastwind SA", "Fjord Logistics", "Granite Works", "Helios BV",
        "Ionic Labs", "Juniper Foods", "Kestrel Parts", "Lumen Health",
        "Meridian Freight", "Northwind Trading", "Oakline Traders"]
_CITY = ["Dublin", "Berlin", "Lyon", "Utrecht", "Malmo", "Porto", "Kraków",
         "Bologna", "Aarhus", "Ghent"]
_COUNTRY = ["IE", "DE", "FR", "NL", "SE", "PT", "PL", "IT", "DK", "BE"]


def _words(col: str) -> set:
    return set(re.split(r"[^a-z0-9]+", col.lower()))


class _Gen:
    """Values for one column, chosen once so a column stays consistent."""

    def __init__(self, rnd: random.Random, table: str, col: str, decl: str,
                 vocab_size: int = 6):
        self.r, self.table, self.col = rnd, table, col
        self.decl = (decl or "TEXT").upper()
        w = _words(col)
        self.w = w
        self.numeric = any(t in self.decl for t in ("INT", "REAL", "NUM", "DEC", "FLOA", "DOUB"))
        self.integral = "INT" in self.decl
        # A small fixed vocabulary per column, so GROUP BY produces groups.
        self.vocab: Optional[List[str]] = None
        for key, opts in (
            ({"status", "state"}, ["open", "closed", "pending", "settled", "void"]),
            ({"type", "kind"}, ["standard", "priority", "bulk", "trial"]),
            ({"plan", "tier"}, ["bronze", "silver", "gold", "platinum"]),
            ({"gender", "sex"}, ["F", "M", "X"]),
            ({"channel", "source"}, ["web", "phone", "partner", "field"]),
            ({"severity", "priority"}, ["low", "medium", "high", "critical"]),
            ({"reason"}, ["price", "damage", "duplicate", "late", "other"]),
            ({"department", "dept", "team"}, ["Engineering", "Finance", "Sales",
                                              "Operations", "Customer Service"]),
            ({"specialty"}, ["cardiology", "oncology", "primary care", "orthopedics"]),
            ({"currency"}, ["EUR", "GBP", "USD"]),
            ({"country"}, _COUNTRY),
            ({"city", "town"}, _CITY),
        ):
            if w & key:
                self.vocab = opts
                break

    def value(self, i: int):
        w, r = self.w, self.r
        if self.vocab is not None and not self.numeric:
            return r.choice(self.vocab)
        if self.numeric:
            if w & {"is", "has", "flag", "active", "chronic", "terminal", "current",
                    "deleted", "paid", "closed"} and self.integral and not (w & {"amount", "total"}):
                return r.randint(0, 1)
            if w & {"year"}:
                return r.randint(2024, 2026)
            if w & {"month"}:
                return r.randint(1, 12)
            if w & {"day", "days", "los", "age", "count", "qty", "quantity",
                    "units", "num", "seq", "line", "no", "rank", "score"}:
                return r.randint(1, 40)
            if w & {"amount", "total", "cost", "price", "salary", "paid", "charge",
                    "balance", "spend", "revenue", "premium", "fee", "value", "rate"}:
                v = round(r.uniform(20, 9000), 2)
                return int(v) if self.integral else v
            if w & {"pct", "percent", "ratio"}:
                return round(r.uniform(0, 1), 3)
            return r.randint(1, 500) if self.integral else round(r.uniform(1, 500), 2)
        # text
        if w & _DATEISH or "DATE" in self.decl or "TIME" in self.decl:
            # Clustered on the recent past, not scattered over a year. Seven of
            # the demo questions ask about "today", "right now", "the last
            # month" or "the last hour"; against uniformly-spread dates every
            # one of them matched nothing and the answer table came back empty.
            # A quarter land inside the last day, two thirds inside the last
            # month, and the tail goes back a year so a yearly GROUP BY still
            # has something to group.
            p = r.random()
            if p < 0.25:
                delta = _dt.timedelta(seconds=r.randint(0, 86400))
            elif p < 0.65:
                delta = _dt.timedelta(days=r.randint(1, 30), seconds=r.randint(0, 86400))
            else:
                delta = _dt.timedelta(days=r.randint(31, 365), seconds=r.randint(0, 86400))
            when = _NOW - delta
            # A timestamp column gets a time; a plain date does not.
            if (w & {"at", "ts", "time", "timestamp"}) or "TIME" in self.decl:
                return when.strftime("%Y-%m-%d %H:%M:%S")
            return when.strftime("%Y-%m-%d")
        if w & {"email"}:
            return "%s.%s@example.com" % (r.choice(_FIRST).lower(), r.choice(_LAST).lower())
        if w & {"phone"}:
            return "+353 1 %03d %04d" % (r.randint(100, 999), r.randint(1000, 9999))
        if w & {"code", "sku", "number", "ref", "reference", "tracking", "npi", "mrn"}:
            return "%s-%05d" % (self.col[:3].upper(), r.randint(1, 99999))
        if w & {"name", "label", "title", "description", "desc"}:
            if w & {"first"}:
                return r.choice(_FIRST)
            if w & {"last", "surname", "family"}:
                return r.choice(_LAST)
            # The table decides as much as the column does: `ref_payer.name`
            # is an organisation, `emp_employee.name` is a person, and both
            # columns are called "name".
            org = {"payer", "provider", "supplier", "vendor", "carrier", "org",
                   "company", "customer", "account", "employer", "plan",
                   "merchant", "counterparty", "bank", "insurer", "facility"}
            person = {"member", "employee", "patient", "person", "contact",
                      "subscriber", "user", "staff", "physician", "doctor"}
            ctx = w | _words(self.table)
            if ctx & person and not (w & org):
                return "%s %s" % (r.choice(_FIRST), r.choice(_LAST))
            if ctx & org:
                return r.choice(_ORG)
            if w & {"display", "full"} or self.col.lower() in ("name", "label"):
                return "%s %s" % (r.choice(_FIRST), r.choice(_LAST))
            return "%s %s" % (r.choice(["Standard", "Premium", "Basic", "Extended"]),
                              self.table.split("_")[-1].title())
        if w & {"address", "street", "line1", "line"}:
            return "%d %s Street" % (r.randint(1, 120), r.choice(_LAST))
        if w & {"city", "town"}:
            return r.choice(_CITY)
        if w & {"country"}:
            return r.choice(_COUNTRY)
        return "%s %d" % (self.col.replace("_", " ").title(), i)


def _tables(con: sqlite3.Connection, schema: str = "main") -> List[str]:
    q = "SELECT name FROM %s.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%%'" % schema
    return [r[0] for r in con.execute(q)]


def _fks(con, schema: str, table: str) -> List[Tuple[str, str, str]]:
    out = []
    for r in con.execute('PRAGMA %s.foreign_key_list("%s")' % (schema, table)):
        out.append((r[3], r[2], r[4]))          # (from_col, ref_table, to_col)
    return out


def _order(con, schema: str, tables: Sequence[str]) -> List[str]:
    """Parents before children; a cycle is broken rather than raised on."""
    deps = {t: {p for _, p, _ in _fks(con, schema, t) if p in tables and p != t}
            for t in tables}
    out, seen = [], set()
    while len(out) < len(tables):
        ready = [t for t in tables if t not in seen and not (deps[t] - seen)]
        if not ready:                            # cycle: take the least-blocked
            ready = [min((t for t in tables if t not in seen),
                         key=lambda t: len(deps[t] - seen))]
        for t in sorted(ready):
            out.append(t); seen.add(t)
    return out


def _n_rows(table: str) -> int:
    for pre, n in ROWS_BY_PREFIX.items():
        if table.startswith(pre):
            return n
    return ROWS_DEFAULT


def seed(con: sqlite3.Connection, schema: str = "main", seed_value: int = 11) -> Dict[str, int]:
    """Fill every table in `schema`. Returns rows written per table."""
    r = random.Random("%s:%d" % (schema, seed_value))
    written: Dict[str, int] = {}
    keys: Dict[str, List] = {}                   # table -> its pk values
    tables = _tables(con, schema)
    for table in _order(con, schema, tables):
        cols = list(con.execute('PRAGMA %s.table_info("%s")' % (schema, table)))
        if not cols:
            continue
        fk = {f: (p, t) for f, p, t in _fks(con, schema, table)}
        pk = [c[1] for c in cols if c[5]]
        gens = {c[1]: _Gen(r, table, c[1], c[2]) for c in cols}
        n = _n_rows(table)
        rows, pks = [], []
        for i in range(1, n + 1):
            vals = []
            for c in cols:
                name, decl, notnull, ispk = c[1], (c[2] or ""), c[3], c[5]
                if ispk and ("INT" in decl.upper() or not decl):
                    vals.append(i); continue
                # An unfinished record: NULL where a column means "this ended".
                # About half open, so both "still open" and "already closed"
                # questions have rows.
                if (not notnull and not ispk and name not in fk
                        and (_words(name) & _OPEN_STATE) and r.random() < 0.5):
                    vals.append(None); continue
                if name in fk:
                    parent, _ = fk[name]
                    pool = keys.get(parent) or []
                    # A nullable orphan now and then is realistic; a NOT NULL
                    # one is a constraint failure, so never there.
                    if pool:
                        vals.append(r.choice(pool) if (notnull or r.random() > 0.05) else None)
                    else:
                        vals.append(None if not notnull else i)
                    continue
                vals.append(gens[name].value(i))
            rows.append(vals)
            if len(pk) == 1:
                pks.append(vals[[c[1] for c in cols].index(pk[0])])
        if rows:
            ph = ",".join("?" * len(cols))
            con.executemany('INSERT OR IGNORE INTO %s."%s" VALUES (%s)' % (schema, table, ph), rows)
            written[table] = con.execute('SELECT COUNT(*) FROM %s."%s"' % (schema, table)).fetchone()[0]
        keys[table] = pks
    con.commit()
    return written


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
    import schema_fixture_health as H                          # noqa: E402
    con = sqlite3.connect(":memory:")
    con.executescript(H.DDL)
    w = seed(con)
    print("clinical: %d tables, %d rows" % (len(w), sum(w.values())))
    for t, n in list(w.items())[:5]:
        print("   %-24s %4d" % (t, n))
