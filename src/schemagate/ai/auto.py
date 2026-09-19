# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""The catalogue, without being asked for it.

Descriptions are the single largest accuracy lever in the library -- 55.8% to
94.2% on 52 business-language questions, and on a 1,200-object schema the
difference between six and eight of eight complex questions producing SQL
that runs. They were also the step everyone skipped, because getting them
meant knowing that ``schemagate describe`` exists, running it, and carrying
its output around in a ``--config`` file. A feature that only helps people who
already know about it is not doing its job.

So every path that answers a question now describes the catalogue first,
whenever it can: the CLI, the MCP server and the Studio all call
:func:`ensure_described` after reflection. "Whenever it can" is precise:

* An API key has to be present. With none, nothing is called and nothing
  changes -- the offline path is exactly what it was.
* Only objects with no description and no hint are sent. A comment the
  database already carries, or a hint a person wrote, is never overwritten.
* Results are cached to a file keyed on the connection, and the describer
  caches by content fingerprint inside that file, so a second run against the
  same schema costs nothing and a changed table is re-described alone.
* ``SCHEMAGATE_AUTO_DESCRIBE=0`` turns it off. Some schemas are large, some
  keys are metered, and some people want to see the prompt before anyone
  sends it.

Only schema metadata leaves the machine -- names, types, comments, foreign
keys -- the same promise ``describe_prompt`` has always made.
"""
from __future__ import annotations

import hashlib
import os
import sys
from typing import Any, Mapping, Optional

KILL_SWITCH = "SCHEMAGATE_AUTO_DESCRIBE"

#: Which model to describe with, in order of preference. The first is specific
#: to this feature; the second is the one the MCP server already reads, so a
#: deployment that configured a model once gets the same one here.
MODEL_VARS = ("SCHEMAGATE_DESCRIBE_MODEL", "SCHEMAGATE_MCP_MODEL")

#: A default per provider, for the case where a key is present and no model
#: was named. Deliberately the cheap, fast tier of each: a description is one
#: sentence and a dozen words, and a 1,200-object schema is 1,200 calls.
#: OCI is absent on purpose -- its model ids vary by region and tenancy, and
#: guessing one produces a confident error rather than a description.
DEFAULT_MODELS = {
    "AnthropicProvider": "claude-sonnet-4-5",
    "OpenAIProvider": "gpt-4o-mini",
    "GeminiProvider": "gemini-2.0-flash",
}


def enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    src = os.environ if env is None else env
    return str(src.get(KILL_SWITCH, "1")).strip().lower() not in (
        "0", "false", "no", "off")


def default_cache_path(label: str) -> str:
    """One file per connection, next to the Studio's, never holding a
    password: callers pass a label with the password already hidden."""
    from .. import remember
    key = hashlib.sha256(label.encode("utf-8")).hexdigest()[:16]
    return str(remember.path().parent / "descriptions" / f"{key}.json")


def provider_from_env(env: Optional[Mapping[str, str]] = None):
    """A provider built from whatever key is present, or None. Never raises:
    the caller is in the middle of connecting, and a missing key is the
    normal case, not an error."""
    from .providers import auto_provider, available_providers
    src = os.environ if env is None else env
    names = available_providers(src)
    if not names:
        return None
    model = next((src[v] for v in MODEL_VARS if src.get(v)), None)
    if not model:
        model = DEFAULT_MODELS.get(names[0])
    if not model:
        return None
    try:
        return auto_provider(model, env=src)
    except Exception:                                            # noqa: BLE001
        return None


#: A description whose best word is less informative than this, in the prose
#: index, is boilerplate: it says something every object in the schema also
#: says. Measured on the 1,200-object fixture, where every comment was written
#: in one voice -- "operational record in the customer contact platform" --
#: the most informative word in any of them scored 0.148, and with those
#: comments in place the auto catalogue described nothing (a comment is a
#: comment) and complex SQL stayed at 6 of 8. Replacing them took it to 8 of 8.
#: A real comment -- "one row per invoice line, with quantity and amount" --
#: carries at least one word the rest of the schema does not, and clears this
#: by a wide margin. Set on the same scale as ABSTAIN_MIN_IDF, and well above
#: it: abstaining is about a field having nothing to say for one question,
#: this is about a description having nothing to say for any.
BOILERPLATE_MAX_IDF = 0.5


def is_boilerplate(cat, doc) -> bool:
    """True when the object's description carries no word that distinguishes
    it from the rest of the catalogue. A human hint is never boilerplate --
    someone chose to write it -- and an absent description is not either; it
    is simply missing, and handled by ``only_missing``."""
    if doc.hint or not doc.description:
        return False
    index = getattr(cat, "_bm25_prose", None)
    if index is None or not index.idf:
        return False
    from ..catalog import _stem
    from ..embedder import tokenize
    # The object's own name and columns do not count. A generated comment
    # nearly always restates them -- "holds crm contact note records" -- and
    # a name is already indexed; repeating it in the prose adds nothing. The
    # question is whether the comment says anything the identifiers do not.
    # Measured: with the name counted, 2 of 1,036 one-voice comments read as
    # boilerplate, because each carried one rare word -- its own.
    #
    # Tokenised the same way the description is, so the two sets actually
    # meet. `_identifier_words` keeps only alphabetic runs, and the first
    # version used it: the digits in `crm_thing_005` were not "own", so `005`
    # -- a token that appears once in the whole corpus -- scored 3.7 and
    # cleared the bar for every object that had one. A run of digits is never
    # prose, so it is skipped outright as well.
    own = set()
    for text in [doc.qname, doc.name] + [c.name for c in doc.columns]:
        own.update(_stem(t) for t in tokenize(str(text or "")))
    best = 0.0
    for token in tokenize(doc.description):
        stem = _stem(token)
        if len(token) > 2 and not token.isdigit() and stem not in own:
            best = max(best, index.idf.get(stem, 0.0))
    return best < BOILERPLATE_MAX_IDF


def ensure_described(cat, cache_path: Optional[str] = None, *,
                     provider: Any = None, label: Optional[str] = None,
                     env: Optional[Mapping[str, str]] = None,
                     replace_boilerplate: bool = True,
                     out=None) -> int:
    """Describe whatever in ``cat`` has no description yet, if a model is
    available. Returns how many descriptions were written; 0 means either
    nothing needed one, or nothing could be called, and both are fine.

    ``provider`` lets a caller that already has one (the Studio, from its
    settings) hand it over; otherwise one is built from the environment.
    ``label`` derives a cache file when ``cache_path`` is not given.
    """
    if not enabled(env):
        return 0
    if provider is None:
        provider = provider_from_env(env)
        if provider is None:
            return 0
    if cache_path is None and label:
        cache_path = default_cache_path(label)

    from .describe import SchemaDescriber
    stream = out or sys.stderr
    cleared = {}
    if replace_boilerplate:
        # Only a built index can say what is boilerplate, and a catalogue
        # fresh from bootstrap has none yet.
        if getattr(cat, "_bm25_prose", None) is None:
            cat.index()
        for doc in list(cat._docs.values()):
            if is_boilerplate(cat, doc):
                # Cleared rather than kept alongside: a boilerplate comment
                # left in the prose index would go on diluting every term it
                # contains, which is the very thing being fixed. Kept in hand
                # so it can be put back if nothing better arrives.
                cleared[doc.qname] = doc.description
                doc.description = None
        if cleared:
            print(f"schemagate: {len(cleared)} description(s) are boilerplate "
                  f"-- no word in them distinguishes the object -- and will "
                  f"be replaced", file=stream)

    def _restore_unreplaced():
        # A comment that was boilerplate is still better than nothing in the
        # prompt, and much better than a catalogue that lost text to a failed
        # call. Whatever did not get a replacement gets its original back.
        for qname, text in cleared.items():
            doc = cat._docs.get(qname)
            if doc is not None and not doc.description:
                doc.description = text

    try:
        describer = SchemaDescriber(provider, cache_path=cache_path)
        written = cat.describe(describer, only_missing=True)
    except Exception as e:                                       # noqa: BLE001
        # A bad key, a network that is down, a model id that no longer
        # exists: none of these should stop a selection that works without
        # descriptions. Say what happened, once, and carry on.
        _restore_unreplaced()
        if cleared:
            cat.index()
        print(f"schemagate: auto-describe skipped ({type(e).__name__}: "
              f"{str(e)[:120]})", file=stream)
        return 0
    _restore_unreplaced()
    if written:
        cat.index()
        where = f" -> {cache_path}" if cache_path else ""
        print(f"schemagate: described {written} object(s) with "
              f"{getattr(provider, 'name', type(provider).__name__)}{where}",
              file=stream)
    return written
