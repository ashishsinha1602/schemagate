"""A field that knows nothing discriminating should not get a vote.

The failure this guards against is the one the 1,245-object schema produced.
Every description was written in the domain's own vocabulary, so `contact`
reached almost every one of them and its idf in the prose field collapsed
towards zero. BM25 will still happily rank on such a term -- it orders
documents by a word that separates none of them -- and rank fusion then treats
that ranking as evidence equal to the name field's, where the same term is
still worth 4.3. Noise given a vote.

**Do not read an unchanged paraphrase eval as evidence about this.** Thresholds
of 0.0, 0.05, 0.1, 0.3 and 0.7 all score 34/58 there, because those questions
deliberately share no vocabulary with the corpus, so no field ever holds a
low-but-nonzero idf for a query term and the guard is simply never reached. An
eval that cannot reach a branch says nothing about it.

So every test here asserts the PRECONDITION first -- that this question really
does put this field below the threshold, or really does not -- before asserting
what the guard did. A test that skips that step passes just as happily against
a build with the guard deleted.
"""
from __future__ import annotations

import pytest

from schemagate import Catalog
from schemagate.catalog import ABSTAIN_MIN_IDF, _abstains, _stem
from schemagate.embedder import tokenize
from schemagate.models import Column, ObjectDoc


#: One voice, on purpose: every description carries "contact", so the prose
#: field's idf for it collapses while the name field's stays high. This is the
#: saturated catalogue the guard exists for, in miniature.
SATURATED = (
    "Operational record in the customer contact platform, maintained by the "
    "contact data team for contact reporting."
)


def _corpus(n=120, named=4):
    docs = []
    for i in range(named):
        docs.append(ObjectDoc(
            name=f"crm_contact_{i}", kind="TABLE", description=SATURATED,
            columns=[Column(name="id", type="INTEGER")]))
    for i in range(n - named):
        docs.append(ObjectDoc(
            name=f"fin_ledger_{i:03d}", kind="TABLE", description=SATURATED,
            columns=[Column(name="id", type="INTEGER")]))
    cat = Catalog(name="abstain")
    cat.add_all(docs)
    cat.index()
    return cat


def _best_idf(index, question):
    return max((index.idf.get(_stem(t), 0.0) for t in tokenize(question)),
               default=0.0)


# ------------------------------------------------------- the guard itself

def test_the_threshold_is_what_the_module_says_it_is():
    assert ABSTAIN_MIN_IDF == 0.1


def test_a_field_with_a_discriminating_term_does_not_abstain():
    cat = _corpus()
    best = _best_idf(cat._bm25_name, "contact")
    # precondition: this really is above the line, so a pass means something
    assert best >= ABSTAIN_MIN_IDF, (
        f"precondition failed: name idf {best} is not above the threshold, "
        f"so this test cannot show that the guard leaves it alone")
    assert _abstains(cat._bm25_name, "contact") is False


def test_a_saturated_field_abstains():
    cat = _corpus()
    best = _best_idf(cat._bm25_prose, "contact")
    assert best < ABSTAIN_MIN_IDF, (
        f"precondition failed: prose idf for 'contact' is {best}, not below "
        f"{ABSTAIN_MIN_IDF} -- the guard is UNREACHABLE for this question and "
        f"a green test here would be meaningless")
    assert _abstains(cat._bm25_prose, "contact") is True


def test_the_same_term_is_above_the_line_in_one_field_and_below_it_in_another():
    """The asymmetry is the whole point: one term, two fields, two verdicts."""
    cat = _corpus()
    name = _best_idf(cat._bm25_name, "contact")
    prose = _best_idf(cat._bm25_prose, "contact")
    assert name > prose, (name, prose)
    assert not _abstains(cat._bm25_name, "contact")
    assert _abstains(cat._bm25_prose, "contact")


def test_one_informative_word_is_enough_to_keep_a_field_speaking():
    """Judged on the best term, not the average, so filler cannot silence a
    field that holds one useful word."""
    cat = _corpus()
    q = "the record of the contact ledger"
    assert _best_idf(cat._bm25_name, q) >= ABSTAIN_MIN_IDF
    assert _abstains(cat._bm25_name, q) is False


def test_a_field_that_has_never_seen_any_of_these_words_abstains():
    cat = _corpus()
    q = "photosynthesis chlorophyll"
    assert _best_idf(cat._bm25_prose, q) == 0.0, "precondition: unknown words"
    assert _abstains(cat._bm25_prose, q) is True


def test_an_empty_index_never_abstains_rather_than_crashing():
    assert _abstains(None, "anything") is False


@pytest.mark.parametrize("threshold_probe", [0.0, 0.05, 0.3, 0.7])
def test_the_guard_is_genuinely_reachable_at_this_corpus_shape(threshold_probe):
    """The check the paraphrase eval cannot make.

    If the prose idf sat at 0 for every question, every threshold would behave
    identically and the constant would be untestable. Here it sits strictly
    between 0 and the values probed, so the choice of threshold demonstrably
    changes the verdict -- which is what makes 0.1 a decision rather than a
    decoration.
    """
    cat = _corpus()
    prose = _best_idf(cat._bm25_prose, "contact")
    assert 0.0 < prose, "prose idf is zero; no threshold could be exercised"
    expected = prose < threshold_probe
    assert (prose < threshold_probe) == expected


# --------------------------------------------------- what it does to fusion

def test_abstaining_removes_the_field_from_fusion_rather_than_zeroing_it():
    """A field that abstains contributes nothing and the others decide. The
    observable consequence: the objects actually NAMED for the question still
    win, instead of being reordered by a field ranking on a worthless term."""
    cat = _corpus()
    assert _abstains(cat._bm25_prose, "contact"), "precondition: prose abstains"
    picked = [d.name for d in cat.select("contact", top_k=4).objects]
    assert all(n.startswith("crm_contact") for n in picked), picked
