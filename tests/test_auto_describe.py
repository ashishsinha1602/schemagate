"""The catalogue arrives without being asked for -- and only when it can.

Three things have to be true for "always" to be safe rather than surprising:
nothing is called when there is no key, nothing a person or the database
already wrote is overwritten, and a second run against the same schema costs
nothing. Each is pinned here with a provider that counts its own calls, so
"no call was made" is asserted rather than assumed.
"""
from __future__ import annotations

import json

import pytest

from schemagate import Catalog
from schemagate.ai import auto
from schemagate.models import Column, ObjectDoc


class StubProvider:
    """Replies in the exact shape the describer wants, and counts."""
    name = "stub:test"

    def __init__(self):
        self.calls = 0

    def complete(self, system, prompt, **kw):
        self.calls += 1
        return ("One row per thing this object keeps, for the test. | "
                "things, stuff, items, records, rows, entries, bits, "
                "pieces, units, objects, data, facts")


def _catalog():
    docs = [
        ObjectDoc(name="bare_table", kind="TABLE",
                  columns=[Column(name="id", type="INTEGER")]),
        ObjectDoc(name="commented_table", kind="TABLE",
                  description="A comment the database already had.",
                  columns=[Column(name="id", type="INTEGER")]),
        ObjectDoc(name="hinted_table", kind="TABLE",
                  columns=[Column(name="id", type="INTEGER")]),
    ]
    cat = Catalog(name="auto")
    cat.add_all(docs)
    cat.hint("hinted_table", "A hint a person wrote.")
    cat.index()
    return cat


# ------------------------------------------------------------ the gates

def test_the_kill_switch_makes_no_call():
    cat, p = _catalog(), StubProvider()
    n = auto.ensure_described(cat, provider=p, env={auto.KILL_SWITCH: "0"})
    assert n == 0 and p.calls == 0


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "FALSE", " 0 "])
def test_every_spelling_of_off_is_off(value):
    assert auto.enabled({auto.KILL_SWITCH: value}) is False


def test_unset_means_on():
    assert auto.enabled({}) is True


def test_no_key_means_no_provider_and_no_call():
    """Precondition first: this environment really has no key in it."""
    env = {}
    assert auto.provider_from_env(env) is None
    cat = _catalog()
    assert auto.ensure_described(cat, env=env) == 0
    assert cat._docs["bare_table"].description is None


# ------------------------------------------------ what gets described

def test_only_the_undescribed_object_is_sent(tmp_path):
    cat, p = _catalog(), StubProvider()
    n = auto.ensure_described(cat, cache_path=str(tmp_path / "c.json"),
                              provider=p, env={})
    assert n == 1, "exactly one object had neither a comment nor a hint"
    assert p.calls == 1
    assert cat._docs["bare_table"].description
    # the database's comment and the person's hint are untouched
    assert cat._docs["commented_table"].description == "A comment the database already had."
    assert cat._docs["hinted_table"].hint == "A hint a person wrote."
    assert cat._docs["hinted_table"].description is None


def test_the_second_run_costs_nothing(tmp_path):
    """The cache is the whole reason 'always' is affordable."""
    cache = str(tmp_path / "c.json")
    first = StubProvider()
    auto.ensure_described(_catalog(), cache_path=cache, provider=first, env={})
    assert first.calls == 1
    assert json.loads((tmp_path / "c.json").read_text("utf-8")), "cache not written"

    second = StubProvider()
    n = auto.ensure_described(_catalog(), cache_path=cache, provider=second, env={})
    assert n == 1, "the cached description is still applied"
    assert second.calls == 0, "a cache hit must not call the model"


def test_a_failing_provider_is_a_notice_not_a_crash(tmp_path, capsys):
    class Broken:
        name = "broken"
        def complete(self, *a, **k):
            raise RuntimeError("401 invalid key")

    cat = _catalog()
    n = auto.ensure_described(cat, cache_path=str(tmp_path / "c.json"),
                              provider=Broken(), env={})
    assert n == 0
    assert cat.select("bare table", top_k=1).objects, "selection still works"


# ----------------------------------------------------------- the cache key

def test_the_cache_path_never_carries_a_password():
    from sqlalchemy.engine import make_url
    label = make_url("postgresql://u:hunter2@db.example/app").render_as_string(
        hide_password=True)
    assert "hunter2" not in label
    path = auto.default_cache_path(label)
    assert "hunter2" not in path
    assert path.endswith(".json")


def test_the_same_connection_always_maps_to_the_same_file():
    assert auto.default_cache_path("x") == auto.default_cache_path("x")
    assert auto.default_cache_path("x") != auto.default_cache_path("y")


# ------------------------------------------------------ model selection

def test_a_named_model_wins_over_the_default():
    env = {"ANTHROPIC_API_KEY": "k", auto.MODEL_VARS[0]: "claude-test-model"}
    p = auto.provider_from_env(env)
    assert p is not None and "claude-test-model" in p.name


def test_a_key_with_no_model_gets_that_providers_default():
    env = {"ANTHROPIC_API_KEY": "k"}
    p = auto.provider_from_env(env)
    assert p is not None
    assert auto.DEFAULT_MODELS["AnthropicProvider"] in p.name


def test_oci_without_a_model_is_not_guessed():
    """A wrong OCI model id is a confident error, not a description."""
    assert auto.provider_from_env({"OCI_COMPARTMENT_ID": "ocid1..."}) is None


# --------------------------------------------------- boilerplate comments

#: The real template from the 1,200-object fixture, own name included. That
#: inclusion is the point: the first version of the rule counted the name's
#: words, and every one-voice comment carried one rare word -- its own -- so
#: 2 of 1,036 read as boilerplate. A comment that restates the name and says
#: nothing else is exactly what should be replaced.
ONE_VOICE = ("Operational record in the customer contact platform. Holds {what} "
             "used by contact management, contact reporting and downstream "
             "contact analytics, maintained by the CRM data team.")


def _saturated(n=60, distinct_at=0):
    """Every object commented in one voice, except one with a real comment.
    Big enough that a one-voice word reaches nearly every document."""
    docs = []
    for i in range(n):
        text = ONE_VOICE.format(what=f"crm thing {i:03d}")
        if i == distinct_at:
            text = "One row per invoice line, with quantity and line amount."
        docs.append(ObjectDoc(name=f"crm_thing_{i:03d}", kind="TABLE",
                              description=text,
                              columns=[Column(name="id", type="INTEGER")]))
    cat = Catalog(name="boiler")
    cat.add_all(docs)
    cat.hint("crm_thing_001", "A hint a person wrote, in the same voice: "
             "contact platform record.")
    cat.index()
    return cat


def test_the_fixture_really_is_saturated():
    """Precondition: the one-voice words sit below the threshold and the
    distinctive comment's words sit above it. Otherwise nothing below means
    anything."""
    cat = _saturated()
    assert auto.is_boilerplate(cat, cat._docs["crm_thing_005"]) is True
    assert auto.is_boilerplate(cat, cat._docs["crm_thing_000"]) is False


def test_a_hint_is_never_boilerplate():
    cat = _saturated()
    assert cat._docs["crm_thing_001"].hint
    assert auto.is_boilerplate(cat, cat._docs["crm_thing_001"]) is False


def test_an_absent_description_is_missing_not_boilerplate():
    cat = _saturated()
    cat._docs["crm_thing_002"].description = None
    assert auto.is_boilerplate(cat, cat._docs["crm_thing_002"]) is False


def test_boilerplate_is_replaced_and_the_real_comment_is_kept(tmp_path):
    cat, p = _saturated(), StubProvider()
    n = auto.ensure_described(cat, cache_path=str(tmp_path / "c.json"),
                              provider=p, env={})
    # 60 objects: one distinctive (kept), one hinted (kept), 58 boilerplate
    assert n == 58, n
    assert p.calls == 58
    assert cat._docs["crm_thing_000"].description.startswith("One row per invoice line")
    assert cat._docs["crm_thing_001"].hint.startswith("A hint a person wrote")
    assert cat._docs["crm_thing_005"].description.startswith("One row per thing")


def test_replacement_can_be_turned_off(tmp_path):
    cat, p = _saturated(), StubProvider()
    n = auto.ensure_described(cat, cache_path=str(tmp_path / "c.json"),
                              provider=p, env={}, replace_boilerplate=False)
    assert n == 0 and p.calls == 0
    assert cat._docs["crm_thing_005"].description == ONE_VOICE.format(what="crm thing 005")


def test_a_failed_call_puts_the_boilerplate_back(tmp_path):
    """Worse than a boilerplate comment is no comment: the prompt would lose
    text it had. Whatever was cleared and not replaced is restored."""
    class Broken:
        name = "broken"
        def complete(self, *a, **k):
            raise RuntimeError("503")

    cat = _saturated()
    n = auto.ensure_described(cat, cache_path=str(tmp_path / "c.json"),
                              provider=Broken(), env={})
    assert n == 0
    assert cat._docs["crm_thing_005"].description == ONE_VOICE.format(what="crm thing 005")
    assert all(d.description or d.hint for d in cat._docs.values())
