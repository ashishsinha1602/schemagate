"""Tables that join INTO the selection: off by default, and never past the caller's visibility."""
from schemagate import Catalog, Principal
from schemagate.models import Column, ForeignKey, ObjectDoc


def warehouse():
    cat = Catalog()
    cat.add(ObjectDoc(name="subject_offered", columns=[Column("subject_key", "TEXT", pk=True),
                                                       Column("subject_title", "TEXT"),
                                                       Column("term_code", "TEXT")]))
    # the bridge: shares no word with the question, points at the parent
    cat.add(ObjectDoc(name="tip_detail", columns=[Column("subject_key", "TEXT"), Column("isbn", "TEXT"),
                                                  Column("record_count", "INTEGER")],
                      foreign_keys=[ForeignKey(["subject_key"], "subject_offered", ["subject_key"])]))
    cat.add(ObjectDoc(name="secret_ledger", roles=["finance"],
                      columns=[Column("subject_key", "TEXT"), Column("amount", "NUMERIC")],
                      foreign_keys=[ForeignKey(["subject_key"], "subject_offered", ["subject_key"])]))
    for i in range(6):
        cat.add(ObjectDoc(name=f"unrelated_{i}", columns=[Column("id", "INTEGER", pk=True),
                                                          Column(f"misc_{i}", "TEXT")]))
    return cat.index()


Q = "subject titles offered in each term"


def names(sel):
    return {h.doc.name for h in sel.hits}


def test_default_is_unchanged():
    cat = warehouse()
    assert names(cat.select(Q, top_k=1)) == names(cat.select(Q, top_k=1, expand_inward=0))
    assert "tip_detail" not in names(cat.select(Q, top_k=1))


def test_inward_adds_the_child_that_points_at_a_chosen_table():
    cat = warehouse()
    sel = cat.select(Q, top_k=1, expand_inward=len(cat.objects()))
    assert "subject_offered" in names(sel)
    assert "tip_detail" in names(sel)
    assert next(h for h in sel.hits if h.doc.name == "tip_detail").reason == "fk"


def test_inward_grows_the_answer_and_keeps_the_ranked_picks():
    cat = warehouse()
    plain = cat.select(Q, top_k=1)
    wide = cat.select(Q, top_k=1, expand_inward=len(cat.objects()))
    assert names(plain) <= names(wide)


def test_inward_never_adds_a_table_the_caller_cannot_see():
    cat = warehouse()
    analyst = Principal("okta:analyst")
    sel = cat.select(Q, top_k=1, principal=analyst, expand_inward=len(cat.objects()))
    assert "secret_ledger" not in names(sel)
    finance = Principal("okta:fin", roles={"finance"})
    assert "secret_ledger" in names(cat.select(Q, top_k=1, principal=finance, expand_inward=len(cat.objects())))
