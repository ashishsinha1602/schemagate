"""The join graph's vote in ``Catalog.select`` (``Catalog._join_lift``).

A question that needs two tables says the words of one; the other joins it and
says little. On a schema full of look-alike tables that join nothing, the joined
table used to lose its slot to them. Whatever lifts a table must come from what
the caller may see: a hidden table can neither be lifted nor lift, and a key on a
column the caller may not read is not an edge.
"""
from collections import Counter

from schemagate import Catalog, Column, ForeignKey, ObjectDoc, Principal
from schemagate.querylog import LogFacts

NOBODY = Principal("okta:analyst")
SECRET = Principal("okta:lead", roles={"secret"})
Q = "average scan quality score for each dig site"
JOINED = "main.rig_passes"


def _t(name, cols, fks=(), comment=None, roles=None):
    return ObjectDoc(name=name, schema="main", kind="TABLE",
                     columns=[Column(c, "TEXT", pk=(i == 0)) for i, c in enumerate(cols)],
                     foreign_keys=[ForeignKey([c], ref, [rc]) for c, ref, rc in fks],
                     description=comment, roles=roles)


def _schema(*extra, key=True):
    """Dig sites and the rig passes over them, among notes that share the question's words and join nothing."""
    docs = [
        _t("dig_sites", ["site_id", "site_name", "region"], comment="Each dig site: its name and region."),
        _t("rig_passes", ["pass_id", "site_id", "rig_code", "q_idx"],
           fks=[("site_id", "dig_sites", "site_id")] if key else [], comment="Passes of the rig."),
    ]
    for w in ["quality", "score", "average"]:
        for j in range(3):
            docs.append(_t(f"{w}_note_{j}", [f"{w}_note_{j}_id", f"{w}_text", f"{w}_level"],
                           comment=f"Free-text {w} notes."))
    docs.extend(extra)
    cat = Catalog(name="digs")
    cat.join_weight = 0.25                 # opt-in since 1.19.0 (off by default); these tests are about it on
    cat.add_all(docs)
    return cat.index()


def _names(cat, top_k=40, **kw):
    return cat.select(Q, top_k=top_k, expand_fks=False, **kw).table_names


def _rank(cat, q=JOINED, **kw):
    names = _names(cat, **kw)
    return names.index(q) if q in names else None


def test_a_table_that_joins_a_strong_pick_rises_into_the_budget():
    cat = _schema()
    cat.join_weight = 0
    assert JOINED not in _names(cat, top_k=6)
    cat.join_weight = 0.4
    assert _names(cat, top_k=6)[:2] == ["main.dig_sites", JOINED]


def test_off_is_the_old_order():
    cat = _schema()
    cat.join_weight = 0
    a = [(h.doc.qname, h.score) for h in cat.select(Q, top_k=10).hits]
    cat.join_weight, cat.join_window = 0.4, 0
    b = [(h.doc.qname, h.score) for h in cat.select(Q, top_k=10).hits]
    assert a == b


def test_a_hidden_table_is_never_lifted_into_the_selection():
    audit = _t("site_audit", ["audit_id", "site_id", "finding"],
               fks=[("site_id", "dig_sites", "site_id")], comment="Audit findings.", roles=["secret"])
    cat = _schema(audit)
    for top_k in (2, 3, 6, 10, 40):
        for expand in (True, False):
            for who in (None, NOBODY):
                sel = cat.select(Q, top_k=top_k, principal=who, expand_fks=expand)
                assert "main.site_audit" not in sel.table_names
    assert "main.site_audit" in _names(cat, principal=SECRET)


def test_a_hidden_table_cannot_lift_what_it_joins():
    # A table only SECRET may see, matching the question well, keyed to one of the notes.
    def secret(key):
        return _t("scan_quality_secret", ["secret_id", "score_note_2_id", "avg_scan_quality_score"],
                  fks=[("score_note_2_id", "score_note_2", "score_note_2_id")] if key else [],
                  comment="Average scan quality score for each dig site.", roles=["secret"])
    keyed, unkeyed = _schema(secret(True)), _schema(secret(False))
    for top_k in (3, 6, 10, 40):
        for who in (None, NOBODY):
            a = keyed.select(Q, top_k=top_k, principal=who, expand_fks=False)
            b = unkeyed.select(Q, top_k=top_k, principal=who, expand_fks=False)
            assert a.table_names == b.table_names
            assert [h.score for h in a.hits] == [h.score for h in b.hits]
    # the same key does move the note for the caller who may see the secret table
    assert _rank(keyed, "main.score_note_2", principal=SECRET) < _rank(unkeyed, "main.score_note_2", principal=SECRET)


def test_a_key_on_a_column_the_caller_may_not_read_is_not_an_edge():
    cat = _schema()
    cat.restrict_column("rig_passes", "site_id", ["secret"])
    unkeyed = _schema(key=False)
    unkeyed.restrict_column("rig_passes", "site_id", ["secret"])
    for top_k in (3, 6, 10):
        a = cat.select(Q, top_k=top_k, principal=NOBODY, expand_fks=False)
        b = unkeyed.select(Q, top_k=top_k, principal=NOBODY, expand_fks=False)
        assert a.table_names == b.table_names
    assert _rank(cat, principal=SECRET) < _rank(unkeyed, principal=SECRET)


def test_a_guessed_key_counts_only_when_the_log_backs_it():
    cat = _schema()
    cat._docs[JOINED].foreign_keys[0].inferred = True
    assert _rank(cat) == _rank(_schema(key=False))
    cat.query_log = LogFacts(together=Counter({frozenset(("main.dig_sites", JOINED)): 3}))
    assert _rank(cat) == _rank(_schema())


def test_tables_the_query_log_reads_together_lift_each_other():
    cat = _schema(key=False)
    base = _rank(cat)
    cat.query_log = LogFacts(together=Counter({frozenset(("main.dig_sites", JOINED)): 1}))
    assert _rank(cat) == base                                   # once is not a habit
    cat.query_log = LogFacts(together=Counter({frozenset(("main.dig_sites", JOINED)): 5}))
    assert _rank(cat) < base
    cat.query_log = LogFacts(joins=Counter({("main.dig_sites", "site_id", JOINED, "site_id"): 4}))
    assert _rank(cat) < base


def test_the_query_log_cannot_reach_past_the_callers_scope():
    def build(log):
        cat = _schema(key=False)
        cat._docs["main.dig_sites"].roles = ["secret"]
        cat._stale = True
        if log:
            cat.query_log = LogFacts(
                together=Counter({frozenset(("main.dig_sites", JOINED)): 9}),
                joins=Counter({("main.dig_sites", "site_id", JOINED, "site_id"): 9}))
        return cat
    with_log, without = build(True), build(False)
    for top_k in (3, 6, 10):
        for who in (None, NOBODY):
            a = with_log.select(Q, top_k=top_k, principal=who, expand_fks=True)
            b = without.select(Q, top_k=top_k, principal=who, expand_fks=True)
            assert "main.dig_sites" not in a.table_names
            assert a.table_names == b.table_names
            assert [h.score for h in a.hits] == [h.score for h in b.hits]
    # a logged join on a column the caller may not read is not an edge either
    cat = _schema(key=False)
    cat.restrict_column("rig_passes", "site_id", ["secret"])
    base = _rank(cat, principal=NOBODY)
    cat.query_log = LogFacts(joins=Counter({("main.dig_sites", "site_id", JOINED, "site_id"): 9}))
    assert _rank(cat, principal=NOBODY) == base
