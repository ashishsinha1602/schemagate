# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Certify schemagate against a real database, whatever the dialect.

One command, any SQLAlchemy URL: it creates a small schema under its own prefix,
runs a fixed set of questions with known answers through reflection, selection,
visibility, pulled concepts, the property graph and query-log mining, then drops
everything it made. Nothing it checks calls a model, so the verdict is about
schemagate on your engine, not about an LLM.

    schemagate certify postgresql://user:pw@host/db

A check that needs something the engine or the user does not have (comments on
SQLite, a readable statement store, Oracle's built-in graph) is reported as SKIP
with the reason, not as a failure.

Lives in the package rather than in `scripts/` because it did not work
otherwise: `schemagate certify` looked for a file three directories above the
installed module, which exists in a git checkout and nowhere else.
`scripts/certify_dialect.py` still runs; it now calls this.
"""
from __future__ import annotations

PREFIX = "schemagate_cert_"
VIEW = f"{PREFIX}v_paid_lines"
GRAPH_NAME = f"{PREFIX}graph"

#: Questions with known answers. Each passes when one of its acceptable table sets is
#: inside the selection; `~` marks a name that must be absent.
GOLDEN = [
    ("invoice totals", [{f"{PREFIX}invoice"}], 3, None),
    ("invoice totals per customer", [{f"{PREFIX}invoice", f"{PREFIX}customer"}], 3, None),
    ("lifetime spend by segment", [{f"{PREFIX}customer"}], 3, None),
    ("which products were on paid invoices", [{VIEW}, {f"{PREFIX}product", f"{PREFIX}invoice_line"}], 4, None),
    ("line value by sku", [{VIEW}, {f"{PREFIX}product", f"{PREFIX}invoice_line"}], 4, None),
    ("annual amount", [{f"~{PREFIX}payroll"}], 10, "analyst"),
    ("annual amount", [{f"{PREFIX}payroll"}], 10, "hr"),
]


def build_metadata(sa):
    meta = sa.MetaData()
    sa.Table(
        f"{PREFIX}customer", meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_number", sa.String(40), nullable=False),
        sa.Column("segment", sa.String(40), comment="Market segment"),
        sa.Column("lifetime_value", sa.Numeric(12, 2), comment="Lifetime spend"),
        comment="Customer master",
    )
    sa.Table(
        f"{PREFIX}invoice", meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("id_customer", sa.Integer, sa.ForeignKey(f"{PREFIX}customer.id")),
        sa.Column("total_gross", sa.Numeric(12, 2)),
        sa.Column("status", sa.String(20)),
    )
    sa.Table(
        f"{PREFIX}product", meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sku", sa.String(40)),
    )
    sa.Table(
        # prod_ref declares no foreign key and follows no naming convention on purpose:
        # only the view and the query log say how it joins
        f"{PREFIX}invoice_line", meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("invoice_id", sa.Integer, sa.ForeignKey(f"{PREFIX}invoice.id")),
        sa.Column("prod_ref", sa.Integer),
        sa.Column("qty", sa.Integer),
    )
    sa.Table(
        f"{PREFIX}payroll", meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("annual_amount", sa.Numeric(12, 2)),
    )
    return meta


VIEW_SQL = (f"CREATE VIEW {VIEW} AS SELECT l.id AS line_id, p.sku, l.qty * i.total_gross AS line_value "
            f"FROM {PREFIX}invoice_line l JOIN {PREFIX}product p ON l.prod_ref = p.id "
            f"JOIN {PREFIX}invoice i ON l.invoice_id = i.id WHERE i.status = 'paid'")

ROWS = {
    f"{PREFIX}customer": [{"id": 1, "account_number": "A-1", "segment": "enterprise", "lifetime_value": 1200.5},
                          {"id": 2, "account_number": "B-2", "segment": "smb", "lifetime_value": 80}],
    f"{PREFIX}invoice": [{"id": 1, "id_customer": 1, "total_gross": 100, "status": "paid"},
                         {"id": 2, "id_customer": 2, "total_gross": 50, "status": "draft"}],
    f"{PREFIX}product": [{"id": 1, "sku": "SKU-RED"}, {"id": 2, "sku": "SKU-BLUE"}],
    f"{PREFIX}invoice_line": [{"id": 1, "invoice_id": 1, "prod_ref": 1, "qty": 2},
                              {"id": 2, "invoice_id": 2, "prod_ref": 2, "qty": 1}],
    f"{PREFIX}payroll": [{"id": 1, "annual_amount": 90000}],
}

#: Statements a user might run. The second carries a value that must never be kept.
LOG_SQL = [
    f"SELECT l.qty, p.sku FROM {PREFIX}invoice_line l JOIN {PREFIX}product p ON l.prod_ref = p.id",
    f"SELECT c.account_number FROM {PREFIX}customer c WHERE c.account_number = 'SECRET-ACCT-9'",
    f"SELECT i.id FROM {PREFIX}invoice i, {PREFIX}customer c WHERE i.id_customer = c.id AND i.status = 'paid'",
]


def main(url: str) -> int:
    try:
        import sqlalchemy as sa
    except ImportError:
        print("SQLAlchemy is required: pip install schemagate")
        return 2

    from schemagate import Catalog, Principal
    from schemagate.introspect import connect_args_from_env, reflect

    analyst = Principal("db:ANALYST", roles=frozenset({"analyst"}))
    hr = Principal("db:HR", roles=frozenset({"payroll"}))
    who = {None: None, "analyst": analyst, "hr": hr}
    passed, failures, skipped = [], [], []

    def check(name, fn):
        try:
            fn()
            passed.append(name)
            print(f"  PASS  {name}")
        except Skip as s:
            skipped.append((name, str(s)))
            print(f"  SKIP  {name}: {s}")
        except Exception as e:                       # noqa: BLE001 -- report every failure, keep going
            failures.append((name, e))
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")

    # Driver options that do not fit in a URL -- an Oracle wallet, for one:
    #   SCHEMAGATE_CONNECT_ARGS='{"config_dir": "/w", "wallet_location": "/w", "wallet_password": "..."}'
    engine = sa.create_engine(url, connect_args=connect_args_from_env())
    name = engine.dialect.name
    print(f"dialect: {name}  driver: {engine.dialect.driver}")
    try:
        with engine.connect() as conn:
            version = conn.exec_driver_sql("SELECT 1").scalar()
        print(f"connection: OK (SELECT 1 -> {version})")
    except Exception as e:                           # noqa: BLE001
        print(f"connection: FAILED -- {type(e).__name__}: {e}")
        return 2

    def run(statement, ok_to_fail=False):
        try:
            with engine.begin() as conn:
                conn.execute(sa.text(statement))
        except Exception:                            # noqa: BLE001
            if not ok_to_fail:
                raise

    meta = build_metadata(sa)
    run(f"DROP PROPERTY GRAPH {GRAPH_NAME}", ok_to_fail=True)
    run(f"DROP VIEW {VIEW}", ok_to_fail=True)
    meta.drop_all(engine, checkfirst=True)
    meta.create_all(engine)
    run(VIEW_SQL)
    with engine.begin() as conn:
        for table, rows in ROWS.items():
            conn.execute(meta.tables[table].insert(), rows)
    print(f"created {len(meta.tables)} tables and 1 view prefixed {PREFIX!r}\n")

    try:
        docs = reflect(engine, include=[f"{PREFIX}%", f"{PREFIX.upper()}%"])
        by_name = {d.name.lower(): d for d in docs}

        check("reflects every table and the view",
              lambda: _assert({f"{PREFIX}customer", f"{PREFIX}invoice_line", VIEW} <= set(by_name),
                              f"found {sorted(by_name)}"))
        check("captures columns and types", lambda: _assert(
            all(c.type for c in by_name[f"{PREFIX}customer"].columns), "a column type came back empty"))
        check("captures primary keys", lambda: _assert(
            any(c.pk for c in by_name[f"{PREFIX}customer"].columns), "no primary key detected"))
        check("captures foreign keys", lambda: _assert(
            any(f"{PREFIX}customer" in fk.ref_table.lower() for fk in by_name[f"{PREFIX}invoice"].foreign_keys),
            "the invoice -> customer foreign key was not reflected"))
        check("captures the view's SQL", lambda: _assert(
            by_name[VIEW].definition and "status" in by_name[VIEW].definition.lower(),
            "the view came back without its definition"))
        check("include patterns filter", lambda: _assert(
            {d.name.lower() for d in reflect(engine, include=[f"{PREFIX}inv%", f"{PREFIX.upper()}INV%"])}
            == {f"{PREFIX}invoice", f"{PREFIX}invoice_line"}, "include pattern did not filter"))

        def comments():
            if not getattr(engine.dialect, "supports_comments", False):
                raise Skip(f"{name} has no table or column comments")
            _assert((by_name[f"{PREFIX}customer"].description or "").strip() == "Customer master"
                    and any((c.comment or "").strip() == "Lifetime spend"
                            for c in by_name[f"{PREFIX}customer"].columns),
                    "comments were written but not reflected")
        check("captures comments", comments)

        # Built the way a user's is, through bootstrap, so what is certified is what they get.
        cat = Catalog(name="certify").bootstrap(engine, include=[f"{PREFIX}%", f"{PREFIX.upper()}%"])
        cat.restrict(f"{PREFIX}payroll", ["payroll"])

        def selected(question, top_k, principal):
            return {d.name.lower() for d in cat.select(question, top_k=top_k, principal=who[principal]).objects}

        def golden(question, acceptable, top_k, principal):
            def fn():
                got = selected(question, top_k, principal)
                ok = any(all((n[1:] not in got) if n.startswith("~") else (n in got) for n in want)
                         for want in acceptable)
                _assert(ok, f"selected {sorted(got)}")
            return fn

        for question, acceptable, top_k, principal in GOLDEN:
            check(f"golden: {question!r}" + (f" as {principal}" if principal else ""),
                  golden(question, acceptable, top_k, principal))

        check("prompt fragment renders", lambda: _assert(
            "(" in cat.select("invoice totals", top_k=2).prompt_fragment(), "prompt_fragment produced nothing usable"))

        # --- concepts pulled from the database -------------------------------
        report = cat.pull_concepts(apply=True, dialect=name)
        concepts = cat.ontology.concepts

        def view_filter():
            _need_sqlglot(report)
            hits = [c for c in concepts.values()
                    if any(o.split(".")[-1].lower() == VIEW for o in c.objects)
                    and "status = 'paid'" in (c.definition or "")]
            _assert(hits, f"no concept carries the view's filter; proposals: {[p.name for p in report.proposals]}")
        check("pull: a view's filter becomes a definition", view_filter)

        def computed():
            _need_sqlglot(report)
            c = cat.ontology.get("line value")
            _assert(c is not None and "*" in (c.definition or ""), f"line_value was not defined; got {c}")
        check("pull: a computed view column defines its alias", computed)

        def comment_terms():
            if not getattr(engine.dialect, "supports_comments", False):
                raise Skip(f"{name} has no comments to pull from")
            _assert(cat.ontology.get("lifetime spend") is not None and cat.ontology.get("customer master") is not None,
                    f"comments did not become terms; proposals: {[p.name for p in report.proposals]}")
        check("pull: comments become terms", comment_terms)

        def comment_term_selects():
            if not getattr(engine.dialect, "supports_comments", False):
                raise Skip(f"{name} has no comments")
            _assert(f"{PREFIX}customer" in selected("customer master records", 2, None), "the term did not select")
        check("golden: 'customer master records' finds the table through its comment", comment_term_selects)

        def meaning_in_prompt():
            _need_sqlglot(report)
            frag = cat.select("line value by sku", top_k=4).prompt_fragment()
            _assert("line_value" in frag and "*" in frag.split("\n\n")[0], "the definition did not reach the prompt")
        check("pull: the definition reaches the prompt", meaning_in_prompt)

        # --- the property graph ----------------------------------------------
        g = cat.graph(analyst, dialect=name)

        def edges(label):
            return {(e.source.split(":", 1)[1].lower(), e.target.split(":", 1)[1].lower()) for e in g.edges if e.label == label}

        def q(table):
            d = by_name[table]
            return d.qname.lower()

        check("graph: a foreign key is an edge", lambda: _assert(
            (q(f"{PREFIX}invoice"), q(f"{PREFIX}customer")) in edges("REFERENCES"), f"{edges('REFERENCES')}"))
        check("graph: a view is derived from its tables", lambda: _assert(
            (q(VIEW), q(f"{PREFIX}product")) in edges("DERIVED_FROM"), f"{edges('DERIVED_FROM')}"))

        def view_join():
            if any("sqlglot" in n for n in g.notes):
                raise Skip("sqlglot is not installed")
            _assert((q(f"{PREFIX}invoice_line"), q(f"{PREFIX}product")) in edges("JOINS"), f"{edges('JOINS')}")
        check("graph: a join only the view declares is an edge", view_join)
        check("graph: a hidden table is nowhere in the caller's graph", lambda: _assert(
            "payroll" not in g.to_json().lower(), "payroll leaked into the analyst's graph"))
        check("graph: the authorised caller's graph has it", lambda: _assert(
            f"object:{q(f'{PREFIX}payroll')}" in {n.lower() for n in cat.graph(hr, dialect=name).nodes},
            "payroll missing from the HR graph"))

        # --- the query log -----------------------------------------------------
        with engine.connect() as conn:
            for _ in range(2):
                for s in LOG_SQL:
                    conn.execute(sa.text(s)).fetchall()
        log_report = cat.learn_from_log(LOG_SQL * 2, dialect=name)

        def mined():
            if any("sqlglot" in s for s in log_report.facts.skipped):
                raise Skip("sqlglot is not installed")
            _assert(any("prod_ref" in k for k in log_report.keys_added), f"{log_report}")
        check("query log: a join seen in SQL becomes an inferred key", mined)

        def log_selects():
            if any("sqlglot" in s for s in log_report.facts.skipped):
                raise Skip("sqlglot is not installed")
            got = selected("line quantities", 2, None)
            _assert(f"{PREFIX}product" in got, f"product not pulled in after the log: {sorted(got)}")
        check("golden: 'line quantities' now brings the product table", log_selects)

        def no_values():
            kept = str(log_report) + cat.graph(hr, dialect=name).to_json()
            kept += cat.select("account number", top_k=3, principal=hr).prompt_fragment()
            _assert("SECRET" not in kept.upper(), "a value from a logged statement was kept")
        check("query log: no value from a statement is kept", no_values)

        def store():
            from schemagate.querylog import LogUnavailable
            try:
                r = cat.learn_from_log(engine, dialect=name)
            except LogUnavailable as e:
                raise Skip(str(e)) from e
            _assert(r.facts.read > 0, "the store was read but held no statements")
        check("query log: the engine's own statement store can be read", store)

        # --- what run_query would refuse ---------------------------------------
        def scope():
            try:
                from schemagate import mcp_server
            except ImportError as e:
                raise Skip("pip install 'schemagate[mcp]' to check run_query") from e
            refused = mcp_server._check_scope(cat, f"SELECT annual_amount FROM {PREFIX}payroll", analyst)
            _assert(refused and "not available" in refused, "a hidden table was not refused")
            _assert(mcp_server._check_scope(cat, f"SELECT annual_amount FROM {PREFIX}payroll", hr) is None,
                    "the authorised caller was refused")
            graph_q = f"SELECT * FROM GRAPH_TABLE ({GRAPH_NAME} MATCH (p IS {PREFIX}payroll) COLUMNS (p.annual_amount))"
            _assert("GRAPH_TABLE" in (mcp_server._check_scope(cat, graph_q, hr) or ""), "GRAPH_TABLE was not refused")
        check("run_query: hidden tables and GRAPH_TABLE are refused", scope)

        # --- Oracle's built-in graph ------------------------------------------
        def native():
            if name != "oracle":
                raise Skip(f"{name} has no built-in property graph")
            ddl = cat.create_graph_sql(analyst, dialect="oracle", name=GRAPH_NAME)
            _assert("payroll" not in ddl.lower(), "the hidden table is in the generated graph")
            try:
                run(ddl[ddl.index("\nCREATE PROPERTY GRAPH") + 1:].rstrip().rstrip(";"))
            except Exception as e:                   # noqa: BLE001
                first = str(e).splitlines()[0]
                if "ORA-01031" in first or "privilege" in first.lower():
                    raise Skip(f"no CREATE PROPERTY GRAPH privilege: {first[:100]}") from e
                raise
            # The edge label is whatever the generator named it (long ones are shortened), so read it back.
            import re
            m = re.search(r'AS "([^"]+)"\s+KEY \([^)]*\)\s+SOURCE KEY \([^)]*\) REFERENCES "[^"]*INVOICE_LINE"'
                          r'[^\n]*\n\s+DESTINATION KEY \("PROD_REF"\)', ddl)
            _assert(m, "no edge for invoice_line.prod_ref in the generated graph")
            with engine.connect() as conn:
                rows = conn.execute(sa.text(
                    f"SELECT * FROM GRAPH_TABLE ({GRAPH_NAME} MATCH (l IS {PREFIX}invoice_line)"
                    f'-[e IS "{m.group(1)}"]->(p IS {PREFIX}product) COLUMNS (p.sku))')).fetchall()
                _assert(len(rows) == 2, f"expected 2 rows through the graph, got {rows}")
                try:
                    conn.execute(sa.text(f"SELECT * FROM GRAPH_TABLE ({GRAPH_NAME} MATCH (p IS {PREFIX}payroll) "
                                         "COLUMNS (p.annual_amount))")).fetchall()
                except Exception:                    # noqa: BLE001 -- the database refused it
                    return
                raise AssertionError("the hidden table could be read through the graph")
        check("oracle: the generated CREATE PROPERTY GRAPH runs and enforces visibility", native)
    finally:
        run(f"DROP PROPERTY GRAPH {GRAPH_NAME}", ok_to_fail=True)
        run(f"DROP VIEW {VIEW}", ok_to_fail=True)
        meta.drop_all(engine, checkfirst=True)
        engine.dispose()
        print(f"\ndropped {PREFIX!r} objects")

    print(f"\n{len(passed)} passed, {len(failures)} failed, {len(skipped)} skipped")
    for n, why in skipped:
        print(f"  skipped: {n}: {why}")
    if failures:
        print(f"\n{name.upper()} NOT CERTIFIED")
        print("Please open an issue with the output above:")
        print("  https://github.com/ashishsinha1602/schemagate/issues")
        return 1
    print(f"\n{name.upper()} CERTIFIED (SQLAlchemy {sa.__version__})")
    return 0


class Skip(Exception):
    """This check cannot run here, and why."""


def _need_sqlglot(report) -> None:
    if any("sqlglot" in s for s in report.skipped):
        raise Skip("sqlglot is not installed (pip install 'schemagate[graph]')")


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)
