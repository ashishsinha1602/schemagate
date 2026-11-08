"""Rank fusion that knows how sure each channel is.

Measured on Snowflake's SQL-Schema-Retrieval benchmark (table level,
recall@10): with every channel voting at full weight, a schema whose column
names are codes (LiveSQLBench-Large) scored 48.2 while the vector channel
alone scored 60.8 -- the lexical channels out-voted it with one-word matches
on readable distractor tables. Three mechanisms fix that without costing the
schemas where lexical evidence is right (BEAVER):

* a column channel: an object scored by its best single column, so the one
  column whose comment says what the question asked counts, and a wide table
  cannot win by breadth;
* a lexical vote scaled by how much of the question the match explains;
* a vector vote scaled by how far its best hit stands out from the crowd.

These tests pin the mechanisms, not the benchmark numbers.
"""
import pytest

from schemagate import Catalog, Column, ObjectDoc, Principal
from schemagate.catalog import _BM25


def _bm25(*docs):
    return _BM25(list(docs))


class TestExplained:
    def test_a_document_with_every_query_term_explains_all_of_it(self):
        ix = _bm25("invoice total gross", "customer segment", "payroll amount")
        shares = ix.explained("invoice total gross")
        assert shares[0] == pytest.approx(1.0)
        assert shares[1] == 0.0 and shares[2] == 0.0

    def test_a_one_word_match_explains_a_fraction(self):
        ix = _bm25("invoice total gross", "invoice customer", "payroll amount")
        shares = ix.explained("invoice total gross")
        assert 0.0 < shares[1] < shares[0]

    def test_terms_the_field_has_never_seen_do_not_count(self):
        ix = _bm25("invoice total", "payroll")
        # "zebra" is unknown to the field: the share is over known terms only
        assert ix.explained("invoice total zebra")[0] == pytest.approx(1.0)

    def test_nothing_known_means_zero_everywhere(self):
        ix = _bm25("invoice total", "payroll")
        assert ix.explained("zebra giraffe") == [0.0, 0.0]


def _col_catalog(**kw):
    """A wide table whose many columns each share one word with the question,
    against a narrow table whose one column comment says the whole thing."""
    cat = Catalog(name="cols")
    wide = ObjectDoc(name="activity_log", schema="s", columns=[
        Column("id", "INT", pk=True), Column("site_note", "TEXT"), Column("site_region", "TEXT"),
        Column("site_code", "TEXT"), Column("site_flag", "TEXT"), Column("scan_window", "TEXT"),
        Column("entered_by", "TEXT"), Column("entered_at", "TS")])
    narrow = ObjectDoc(name="pointcloud", schema="s", columns=[
        Column("cloudregistry", "INT", pk=True), Column("zoneref", "TEXT"),
        Column("cloud_metrics", "JSON", comment="scan quality score per site, resolution and coverage")])
    filler = [ObjectDoc(name=f"other_{i}", schema="s", columns=[Column("x", "INT"), Column(f"col_{i}", "TEXT")])
              for i in range(6)]
    cat.add_all([wide, narrow, *filler])
    cat.index()
    for k, v in kw.items():
        setattr(cat, k, v)
    return cat


class TestColumnChannel:
    def test_the_best_single_column_counts_and_breadth_does_not(self):
        """Body channel alone: the table with five columns that each share a word wins by
        breadth. Column channel alone: the table whose one column says the whole thing wins."""
        q = "scan quality score per site"
        body_only = [d.name for d in _col_catalog(column_weight=0.0).select(
            q, top_k=2, vector_weight=0.0, expand_fks=False).objects]
        assert body_only[0] == "activity_log"
        col_only = [d.name for d in _col_catalog(column_weight=1.0).select(
            q, top_k=2, vector_weight=0.0, lexical_weight=0.0, expand_fks=False).objects]
        assert col_only[0] == "pointcloud"

    def test_with_every_channel_the_one_column_table_is_not_buried(self):
        cat = _col_catalog(column_weight=1.0, rrf_k=5, lexical_confidence="relative")
        names = [d.name for d in cat.select("scan quality score per site", top_k=2).objects]
        assert "pointcloud" in names

    def test_a_hidden_object_never_gets_a_column_vote(self):
        cat = _col_catalog(column_weight=1.0)
        cat.restrict("pointcloud", ["geo"])
        analyst = Principal("db:a", roles=frozenset({"analyst"}))
        names = [d.name for d in cat.select("scan quality score per site", top_k=3, principal=analyst).objects]
        assert "pointcloud" not in names

    def test_the_defaults_are_the_measured_ones(self):
        """Pinned so a refactor cannot quietly undo what was measured: K=10,
        relative lexical confidence, the column channel on, the body at half."""
        import inspect
        cat = Catalog()
        assert cat.rrf_k == 10
        assert cat.lexical_confidence == "relative"
        assert cat.column_weight == 1.0
        assert inspect.signature(Catalog.select).parameters["lexical_weight"].default == 0.5
        assert inspect.signature(Catalog.select).parameters["vector_weight"].default == 1.0


class TestLexicalConfidence:
    def test_relative_keeps_the_best_match_and_shrinks_a_one_word_match(self):
        cat = Catalog(name="rel")
        cat.add(ObjectDoc(name="invoice_totals", schema="s", columns=[Column("gross_total", "NUM")]))
        cat.add(ObjectDoc(name="invoice_notes", schema="s", columns=[Column("note", "TEXT")]))
        cat.index()
        cat.lexical_confidence = "relative"
        q = "invoice gross total"
        names = [d.name for d in cat.select(q, top_k=2, vector_weight=0.0).objects]
        assert names[0] == "invoice_totals"

    @pytest.mark.parametrize("mode", ["none", "channel", "relative", "object"])
    def test_every_mode_returns_a_full_ranking(self, mode):
        cat = _col_catalog(lexical_confidence=mode, column_weight=1.0)
        sel = cat.select("scan quality score per site", top_k=4)
        assert len(sel.objects) == 4


class TestRankFusionConstant:
    def test_the_constant_is_per_catalog(self):
        cat = _col_catalog()
        assert cat.rrf_k > 0
        cat.rrf_k = 5
        assert len(cat.select("scan quality score per site", top_k=3).objects) == 3

    def test_a_small_constant_makes_rank_matter_more_than_presence(self):
        """At K=60 an object ranked 30th on three lexical fields out-votes one
        ranked 1st on the vector field alone; at the shipped K it does not."""
        from schemagate.catalog import _RRF_K
        presence = 3 * 1.0 / (60 + 30 + 1)
        first = 1.0 / (60 + 1)
        assert presence > first
        presence = 3 * 1.0 / (_RRF_K + 30 + 1)
        first = 1.0 / (_RRF_K + 1)
        assert first > presence
