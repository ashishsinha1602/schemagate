# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""The organisation's vocabulary, as concepts the catalog can use.

A concept is a business idea with the words people use for it, the objects or
columns that hold it, an optional rule that makes it precise, a definition, and
its place among other concepts::

    revenue    synonyms: sales, turnover
               maps:     billing_invoice.total_net
               filter:   billing_invoice.status = 'issued'
               broader:  money in

Three things use it.

* **Selection.** A question that uses a concept's name or a synonym brings in
  the objects it maps to (``Catalog.select``), the way typing a table's name
  does. Concepts one step away -- broader or narrower -- add a weaker signal and
  no guaranteed slot: "parties" should consider ``crm_customer``, not insist on it.
* **The prompt.** A matched concept with a column, a rule or a definition is
  written above the DDL, so the model writes ``WHERE status = 'issued'``
  instead of summing drafts. Only for objects and columns this caller may see.
* **Your tools.** ``Ontology.to_dict`` / ``from_dict`` round-trip through the
  ``ontology`` block of ``catalog.json``; ``schemagate.ontology_io`` imports
  dbt semantic models, Snowflake semantic views and CSV glossaries.

A concept never widens access. It is matched against the question, but every
object it names still has to pass the caller's visibility, and its meaning line
is left out if any table or column it would describe is withheld.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .embedder import tokenize


def _stem(t: str) -> str:
    # The catalog's own plural folding, imported lazily to avoid a cycle.
    from .catalog import _stem as stem
    return stem(t)


def phrase_key(text: str) -> Tuple[str, ...]:
    """How a phrase is matched: the index's tokenizer, plurals folded."""
    return tuple(_stem(t) for t in tokenize(text))


@dataclass
class Concept:
    """One business idea. ``objects`` and ``columns`` hold qualified names."""
    name: str
    synonyms: List[str] = field(default_factory=list)
    objects: List[str] = field(default_factory=list)            # qnames
    columns: List[Tuple[str, str]] = field(default_factory=list)  # (qname, column)
    filter: Optional[str] = None
    definition: Optional[str] = None
    broader: List[str] = field(default_factory=list)            # concept names
    source: str = "manual"                                      # manual | dbt | snowflake | csv | learned

    def phrases(self) -> List[str]:
        return [self.name] + [s for s in self.synonyms if s]

    def all_objects(self) -> List[str]:
        """Every object this concept points at, columns' tables included."""
        out = list(self.objects)
        for q, _ in self.columns:
            if q not in out:
                out.append(q)
        return out


class Ontology:
    """Concepts, the phrases that name them, and how they relate."""

    def __init__(self) -> None:
        self.concepts: Dict[str, Concept] = {}                  # key: lower-cased name
        self._phrases: Dict[Tuple[str, ...], str] = {}          # phrase key -> concept key

    def __len__(self) -> int:
        return len(self.concepts)

    def __bool__(self) -> bool:
        return bool(self.concepts)

    @staticmethod
    def key(name: str) -> str:
        return " ".join(tokenize(name))

    def get(self, name: str) -> Optional[Concept]:
        return self.concepts.get(self.key(name))

    def add(self, concept: Concept) -> Concept:
        """Add a concept, or merge it into the one with the same name.

        Merging keeps every synonym, object and column from both, and lets the
        newer filter, definition and source replace the older ones -- so a
        ``term()`` call after an import extends the imported concept instead of
        replacing it.
        """
        k = self.key(concept.name)
        if not k:
            raise ValueError(f"concept {concept.name!r} has no words")
        if not phrase_key(concept.name):
            raise ValueError(f"concept {concept.name!r} has no words")
        old = self.concepts.get(k)
        if old is not None:
            for s in concept.synonyms:
                if s not in old.synonyms:
                    old.synonyms.append(s)
            for q in concept.objects:
                if q not in old.objects:
                    old.objects.append(q)
            for c in concept.columns:
                if c not in old.columns:
                    old.columns.append(c)
            for b in concept.broader:
                if b not in old.broader:
                    old.broader.append(b)
            old.filter = concept.filter or old.filter
            old.definition = concept.definition or old.definition
            concept = old
        else:
            self.concepts[k] = concept
        for p in concept.phrases():
            pk = phrase_key(p)
            if pk:
                # First owner keeps a phrase: two concepts claiming one word is
                # reported by check(), not silently resolved by load order.
                self._phrases.setdefault(pk, k)
        return concept

    # ------------------------------------------------------------- matching

    def match(self, question: str) -> List[Tuple[Concept, str]]:
        """The concepts a question uses, most specific phrase only, in order.

        "take things offline" (a maintenance window) beats the single word
        "offline" inside it, the rule object names already follow.
        """
        if not self._phrases:
            return []
        stems = [_stem(t) for t in tokenize(question)]
        found = []
        for pk, ck in self._phrases.items():
            n = len(pk)
            for i in range(len(stems) - n + 1):
                if tuple(stems[i:i + n]) == pk:
                    found.append((i, n, ck, " ".join(pk)))
                    break
        kept = [f for f in found
                if not any(o is not f and o[1] > f[1] and o[0] <= f[0]
                           and f[0] + f[1] <= o[0] + o[1] for o in found)]
        out, seen = [], set()
        for _, _, ck, phrase in sorted(kept, key=lambda f: (f[0], -f[1])):
            if ck not in seen:
                seen.add(ck)
                out.append((self.concepts[ck], phrase))
        return out

    def neighbours(self, concept: Concept) -> List[Concept]:
        """Concepts one step away: its broader ones and the ones narrower than it."""
        out = []
        for b in concept.broader:
            c = self.get(b)
            if c is not None and c is not concept:
                out.append(c)
        k = self.key(concept.name)
        for c in self.concepts.values():
            if c is not concept and any(self.key(b) == k for b in c.broader) and c not in out:
                out.append(c)
        return out

    # -------------------------------------------------------------- checking

    def check(self) -> List[str]:
        """Problems a person should fix: a broader concept that does not exist,
        a phrase two concepts both claim, a hierarchy loop."""
        problems = []
        for c in self.concepts.values():
            for b in c.broader:
                if self.get(b) is None:
                    problems.append(f"{c.name!r}: broader concept {b!r} is not defined")
        owners: Dict[Tuple[str, ...], List[str]] = {}
        for c in self.concepts.values():
            for p in c.phrases():
                owners.setdefault(phrase_key(p), []).append(c.name)
        for pk, names in owners.items():
            if len(set(names)) > 1:
                problems.append(f"phrase {' '.join(pk)!r} is claimed by {sorted(set(names))}; "
                                f"only {names[0]!r} gets it")
        for c in self.concepts.values():
            seen, todo = set(), list(c.broader)
            while todo:
                b = self.key(todo.pop())
                if b == self.key(c.name):
                    problems.append(f"{c.name!r} is broader than itself")
                    break
                if b in seen or b not in self.concepts:
                    continue
                seen.add(b)
                todo.extend(self.concepts[b].broader)
        return problems

    # ------------------------------------------------------------ round trip

    def to_dict(self) -> Dict[str, Any]:
        """The ``ontology`` block of ``catalog.json``."""
        out: Dict[str, Any] = {}
        for c in self.concepts.values():
            e: Dict[str, Any] = {}
            if c.synonyms:
                e["synonyms"] = list(c.synonyms)
            maps = list(c.objects) + [f"{q}.{col}" for q, col in c.columns]
            if maps:
                e["maps"] = maps
            if c.filter:
                e["filter"] = c.filter
            if c.definition:
                e["definition"] = c.definition
            if c.broader:
                e["broader"] = list(c.broader)
            if c.source != "manual":
                e["source"] = c.source
            out[c.name] = e
        return {"concepts": out}


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_$#]*")


def identifiers(text: Optional[str]) -> set:
    """Lower-cased identifiers in a filter or definition, for the ACL check."""
    return {m.group(0).lower() for m in _IDENT.finditer(text or "")}


def concept_from_spec(name: str, spec: Any) -> Dict[str, Any]:
    """Normalise one ``catalog.json`` entry: a string or list is shorthand for ``maps``."""
    if isinstance(spec, str):
        return {"maps": [spec]}
    if isinstance(spec, list):
        return {"maps": list(spec)}
    if not isinstance(spec, Mapping):
        raise ValueError(f"ontology concept {name!r} must be an object, a name, or a list of names")
    allowed = {"synonyms", "maps", "filter", "definition", "broader", "source"}
    unknown = set(spec) - allowed
    if unknown:
        raise ValueError(f"ontology concept {name!r}: unknown field(s) {sorted(unknown)}; "
                         f"expected any of {sorted(allowed)}")
    out = dict(spec)
    for f in ("synonyms", "maps", "broader"):
        v = out.get(f)
        if v is None:
            out[f] = []
        elif isinstance(v, str):
            out[f] = [v]
        elif not isinstance(v, list):
            raise ValueError(f"ontology concept {name!r}: {f!r} must be a list")
    return out


def concepts_in(block: Any) -> Iterable[Tuple[str, Dict[str, Any]]]:
    """The concepts of an ``ontology`` block, ``{"concepts": {...}}`` or the bare map."""
    if not isinstance(block, Mapping):
        raise ValueError("the ontology block must be an object")
    body = block.get("concepts", block) if "concepts" in block else block
    if not isinstance(body, Mapping):
        raise ValueError("ontology 'concepts' must be an object mapping a name to its definition")
    for name, spec in body.items():
        yield str(name), concept_from_spec(str(name), spec)


def meaning_line(c: Concept) -> Optional[str]:
    """What a matched concept tells the model, or None if it only names objects."""
    parts = []
    if c.columns:
        parts.append(", ".join(f"{q}.{col}" for q, col in c.columns))
    if c.filter:
        parts.append(f"only where {c.filter}")
    head = c.name + (f" (also: {', '.join(c.synonyms[:4])})" if c.synonyms else "")
    text = "; ".join(parts)
    if c.definition:
        text = f"{text}. {c.definition}" if text else c.definition
    if not text:
        return None
    return f"-- {head}: {text}"


# ------------------------------------------------------------------ learning

#: Words that carry no meaning of their own in a question about data. A phrase
#: may contain them ("per member per month") but may not start or end with one.
STOP = frozenset("""
a an the of for to in on at by with from and or not no is are was were be been being do does did
how many much what which who whom whose where when why list show give find get tell me us our we
you your i my all each every any some there their them they it its this that these those than then
per as into over under about between more most less least top number count total average avg
""".split())


def learn(pairs: Iterable[Tuple[str, Iterable[str]]], *, min_support: int = 2,
          min_precision: float = 0.6, max_n: int = 3, max_per_object: int = 5,
          already_named=None) -> List[Dict[str, Any]]:
    """Concepts suggested by a question history: ``[(question, [qname, ...]), ...]``.

    A phrase is suggested for an object when it appears in at least
    ``min_support`` questions whose SQL read that object, and at least
    ``min_precision`` of all the questions using the phrase read it. That keeps
    the domain's words ("passenger" -> flights) and drops the ones every
    question shares ("how many"). ``already_named(phrase_key, qname)`` lets the
    caller skip phrases the object's own name already answers.

    Returns suggestions, strongest first, each ``{"phrase", "object",
    "support", "precision"}``. Nothing is added to any catalog here: a person,
    or ``Catalog.learn_concepts(apply=True)``, decides.
    """
    phrase_n: Dict[Tuple[str, ...], int] = {}
    pair_n: Dict[Tuple[Tuple[str, ...], str], int] = {}
    surface: Dict[Tuple[str, ...], str] = {}
    for question, objects in pairs:
        objs = {o for o in objects if o}
        if not objs:
            continue
        words = tokenize(question)
        stems = [_stem(w) for w in words]
        grams = set()
        for n in range(1, max_n + 1):
            for i in range(len(stems) - n + 1):
                g = tuple(stems[i:i + n])
                if g[0] in STOP or g[-1] in STOP or any(t.isdigit() for t in g):
                    continue
                if all(t in STOP for t in g) or (n == 1 and len(g[0]) < 3):
                    continue
                grams.add(g)
                surface.setdefault(g, " ".join(words[i:i + n]))
        for g in grams:
            phrase_n[g] = phrase_n.get(g, 0) + 1
            for o in objs:
                pair_n[(g, o)] = pair_n.get((g, o), 0) + 1
    by_obj: Dict[str, List[Dict[str, Any]]] = {}
    for (g, o), support in pair_n.items():
        if support < min_support:
            continue
        precision = support / phrase_n[g]
        if precision < min_precision:
            continue
        if already_named is not None and already_named(g, o):
            continue
        by_obj.setdefault(o, []).append({"phrase": surface[g], "object": o, "support": support,
                                          "precision": round(precision, 3), "_key": g})
    out = []
    for o, cands in by_obj.items():
        # shorter first, so a longer phrase is kept only when it says something its parts do not
        cands.sort(key=lambda c: (len(c["_key"]), -c["precision"], -c["support"], c["phrase"]))
        kept: List[Dict[str, Any]] = []
        for c in cands:
            # a longer phrase adds nothing over a kept shorter one unless it is more precise
            if any(set(k["_key"]) <= set(c["_key"]) and k["precision"] >= c["precision"] for k in kept):
                continue
            kept.append(c)
            if len(kept) >= max_per_object:
                break
        out.extend(kept)
    out.sort(key=lambda c: (-c["support"], -c["precision"], c["object"], c["phrase"]))
    for c in out:
        del c["_key"]
    return out
