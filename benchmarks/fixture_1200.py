"""A ~1,200-object schema, because the shipped fixtures cannot exhibit the claim.

Every open measurement problem in this repository has one cause: the largest
fixture is 260 objects and the interesting ones are 27-51, so a term cannot
reach half the corpus. The headline finding -- that cataloguing a large schema
made retrieval *worse*, because every description repeated the domain's
vocabulary until the user's own word carried almost no information -- is not
reproducible on anything shipped here. It was measured once, on a private
1,245-object schema, and has been quoted ever since without a fixture behind it.

This builds one that can exhibit it, deterministically, from a seed.

    python benchmarks/fixture_1200.py --target oracle --create
    python benchmarks/fixture_1200.py --target oracle --measure

The shape, which is the whole point:

  * ~1,200 tables and views in realistic name families, so `contact` appears in
    a handful of NAMES and its idf in the name index stays high.
  * descriptions written in ONE voice, the way a cataloguer or a model writes
    them, so `contact` reaches most of the 1,200 DESCRIPTIONS and its idf in a
    flat bag of words collapses.
  * one wide fact table with meaningful column names, so column ranking has
    something to rank -- across all six shipped schemas exactly one object
    exceeds the 40-column budget and its columns are called attribute_000
    upward, which nothing can rank.
  * a question set that SHARES vocabulary with the corpus. The paraphrase set
    deliberately shares none, which is why a df diagnostic run against it sees
    nothing at all.

Nothing here is tuned until a claim appears. The corpus *shape* is specified up
front -- how many names and how many descriptions carry the term -- and what is
then measured is whether a flat bag is worse than fielded scoring on it. That
question is allowed to come back "no".
"""
from __future__ import annotations

import argparse
import os
import pathlib
import random
import sys

SEED = 20260917

#: Names containing `contact`. Chosen so idf_name = log(1 + (N-df+.5)/(df+.5))
#: lands near 4.3 at N=1200 -- the value the original finding reported for a
#: term that is still informative.
CONTACT_NAME_FAMILY = 16

#: Descriptions containing `contact`. Chosen so the same term's idf in a flat
#: bag lands near 0.15 -- the value the original finding reported once every
#: description had been written in the domain's own vocabulary.
CONTACT_DESCRIPTION_COUNT = 1035

TARGET_OBJECTS = 1200

#: One wide fact table, in the 150-200 column band, with names a question can
#: actually prefer between.
WIDE_TABLE = "crm_engagement_fact"
WIDE_COLUMNS = 176

SCHEMA = "SGBENCH"

# --------------------------------------------------------------------------
# the corpus
# --------------------------------------------------------------------------

#: Entity families. `contact` is one of sixty-odd, which is what keeps its name
#: idf high while its description idf collapses -- the asymmetry being measured.
ENTITIES = [
    "contact", "company", "deal", "invoice", "payment", "ticket", "campaign",
    "lead", "account", "opportunity", "quote", "order", "shipment", "product",
    "price", "discount", "refund", "subscription", "renewal", "contract",
    "employee", "department", "team", "role", "permission", "session",
    "document", "template", "workflow", "task", "reminder", "notification",
    "message", "thread", "attachment", "comment", "reaction", "mention",
    "segment", "audience", "channel", "source", "medium", "touchpoint",
    "journey", "milestone", "forecast", "target", "quota_plan", "territory",
    "region", "currency", "tax", "ledger", "journal", "budget", "expense",
    "vendor", "purchase", "receipt", "asset", "licence", "integration",
    "webhook", "api_key", "audit", "consent", "preference", "survey",
]

SUFFIXES = [
    "", "_list", "_import_log", "_tag", "_note", "_history", "_audit",
    "_setting", "_status", "_type", "_link", "_owner", "_share", "_archive",
    "_draft", "_snapshot", "_rollup", "_queue", "_error", "_mapping",
]

#: The single voice. This is the realistic failure: a cataloguer -- human or
#: model -- told to describe a CRM writes every description in the CRM's own
#: words, so the word the user is most likely to type ends up in almost every
#: document and stops discriminating between them.
ONE_VOICE = (
    "Operational record in the customer contact platform. Holds {what} used by "
    "contact management, contact reporting and downstream contact analytics, "
    "and is maintained by the CRM data team as part of the contact data model."
)

#: The remainder, in a voice that does not mention the term, so the corpus is
#: not uniformly saturated.
OTHER_VOICE = (
    "Reference record in the finance and operations subject area. Holds {what} "
    "used by reconciliation and period-end reporting."
)


def _object_names():
    """~1,200 names, `contact` appearing in exactly CONTACT_NAME_FAMILY."""
    names = []
    # the contact family first, at a fixed size
    for suffix in SUFFIXES[:CONTACT_NAME_FAMILY]:
        names.append(f"crm_contact{suffix}")
    assert len(names) == CONTACT_NAME_FAMILY

    prefix_for = {
        "invoice": "bill", "payment": "bill", "refund": "bill", "tax": "fin",
        "ledger": "fin", "journal": "fin", "budget": "fin", "expense": "fin",
        "employee": "hr", "department": "hr", "team": "hr", "role": "hr",
        "vendor": "sup", "purchase": "sup", "receipt": "sup", "asset": "ops",
    }
    for entity in ENTITIES:
        if entity == "contact":
            continue
        prefix = prefix_for.get(entity, "crm")
        for suffix in SUFFIXES:
            if len(names) >= TARGET_OBJECTS:
                break
            names.append(f"{prefix}_{entity}{suffix}")
        if len(names) >= TARGET_OBJECTS:
            break
    # de-duplicate defensively without disturbing order
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out[:TARGET_OBJECTS]


def build_spec():
    """Deterministic: (name, kind, description, [(col, type)]) for every object."""
    rng = random.Random(SEED)
    names = _object_names()

    # Which objects get the saturated voice. The contact-named family is always
    # included -- a catalogue would hardly describe crm_contact without the word
    # -- and the rest are drawn by seeded shuffle so the choice is not
    # correlated with anything else in the corpus.
    rest = names[CONTACT_NAME_FAMILY:]
    rng.shuffle(rest)
    saturated = set(names[:CONTACT_NAME_FAMILY])
    saturated.update(rest[:max(0, CONTACT_DESCRIPTION_COUNT - CONTACT_NAME_FAMILY)])

    base_cols = [
        ("id", "NUMBER"), ("created_at", "DATE"), ("updated_at", "DATE"),
        ("status", "VARCHAR2(30)"), ("owner_id", "NUMBER"),
    ]
    extra_pool = [
        ("display_name", "VARCHAR2(120)"), ("external_ref", "VARCHAR2(60)"),
        ("amount", "NUMBER(14,2)"), ("quantity", "NUMBER"),
        ("is_active", "NUMBER(1)"), ("notes", "VARCHAR2(400)"),
        ("region_code", "VARCHAR2(10)"), ("source_system", "VARCHAR2(40)"),
    ]

    spec = []
    for i, name in enumerate(names):
        what = name.replace("_", " ")
        voice = ONE_VOICE if name in saturated else OTHER_VOICE
        description = voice.format(what=what)
        kind = "VIEW" if i % 7 == 6 else "TABLE"
        cols = list(base_cols)
        for c in extra_pool[: 2 + (i % 5)]:
            cols.append(c)
        fk = FOREIGN_KEYS.get(name)
        if fk and fk[0] not in [c for c, _ in cols]:
            cols.append((fk[0], "NUMBER"))
        # A view cannot carry a constraint, so anything with a declared key is
        # a table. Without this a family member could land on the i%7 view slot
        # and silently drop its half of the join graph.
        if fk:
            kind = "TABLE"
        spec.append((name, kind, description, cols))

    spec.append((WIDE_TABLE, "TABLE",
                 ONE_VOICE.format(what="engagement measures per contact"),
                 _wide_columns()))
    return spec


def _wide_columns():
    """176 columns whose names a question can discriminate between.

    The point of contrast with `wide_measurement_matrix`, whose 321 columns are
    attribute_000 upward: nothing can rank those, so the one wide object in the
    repository cannot exercise column ranking at all.
    """
    cols = [("id", "NUMBER"), ("contact_id", "NUMBER"),
            ("company_id", "NUMBER"), ("captured_on", "DATE")]
    measures = [
        "email_open", "email_click", "email_bounce", "email_reply",
        "call_inbound", "call_outbound", "call_missed", "call_duration",
        "meeting_booked", "meeting_held", "meeting_noshow",
        "web_visit", "web_pageview", "web_form_submit", "web_chat",
        "sms_sent", "sms_reply", "push_sent", "push_open",
        "deal_created", "deal_won", "deal_lost", "quote_sent",
        "invoice_raised", "invoice_paid", "invoice_overdue",
        "ticket_opened", "ticket_resolved", "ticket_reopened",
    ]
    windows = ["_7d", "_30d", "_90d", "_365d", "_lifetime"]
    for measure in measures:
        for window in windows:
            if len(cols) >= WIDE_COLUMNS:
                break
            cols.append((f"{measure}{window}", "NUMBER"))
        if len(cols) >= WIDE_COLUMNS:
            break
    while len(cols) < WIDE_COLUMNS:
        cols.append((f"reserved_measure_{len(cols):03d}", "NUMBER"))
    return cols[:WIDE_COLUMNS]


#: A declared foreign-key graph over the families above.
#:
#: Without this the fixture could not exercise the feature that makes generated
#: SQL runnable at all: a question names one table, and the join tables it
#: needs are the ones it never mentions. `child: (column, parent)`.
def _family_keys():
    """Every suffixed family member references its parent.

    This is what a real schema looks like and the previous version did not have
    it: only fourteen tables carried a key, so foreign-key expansion -- the
    thing that turns a ranked pick into a runnable join -- had almost nothing
    to follow. `crm_contact_note` without a key to `crm_contact` is not a
    realistic table, it is a table with its most important column deleted.

    Measured consequence of not having it: asked for contacts by status with
    at least one payment, selection returned six `*_status` tables from six
    unrelated domains and the model correctly refused to write SQL.
    """
    names = set(_object_names())
    out = {}
    for name in names:
        for suffix in SUFFIXES:
            if not suffix or not name.endswith(suffix):
                continue
            parent = name[: -len(suffix)]
            if parent in names and parent != name:
                out[name] = ("parent_id", parent)
            break
    return out


FOREIGN_KEYS = {
    "crm_contact_list":       ("contact_id", "crm_contact"),
    "crm_contact_note":       ("contact_id", "crm_contact"),
    "crm_contact_tag":        ("contact_id", "crm_contact"),
    "crm_contact_owner":      ("contact_id", "crm_contact"),
    "crm_contact_audit":      ("contact_id", "crm_contact"),
    "crm_contact_import_log": ("contact_id", "crm_contact"),
    "crm_contact_share":      ("contact_id", "crm_contact"),
    "crm_contact_archive":    ("contact_id", "crm_contact"),
    "crm_contact_history":    ("contact_id", "crm_contact"),
    "bill_invoice":           ("contact_id", "crm_contact"),
    "bill_payment":           ("invoice_id", "bill_invoice"),
    "bill_refund":            ("invoice_id", "bill_invoice"),
    "hr_employee":            ("department_id", "hr_department"),
    WIDE_TABLE:               ("contact_id", "crm_contact"),
}

# Hand-written cross-family keys win; the generated within-family ones fill in
# everywhere else. Order matters: `bill_payment` must point at `bill_invoice`,
# not at a `bill_pay` parent that does not exist.
for _child, _edge in _family_keys().items():
    FOREIGN_KEYS.setdefault(_child, _edge)

#: Questions that need MORE THAN ONE table to answer, which is the case the
#: single-table questions above cannot test. Scored with the strict predicate
#: -- every gold table present, not merely one of them -- because a join
#: question answered with half its tables produces SQL that does not run.
COMPLEX_QUESTIONS = [
    ("which contacts have unpaid invoices",
     {"crm_contact", "bill_invoice", "bill_payment"}),
    ("payments received against invoices per contact",
     {"crm_contact", "bill_invoice", "bill_payment"}),
    ("refunds raised against invoices",
     {"bill_invoice", "bill_refund"}),
    ("notes written on contacts and who owns them",
     {"crm_contact", "crm_contact_note", "crm_contact_owner"}),
    ("contacts on a list together with their tags",
     {"crm_contact", "crm_contact_list", "crm_contact_tag"}),
    ("employees and the department they belong to",
     {"hr_employee", "hr_department"}),
    ("which contacts failed to import and what was archived",
     {"crm_contact_import_log", "crm_contact_archive"}),
    ("email engagement for each contact",
     {"crm_contact", WIDE_TABLE}),
]

#: Questions made only of boilerplate every description shares, so no field has
#: a discriminating term and the abstention guard becomes REACHABLE.
#:
#: Kept out of the recall set deliberately. They have no sensible gold answer --
#: that is the point of them -- and mixing them into (b) would let a probe for
#: one property quietly move the number for another.
#:
#: Note the guard is not reached by `contact` itself at this corpus shape: its
#: flat idf is 0.148 (df 1,036 of 1,201 -- the 1,035 saturated descriptions plus
#: the wide table's "per contact"), and the threshold is 0.1. Those two targets
#: are not incompatible, they are 52 descriptions apart: with the idf formula
#: above, idf < 0.1 needs df >= 1,088 (90.6%), so CONTACT_DESCRIPTION_COUNT =
#: 1087 would put `contact` exactly on the cut, at idf 0.099. The spec keeps
#: 1,035 because it is pinned to the original finding's ~0.15, which sat at the
#: same coverage to a tenth of a point; the probes below reach the guard instead.
ABSTENTION_PROBES = [
    "records held and used",
    "record used by reporting",
    "holds records used",
]

#: Questions that SHARE vocabulary with the corpus. The paraphrase set shares
#: none by design, which is correct for what it measures and useless here: a df
#: diagnostic needs the user's word to actually be in the index.
QUESTIONS = [
    ("which contacts failed to import",        {"crm_contact_import_log"}),
    ("contact import log",                     {"crm_contact_import_log"}),
    ("contact tags",                           {"crm_contact_tag"}),
    ("notes written against a contact",        {"crm_contact_note"}),
    ("contact list membership",                {"crm_contact_list"}),
    ("history of changes to a contact",        {"crm_contact_history"}),
    ("who owns each contact",                  {"crm_contact_owner"}),
    ("contact sharing rules",                  {"crm_contact_share"}),
    ("archived contacts",                      {"crm_contact_archive"}),
    ("contact audit trail",                    {"crm_contact_audit"}),
    ("draft contacts not yet published",       {"crm_contact_draft"}),
    ("contact record settings",                {"crm_contact_setting"}),
    ("email opens and clicks per contact",     {WIDE_TABLE}),
    ("meetings booked per contact last 30 days", {WIDE_TABLE}),
    ("invoice payment records",                {"bill_invoice", "bill_payment"}),
    ("employee departments",                   {"hr_employee", "hr_department"}),
]


# --------------------------------------------------------------------------
# DDL
# --------------------------------------------------------------------------

def oracle_ddl(spec):
    """(creates, comments) as two lists of statements, no trailing semicolons."""
    creates, comments = [], []
    by_name = {s[0]: s for s in spec}
    for name, kind, description, cols in spec:
        if kind == "VIEW":
            continue
        body = ", ".join(f"{c} {t}" for c, t in cols)
        creates.append(
            f'CREATE TABLE {SCHEMA}."{name.upper()}" ({body}, '
            f'CONSTRAINT "PK_{name.upper()[:22]}" PRIMARY KEY ("ID"))')
        safe = description.replace("'", "''")
        comments.append(
            f'COMMENT ON TABLE {SCHEMA}."{name.upper()}" IS \'{safe}\'')
    # Constraints after every table exists, so parent order does not matter.
    present = {n for n, k, _d, _c in spec if k == "TABLE"}
    for child, (column, parent) in FOREIGN_KEYS.items():
        if child in present and parent in present:
            creates.append(
                f'ALTER TABLE {SCHEMA}."{child.upper()}" ADD CONSTRAINT '
                f'"FK_{child.upper()[:22]}" FOREIGN KEY ("{column.upper()}") '
                f'REFERENCES {SCHEMA}."{parent.upper()}" ("ID")')

    # views last: each selects from a table that now exists
    tables = [s[0] for s in spec if s[1] == "TABLE"]
    for name, kind, description, cols in spec:
        if kind != "VIEW":
            continue
        src = tables[hash(name) % len(tables)]
        picked = ", ".join(c for c, _ in by_name[src][3][:4])
        creates.append(
            f'CREATE VIEW {SCHEMA}."{name.upper()}" AS '
            f'SELECT {picked} FROM {SCHEMA}."{src.upper()}"')
        safe = description.replace("'", "''")
        comments.append(
            f'COMMENT ON TABLE {SCHEMA}."{name.upper()}" IS \'{safe}\'')
    return creates, comments


def oracle_rows(spec, per_table=3):
    """Data, because a schema with no rows cannot show sample values.

    Deliberately small and typed from the column name, the same rule
    `studio/seed_fixtures.py` uses: a column called `status` gets a status, one
    called `amount` gets money. A row that contradicts its column name is worse
    than no row.
    """
    # Parents before children, or the child's row is rejected by the very
    # constraint that makes the fixture worth having. Oracle said so out loud:
    # ORA-02291 on hr_employee, because `employee` precedes `department` in
    # the entity list and nothing had put them in dependency order.
    def _depth(name):
        seen, d = set(), 0
        while name in FOREIGN_KEYS and name not in seen:
            seen.add(name)
            name = FOREIGN_KEYS[name][1]
            d += 1
        return d

    stmts = []
    for name, kind, _desc, cols in sorted(spec, key=lambda s: _depth(s[0])):
        if kind != "TABLE":
            continue
        for r in range(per_table):
            vals = []
            for col, typ in cols:
                vals.append(_value_for(col, typ, r))
            stmts.append(
                f'INSERT INTO {SCHEMA}."{name.upper()}" '
                f'({", ".join(c for c, _ in cols)}) VALUES ({", ".join(vals)})')
    return stmts


def _value_for(col, typ, r):
    low = col.lower()
    if typ.startswith("DATE"):
        return f"SYSDATE - {r * 7}"
    if low == "status":
        return "'" + ["active", "pending", "closed"][r % 3] + "'"
    if low.endswith("_id") or low == "id":
        return str(r + 1)
    if "amount" in low:
        return f"{(r + 1) * 125.5:.2f}"
    if low == "is_active":
        return str(r % 2)
    if typ.startswith("NUMBER"):
        return str((r + 1) * 3)
    if low == "display_name":
        return f"'Record {r + 1}'"
    if low == "region_code":
        return "'" + ["EMEA", "AMER", "APAC"][r % 3] + "'"
    if low == "source_system":
        return "'" + ["crm", "billing", "import"][r % 3] + "'"
    return f"'{low}-{r + 1}'"


# --------------------------------------------------------------------------
# the same fixture on PostgreSQL
#
# Same spec, same FK graph, same rows, second dialect. A finding that holds on
# one database is a finding about that database; the point of a second target
# is that the generator, not the fixture, is what is checked in.
# --------------------------------------------------------------------------

PG_SCHEMA = "sgbench"

#: Oracle spellings in the spec, PostgreSQL spellings in the DDL. The spec is
#: kept in one dialect so the two databases get byte-for-byte the same shape.
_PG_TYPES = {"NUMBER": "NUMERIC", "VARCHAR2": "VARCHAR", "DATE": "TIMESTAMP"}


def _pg_type(typ: str) -> str:
    head, _, tail = typ.partition("(")
    mapped = _PG_TYPES.get(head, head)
    return f"{mapped}({tail}" if tail else mapped


def postgres_ddl(spec):
    """(creates, comments), the twin of oracle_ddl. Identifiers unquoted:
    they are lowercase snake_case already, which is what PostgreSQL folds to."""
    creates, comments = [], []
    by_name = {s[0]: s for s in spec}
    for name, kind, description, cols in spec:
        if kind == "VIEW":
            continue
        body = ", ".join(f"{c} {_pg_type(t)}" for c, t in cols)
        creates.append(
            f"CREATE TABLE {PG_SCHEMA}.{name} ({body}, "
            f"CONSTRAINT pk_{name} PRIMARY KEY (id))")
        safe = description.replace("'", "''")
        comments.append(f"COMMENT ON TABLE {PG_SCHEMA}.{name} IS '{safe}'")
    present = {n for n, k, _d, _c in spec if k == "TABLE"}
    for child, (column, parent) in FOREIGN_KEYS.items():
        if child in present and parent in present:
            creates.append(
                f"ALTER TABLE {PG_SCHEMA}.{child} ADD CONSTRAINT fk_{child} "
                f"FOREIGN KEY ({column}) REFERENCES {PG_SCHEMA}.{parent} (id)")
    tables = [s[0] for s in spec if s[1] == "TABLE"]
    for name, kind, description, cols in spec:
        if kind != "VIEW":
            continue
        src = tables[hash(name) % len(tables)]
        picked = ", ".join(c for c, _ in by_name[src][3][:4])
        creates.append(
            f"CREATE VIEW {PG_SCHEMA}.{name} AS SELECT {picked} FROM {PG_SCHEMA}.{src}")
        safe = description.replace("'", "''")
        comments.append(f"COMMENT ON VIEW {PG_SCHEMA}.{name} IS '{safe}'")
    return creates, comments


def postgres_rows(spec, per_table=3):
    """Twin of oracle_rows: parents first, values typed from the column name.
    Only the date literal differs, so everything else delegates."""
    def _depth(name):
        seen, d = set(), 0
        while name in FOREIGN_KEYS and name not in seen:
            seen.add(name)
            name = FOREIGN_KEYS[name][1]
            d += 1
        return d

    def _val(col, typ, r):
        if typ.startswith("DATE"):
            return f"NOW() - INTERVAL '{r * 7} days'"
        return _value_for(col, typ, r)

    stmts = []
    for name, kind, _desc, cols in sorted(spec, key=lambda s: _depth(s[0])):
        if kind != "TABLE":
            continue
        for r in range(per_table):
            vals = [_val(c, t, r) for c, t in cols]
            stmts.append(
                f"INSERT INTO {PG_SCHEMA}.{name} "
                f"({', '.join(c for c, _ in cols)}) VALUES ({', '.join(vals)})")
    return stmts


#: A local container by default. The Xmagnet dev RDS is deliberately not the
#: default: 1,200 tables is not something to put on a shared database without
#: being asked, even in a schema of their own.
PG_URL_DEFAULT = "postgresql://postgres:sgbench@127.0.0.1:5433/sgbench"


def create_postgres(spec, per_table=3):
    import time
    import psycopg
    url = os.environ.get("SGBENCH_PG_URL", PG_URL_DEFAULT)
    conn = psycopg.connect(url, autocommit=True)
    cur = conn.cursor()
    print(f"dropping and recreating schema {PG_SCHEMA} ...", flush=True)
    cur.execute(f"DROP SCHEMA IF EXISTS {PG_SCHEMA} CASCADE")
    cur.execute(f"CREATE SCHEMA {PG_SCHEMA}")

    def _run(statements, label):
        # autocommit + per-statement try: one bad statement must not abandon
        # the rest, and a fixture silently short of objects is worse than one
        # that reports what failed -- the same rule _run_batched follows.
        fails, t0 = [], time.time()
        for i, s in enumerate(statements):
            try:
                cur.execute(s)
            except Exception as e:                               # noqa: BLE001
                fails.append(str(e).splitlines()[0][:120])
        print(f"  {label}: {len(statements)} in {time.time() - t0:.0f}s", flush=True)
        return fails

    creates, comments = postgres_ddl(spec)
    f1 = _run(creates, "objects")
    f2 = _run(comments, "comments")
    f3 = _run(postgres_rows(spec, per_table=per_table), "rows")

    cur.execute("select count(*) from information_schema.tables "
                "where table_schema=%s", (PG_SCHEMA,))
    created = cur.fetchone()[0]
    cur.execute("select count(*) from pg_description d join pg_class c on "
                "c.oid=d.objoid join pg_namespace n on n.oid=c.relnamespace "
                "where n.nspname=%s and d.objsubid=0", (PG_SCHEMA,))
    commented = cur.fetchone()[0]
    cur.execute(f"select count(*) from {PG_SCHEMA}.{WIDE_TABLE}")
    wide_rows = cur.fetchone()[0]
    conn.close()
    print(f"\nobjects in {PG_SCHEMA} : {created}")
    print(f"with a description  : {commented}")
    print(f"rows in {WIDE_TABLE}: {wide_rows}")
    for label, fails in (("create", f1), ("comment", f2), ("insert", f3)):
        if fails:
            print(f"{label} failures: {len(fails)}  e.g. {fails[0]}")
    return created


# --------------------------------------------------------------------------
# the live database
# --------------------------------------------------------------------------

def _load_env(path="atp.env"):
    """Credentials into the process only. Never printed, never committed."""
    p = pathlib.Path(path)
    if not p.exists():
        p = pathlib.Path(os.environ.get("SCHEMAGATE_ATP_ENV", "")) or p
    if p.exists():
        for line in p.read_text("utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def oracle_connect(user=None, password=None):
    import oracledb
    wallet = os.environ.get("SCHEMAGATE_WALLET") or str(
        (pathlib.Path.cwd() / "wallet").resolve())
    return oracledb.connect(
        user=user or "ADMIN",
        password=password or os.environ["ADMIN_PASSWORD"],
        dsn=os.environ.get("SCHEMAGATE_ADB_DSN", "efich240h8dtycfj_high"),
        config_dir=wallet, wallet_location=wallet,
        wallet_password=os.environ.get("WALLET_PASSWORD"))


def _run_batched(cur, statements, batch=100, label=""):
    """EXECUTE IMMEDIATE in blocks, because 5,500 round trips is the slow way.

    Errors are collected rather than raised: one bad statement in a block would
    otherwise abandon the rest, and a fixture that is silently 400 objects short
    is worse than one that reports what failed.
    """
    import time
    failures, done, t0 = [], 0, time.time()
    for i in range(0, len(statements), batch):
        chunk = statements[i:i + batch]
        body = "\n".join(
            "  begin execute immediate q'[" + s + "]'; exception when others "
            "then :errs := :errs || sqlerrm || '|'; end;"
            for s in chunk)
        errs = cur.var(str)
        errs.setvalue(0, "")
        try:
            cur.execute("begin\n" + body + "\nend;", errs=errs)
            got = errs.getvalue() or ""
            if got:
                failures.extend(x for x in got.split("|") if x)
        except Exception as e:                                   # noqa: BLE001
            failures.append(f"{type(e).__name__}: {e}")
        done += len(chunk)
        if label and (i // batch) % 10 == 0:
            print(f"  {label}: {done}/{len(statements)}  "
                  f"{time.time() - t0:.0f}s", flush=True)
    return failures


def create_remote(spec, per_table=3):
    _load_env()
    admin = oracle_connect()
    cur = admin.cursor()
    pw = os.environ.get("SGBENCH_PASSWORD")
    if not pw:
        import secrets
        pw = "Sg" + secrets.token_urlsafe(18).replace("-", "_") + "9!"
        with open("atp.env", "a", encoding="utf-8") as fh:
            fh.write(f"\nSGBENCH_PASSWORD={pw}\n")
        print("  generated SGBENCH_PASSWORD and appended it to atp.env "
              "(gitignored, not printed)")
        os.environ["SGBENCH_PASSWORD"] = pw

    print("dropping and recreating the benchmark user ...", flush=True)
    for stmt in (f"DROP USER {SCHEMA} CASCADE",):
        try:
            cur.execute(stmt)
        except Exception as e:                                   # noqa: BLE001
            if "ORA-01918" not in str(e):
                print("  (drop)", str(e)[:90])
    cur.execute(f'CREATE USER {SCHEMA} IDENTIFIED BY "{pw}"')
    for stmt in (
        f"GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW TO {SCHEMA}",
        f"ALTER USER {SCHEMA} QUOTA UNLIMITED ON DATA",
    ):
        cur.execute(stmt)

    creates, comments = oracle_ddl(spec)
    print(f"creating {len(creates)} objects ...", flush=True)
    f1 = _run_batched(cur, creates, label="objects")
    print(f"commenting {len(comments)} objects ...", flush=True)
    f2 = _run_batched(cur, comments, label="comments")
    rows = oracle_rows(spec, per_table=per_table)
    print(f"inserting {len(rows)} rows ...", flush=True)
    f3 = _run_batched(cur, rows, batch=200, label="rows")
    admin.commit()

    cur.execute("select count(*) from all_objects where owner=:o "
                "and object_type in ('TABLE','VIEW')", o=SCHEMA)
    created = cur.fetchone()[0]
    cur.execute("select count(*) from all_tab_comments where owner=:o "
                "and comments is not null", o=SCHEMA)
    commented = cur.fetchone()[0]
    cur.execute(f'select count(*) from {SCHEMA}."{WIDE_TABLE.upper()}"')
    wide_rows = cur.fetchone()[0]
    admin.close()

    print(f"\nobjects in {SCHEMA} : {created}")
    print(f"with a description : {commented}")
    print(f"rows in {WIDE_TABLE}: {wide_rows}")
    for label, fails in (("create", f1), ("comment", f2), ("insert", f3)):
        if fails:
            print(f"{label} failures: {len(fails)}  e.g. {fails[0][:110]}")
    return created


# --------------------------------------------------------------------------
# the four acceptance checks
# --------------------------------------------------------------------------

def live_engine(target: str = "oracle"):
    import sqlalchemy as sa
    if target == "postgres":
        url = os.environ.get("SGBENCH_PG_URL", PG_URL_DEFAULT)
        return sa.create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    _load_env()
    wallet = os.environ.get("SCHEMAGATE_WALLET") or str(
        (pathlib.Path.cwd() / "wallet").resolve())
    dsn = os.environ.get("SCHEMAGATE_ADB_DSN", "efich240h8dtycfj_high")
    return sa.create_engine(
        f"oracle+oracledb://:@", connect_args=dict(
            user=SCHEMA, password=os.environ["SGBENCH_PASSWORD"], dsn=dsn,
            config_dir=wallet, wallet_location=wallet,
            wallet_password=os.environ.get("WALLET_PASSWORD")))


def _flat_rank(cat, question, top_k):
    """Rank by the flat bag alone -- name, prose and body in one index.

    This is what schemagate did before fielded scoring, and what most retrieval
    over a schema still does. Scored through the catalog's own `_bm25`, not a
    reimplementation, so the comparison is between two ways of using the same
    machinery rather than between this library and a straw man.
    """
    # Through the accessor, not the attribute: `_order` and `_bm25` are both
    # derived state built by the same index(), and reading either directly
    # depends on this call sitting below the explicit index() above. That is a
    # fact about this file's ordering rather than a property of it.
    order = cat._ordered()
    scores = cat._bm25.scores(question)
    pairs = [(order[i], s) for i, s in enumerate(scores) if s > 0]
    # Name as the secondary key, so this baseline is not itself decided by
    # reflection order -- the very bug the tie-determinism fix is about. A
    # comparison whose baseline wobbles measures the wobble.
    pairs.sort(key=lambda p: (-p[1], p[0]))
    return [q for q, _ in pairs[:top_k]]


def measure(top_k=6, target="oracle"):
    import math
    from schemagate import Catalog

    import pickle
    import time
    default_cache = ".sgbench_docs.pkl" if target == "oracle" else f".sgbench_docs_{target}.pkl"
    cache = pathlib.Path(os.environ.get("SGBENCH_CACHE", default_cache))
    cat = Catalog(name="sgbench")
    if cache.exists():
        cat.add_all(pickle.loads(cache.read_bytes()))
        print(f"loaded {len(cat._docs)} reflected objects from {cache}")
    else:
        print(f"reflecting {SCHEMA} from the live Autonomous Database ...",
              flush=True)
        t0 = time.time()
        cat.bootstrap(live_engine(target),
                      schemas=[PG_SCHEMA if target == "postgres" else SCHEMA])
        print(f"reflected in {time.time() - t0:.0f}s")
        cache.write_bytes(pickle.dumps(list(cat._docs.values())))
    t0 = time.time()
    cat.index()
    n = len(cat._docs)
    print(f"reflected {n} objects in {time.time() - t0:.0f}s\n")

    ok = {}

    # (a) ---------------------------------------------------------------
    print("(a) idf of 'contact'")
    idf_name = cat._bm25_name.idf.get("contact", 0.0)
    idf_flat = cat._bm25.idf.get("contact", 0.0)
    idf_prose = cat._bm25_prose.idf.get("contact", 0.0)
    print(f"    name index : {idf_name:.3f}   (target ~4.3)")
    print(f"    flat bag   : {idf_flat:.3f}   (target ~0.15)")
    print(f"    prose index: {idf_prose:.3f}")
    ok["a"] = idf_name > 3.5 and idf_flat < 0.35
    print(f"    => {'PASS' if ok['a'] else 'FAIL'}\n")

    # (b) ---------------------------------------------------------------
    print("(b) flat bag vs fielded, recall@%d over %d questions" % (top_k, len(QUESTIONS)))
    flat_hits = fielded_hits = 0
    rows = []
    for q, gold in QUESTIONS:
        flat = {name.split(".")[-1].lower() for name in _flat_rank(cat, q, top_k)}
        fld = {d.name.lower() for d in cat.select(q, top_k=top_k).objects}
        g = {x.lower() for x in gold}
        f_ok, d_ok = bool(g & flat), bool(g & fld)
        flat_hits += f_ok
        fielded_hits += d_ok
        rows.append((q, f_ok, d_ok))
    n_q = len(QUESTIONS)
    print(f"    flat bag : {flat_hits}/{n_q}  ({flat_hits / n_q * 100:.1f}%)")
    print(f"    fielded  : {fielded_hits}/{n_q}  ({fielded_hits / n_q * 100:.1f}%)")
    b_only = sum(1 for _, f, d in rows if d and not f)
    c_only = sum(1 for _, f, d in rows if f and not d)
    print(f"    fielded fixes {b_only}, breaks {c_only}")
    ok["b"] = fielded_hits > flat_hits
    print(f"    => {'REPRODUCES' if ok['b'] else 'DOES NOT REPRODUCE'}")
    for q, f, d in rows:
        if f != d:
            print(f"       {'fielded only' if d else 'flat only   '}: {q!r}")
    print()

    # (c) ---------------------------------------------------------------
    print("(c) column ranking")
    wide = next((d for d in cat._docs.values()
                 if d.name.lower() == WIDE_TABLE.lower()), None)
    changed = pinned_changed = 0
    for q, _gold in QUESTIONS:
        sel = cat.select(q, top_k=top_k)
        with_q = sel.prompt_fragment()
        without = "\n\n".join(
            d.render_ddl(40, principal=sel.principal) for d in sel.objects)
        changed += with_q != without
        if wide is not None:
            psel = cat.select(q, top_k=top_k, pin=[wide.qname])
            pw = psel.prompt_fragment()
            pwo = "\n\n".join(
                d.render_ddl(40, principal=psel.principal) for d in psel.objects)
            pinned_changed += pw != pwo
    print(f"    prompts changed, as retrieved      : {changed}/{n_q}")
    print(f"    prompts changed, wide table pinned : {pinned_changed}/{n_q}")
    if wide is not None:
        def _cols(t):
            return [l.strip().split()[0].rstrip(",") for l in t.splitlines()
                    if l.startswith("  ") and "--" not in l]
        q = "meetings booked per contact last 30 days"
        a, b = _cols(wide.render_ddl(40)), _cols(wide.render_ddl(40, question=q))
        gained = [c for c in b if c not in a]
        lost = [c for c in a if c not in b]
        print(f"    {wide.name}: {len(wide.columns)} columns")
        print(f"      question {q!r}")
        print(f"      pulled in : {gained[:6]}")
        print(f"      dropped   : {lost[:6]}")
    # As retrieved this is 0, and that is a real result about *retrieval*, not
    # about ranking: the wide fact table is never returned for any of these
    # questions, so the code under test never runs. Reported both ways rather
    # than reshaped until the number is the one wanted.
    ok["c"] = pinned_changed >= 1
    print(f"    => {'PASS (pinned)' if ok['c'] else 'FAIL'}"
          f"{'  -- but 0 as retrieved; see note' if changed == 0 else ''}\n")

    # (d) ---------------------------------------------------------------
    print("(d) abstention reachability  (guard itself is Task 1 commit 2)")
    from schemagate.catalog import _stem
    from schemagate.embedder import tokenize
    # Stemmed, because the index is. An earlier version of this check looked up
    # the raw token, so "contacts" missed the "contact" posting and every
    # question scored 0.0 -- an absence reported as a finding. The gate for
    # this whole exercise says assert the precondition is reachable before
    # asserting the conclusion; this is the same discipline applied to the
    # diagnostic itself.
    def _best(index, q):
        return max((index.idf.get(_stem(t), 0.0) for t in tokenize(q)),
                   default=0.0)

    real = [(q, _best(cat._bm25, q)) for q, _g in QUESTIONS
            if _best(cat._bm25, q) < 0.1]
    print(f"    recall questions below 0.1 in the flat bag: {len(real)}/{n_q}"
          f"   (expected 0: every one carries a discriminating term)")
    probes = [(q, _best(cat._bm25, q), _best(cat._bm25_prose, q),
               _best(cat._bm25_name, q)) for q in ABSTENTION_PROBES]
    print("    probes            flat  prose   name")
    for q, f, p, nm in probes:
        print(f"      {q!r:36} {f:5.3f}  {p:5.3f}  {nm:5.3f}")
    reachable = [p for p in probes if p[1] < 0.1]
    print(f"    probes that reach the guard: {len(reachable)}/{len(probes)}")
    ok["d"] = bool(reachable)
    print(f"    => {'REACHABLE' if ok['d'] else 'NOT REACHABLE'}\n")

    # (e) ---------------------------------------------------------------
    # Complex questions: more than one table, scored strictly. A join question
    # answered with half its tables produces SQL that does not run, so
    # any-gold-present would be the wrong predicate here and would flatter it.
    print("(e) complex questions, ALL gold tables present")
    hit = 0
    for q, gold in COMPLEX_QUESTIONS:
        g = {x.lower() for x in gold}
        got = {d.name.lower() for d in cat.select(q, top_k=max(top_k, len(g) + 2)).objects}
        full = g <= got
        hit += full
        if not full:
            print(f"      MISS {q!r}  missing {sorted(g - got)}")
    n_c = len(COMPLEX_QUESTIONS)
    print(f"    {hit}/{n_c} answered completely  ({hit / n_c * 100:.1f}%)")
    # Without FK expansion the same questions, so the contribution is visible
    # rather than asserted.
    no_fk = 0
    for q, gold in COMPLEX_QUESTIONS:
        g = {x.lower() for x in gold}
        got = {d.name.lower() for d in cat.select(
            q, top_k=max(top_k, len(g) + 2), expand_fks=False).objects}
        no_fk += g <= got
    print(f"    {no_fk}/{n_c} with foreign-key expansion turned off")
    print(f"    foreign-key expansion is worth {hit - no_fk} of {n_c}")
    ok["e"] = hit >= 1
    print(f"    => {'PASS' if ok['e'] else 'FAIL'}\n")

    # ------------------------------------------------ the apparatus sweep
    # Before publishing (b), move the apparatus and see whether the finding
    # moves with it. A result that only exists at one K, or under one notion of
    # "correct", measured the apparatus.
    print("apparatus sweep on (b): does the sign survive?")
    print(f"    {'K':>4}  {'flat':>10}  {'fielded':>10}   verdict")
    survived = 0
    grids = [1, 3, 5, 6, 10, 20, 40]
    for k in grids:
        f = d = 0
        for q, gold in QUESTIONS:
            g = {x.lower() for x in gold}
            f += bool(g & {x.split(".")[-1].lower() for x in _flat_rank(cat, q, k)})
            d += bool(g & {o.name.lower() for o in cat.select(q, top_k=k).objects})
        verdict = "fielded" if d > f else ("flat" if f > d else "tie")
        survived += verdict == "fielded"
        print(f"    {k:>4}  {f:>4}/{n_q:<5}  {d:>4}/{n_q:<5}   {verdict}")
    print(f"    fielded wins at {survived}/{len(grids)} values of K")

    # A second predicate: all-gold-present rather than any-gold-present. Every
    # gold set here has one member except two, so this mostly re-asks the same
    # question -- which is the point of checking rather than assuming.
    strict_f = strict_d = 0
    for q, gold in QUESTIONS:
        g = {x.lower() for x in gold}
        strict_f += g <= {x.split(".")[-1].lower() for x in _flat_rank(cat, q, top_k)}
        strict_d += g <= {o.name.lower() for o in cat.select(q, top_k=top_k).objects}
    print(f"    predicate=all-gold @k={top_k}: flat {strict_f}/{n_q}, "
          f"fielded {strict_d}/{n_q} -> "
          f"{'fielded' if strict_d > strict_f else 'not fielded'}")
    ok["b_sweep"] = survived >= len(grids) - 1
    print(f"    => {'SURVIVES the sweep' if ok['b_sweep'] else 'APPARATUS-DEPENDENT'}\n")

    print("summary:", {k: ("pass" if v else "fail") for k, v in ok.items()})
    return 0 if all(ok.values()) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--print-shape", action="store_true")
    ap.add_argument("--create", action="store_true",
                    help="build the fixture on the live Oracle ADB")
    ap.add_argument("--rows", type=int, default=3)
    ap.add_argument("--target", choices=("oracle", "postgres"), default="oracle",
                    help="which database to build on / measure against")
    ap.add_argument("--measure", action="store_true",
                    help="reflect the live fixture and run the four checks")
    ap.add_argument("--top-k", type=int, default=6)
    args = ap.parse_args()

    if args.create:
        if args.target == "postgres":
            create_postgres(build_spec(), per_table=args.rows)
        else:
            create_remote(build_spec(), per_table=args.rows)
        return 0
    if args.measure:
        return measure(top_k=args.top_k, target=args.target)

    spec = build_spec()
    if args.print_shape:
        names = [s[0] for s in spec]
        n_name = sum(1 for n in names if "contact" in n)
        n_desc = sum(1 for s in spec if "contact" in s[2].lower())
        print(f"objects          : {len(spec)}")
        print(f"tables           : {sum(1 for s in spec if s[1] == 'TABLE')}")
        print(f"views            : {sum(1 for s in spec if s[1] == 'VIEW')}")
        print(f"'contact' in name: {n_name}")
        print(f"'contact' in desc: {n_desc}")
        print(f"widest object    : {WIDE_TABLE} "
              f"({max(len(s[3]) for s in spec)} columns)")
        print(f"questions        : {len(QUESTIONS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
