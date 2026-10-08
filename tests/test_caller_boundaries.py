"""Visibility at its edges: a caller who may read nothing, a caller who may read a little, and the same catalog
answering different callers one after another.

Suggested in review (dev.to, 2026-10-05): an empty eligible set must give an empty selection rather than an
invitation to fill top_k with ineligible objects, and caller-specific state must not leak in either order, from
an authorised call into a restricted one (disclosure) or from a restricted call into an authorised one (stale
suppression). Every assertion is against the caller's own eligible set, never a catalog-wide threshold.
"""
from schemagate import Principal

ANALYST = Principal("okta:analyst")
PAYROLL = Principal("okta:hrlead", roles={"payroll", "hr"})
NOBODY_ROLE = ["no-such-role"]


def _names(sel):
    return {d.name for d in sel.objects}


def _all_names(cat):
    return {d.name for d in cat.objects()}


# --- a caller who may read nothing -------------------------------------------------------------------------

def test_a_caller_with_nothing_visible_gets_an_empty_selection(cat):
    every = _all_names(cat)
    for name in every:
        cat.restrict(name, NOBODY_ROLE)
    sel = cat.select("salary and pay grade by employee", top_k=10, principal=ANALYST)
    assert sel.objects == []
    assert sel.hits == []
    prompt = sel.prompt_fragment().lower()
    assert not any(n.lower() in prompt for n in every), "an object name reached an empty caller's prompt"


def test_an_empty_caller_gets_no_meaning_lines_either(cat):
    """A business term mapped to a table the caller may not read must not describe it, even when the caller
    can see nothing else to anchor it to."""
    cat.concept("pay", synonyms=["salary"], maps=["hr_compensation.annual_amount"])
    for name in _all_names(cat):
        cat.restrict(name, NOBODY_ROLE)
    sel = cat.select("salary by employee", top_k=10, principal=ANALYST)
    assert sel.meanings == []
    assert "annual_amount" not in sel.prompt_fragment()


def test_a_caller_who_sees_a_little_gets_only_that_little(cat):
    """top_k=10 against two eligible objects: the selection may be shorter than top_k, never wider than the
    eligible set. Coverage, foreign-key expansion and the term slot all draw from the same eligible set."""
    keep = {"hr_compensation", "hr_employee"} & _all_names(cat)
    assert len(keep) == 2, "fixture changed: expected both hr tables in the demo schema"
    for name in _all_names(cat) - keep:
        cat.restrict(name, NOBODY_ROLE)
    sel = cat.select("salary and pay grade by employee", top_k=10, principal=ANALYST)
    assert _names(sel) <= keep
    assert _names(sel), "the two visible tables answer this question; an empty result would be a regression"


def test_the_stopping_point_moves_with_visibility(cat):
    """Same question, same catalog: a caller with one eligible object stops at one; a caller with every object
    eligible gets more. The cut-off follows the caller's eligible set."""
    for name in _all_names(cat) - {"hr_compensation"}:
        cat.restrict(name, ["payroll"])
    narrow = cat.select("salary and pay grade by employee", top_k=10, principal=ANALYST)
    wide = cat.select("salary and pay grade by employee", top_k=10, principal=PAYROLL)
    assert _names(narrow) == {"hr_compensation"}
    assert len(_names(wide)) > 1


# --- the same catalog, callers alternating ---------------------------------------------------------------

def _hidden_for_analyst(cat):
    cat.restrict("hr_compensation", ["payroll"])
    cat.concept("pay", synonyms=["salary"], maps=["hr_compensation.annual_amount"])


def _assert_restricted(sel):
    prompt = sel.prompt_fragment().lower()
    assert "hr_compensation" not in _names(sel)
    assert "hr_compensation" not in prompt
    assert "annual_amount" not in prompt
    assert sel.meanings == []


def _assert_authorised(sel, baseline):
    assert "hr_compensation" in _names(sel)
    assert any("annual_amount" in m for m in sel.meanings)
    assert _names(sel) == baseline, "an earlier restricted call changed what an authorised caller gets"


Q = "salary and pay grade by employee"


def test_authorised_then_restricted_does_not_disclose(cat):
    """Disclosure direction: whatever the authorised call warmed (index, caches, term matches) must not reach
    the restricted caller who follows on the same catalog instance."""
    _hidden_for_analyst(cat)
    first = cat.select(Q, top_k=10, principal=PAYROLL)
    assert "hr_compensation" in _names(first)
    for _ in range(3):
        _assert_restricted(cat.select(Q, top_k=10, principal=ANALYST))
        cat.select(Q, top_k=10, principal=PAYROLL)


def test_restricted_then_authorised_does_not_suppress(cat):
    """Stale-restriction direction: a restricted call first must not leave state that hides a table from the
    authorised caller after it. The baseline comes from a fresh catalog so the order cannot shape it."""
    _hidden_for_analyst(cat)
    _assert_restricted(cat.select(Q, top_k=10, principal=ANALYST))
    baseline = _names(cat.select(Q, top_k=10, principal=PAYROLL))
    for _ in range(3):
        _assert_restricted(cat.select(Q, top_k=10, principal=ANALYST))
        _assert_authorised(cat.select(Q, top_k=10, principal=PAYROLL), baseline)


def test_both_orders_give_each_caller_the_same_answer(cat, db_url):
    """Order independence: each caller's selection is identical whether it ran first or second."""
    from schemagate import Catalog
    from schema_fixture import HINTS

    def fresh():
        c = Catalog().bootstrap(db_url)
        for t, h in HINTS.items():
            c.hint(t, h)
        c = c.index()
        _hidden_for_analyst(c)
        return c

    a = fresh()
    a_first_auth = _names(a.select(Q, top_k=10, principal=PAYROLL))
    a_then_restr = _names(a.select(Q, top_k=10, principal=ANALYST))
    b = fresh()
    b_first_restr = _names(b.select(Q, top_k=10, principal=ANALYST))
    b_then_auth = _names(b.select(Q, top_k=10, principal=PAYROLL))
    assert a_first_auth == b_then_auth
    assert a_then_restr == b_first_restr
