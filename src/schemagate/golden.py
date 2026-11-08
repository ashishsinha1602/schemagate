# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""A golden question set for *your* schema, with no labels and no model.

`schemagate certify URL` proves schemagate on an engine with a fixture it
creates itself. This proves the catalog you actually have: for every table a
question written from the table's own words (its comment, or its name, plus
one or two of its most distinctive columns), for every foreign key a question
that needs both ends, and for every view one on the view. The answer to each
is known by construction, so the set needs nobody to label anything.

What the run reports is not a score to be proud of; it is the list of tables
that cannot be found *even from their own description*. A table that fails
its own question is unreachable by any question, and the fix is one line: a
comment in the database, or ``schemagate hint``. The set is saved as JSONL so
the questions can be edited into real ones and rerun; with ``--provider`` a
model rewrites each into the words a person would use, which is the harder
test and the one that matters.

Nothing here reads data. Questions are built from names and comments only.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence

from .embedder import tokenize
from .models import _sentence

#: Column names that say nothing about what a table is for.
_HOUSEKEEPING = frozenset({
    "id", "pk", "key", "uuid", "guid", "created", "created_at", "created_on", "created_by",
    "updated", "updated_at", "updated_on", "updated_by", "modified", "modified_at",
    "deleted", "deleted_at", "is_deleted", "version", "row_version", "ts", "timestamp",
    "status", "active", "is_active", "flag", "notes", "comment", "comments", "description",
})

_MAX_PHRASE_WORDS = 8


@dataclass
class Golden:
    """One question with its answer: every name in ``tables`` must be selected."""
    question: str
    tables: List[str]
    kind: str = "table"                      # table | join | view | user
    source: Optional[str] = None             # the words it was built from, for the report

    def to_dict(self) -> dict:
        return {"question": self.question, "tables": list(self.tables), "kind": self.kind}


@dataclass
class Result:
    item: Golden
    selected: List[str]
    found: bool
    missing: List[str] = field(default_factory=list)


@dataclass
class Report:
    results: List[Result]
    top_k: int
    skipped: List[str] = field(default_factory=list)

    @property
    def found(self) -> int:
        return sum(1 for r in self.results if r.found)

    def unreachable(self) -> List[str]:
        """Tables that missed their *own* question: nothing will find them."""
        out = []
        for r in self.results:
            if r.item.kind == "table" and not r.found:
                out.extend(t for t in r.missing if t not in out)
        return out

    def by_kind(self):
        c = Counter()
        f = Counter()
        for r in self.results:
            c[r.item.kind] += 1
            f[r.item.kind] += r.found
        return [(k, f[k], c[k]) for k in ("table", "join", "view", "user") if c[k]]

    def __str__(self) -> str:
        n = len(self.results)
        if not n:
            return "golden: no questions"
        lines = [f"golden: {self.found} of {n} questions answered within top {self.top_k} "
                 f"({100 * self.found / n:.0f}%)"]
        for kind, got, tot in self.by_kind():
            lines.append(f"  {kind:6s} {got}/{tot}")
        bad = self.unreachable()
        if bad:
            lines.append(f"  {len(bad)} table(s) not found by their own words -- no question will reach "
                         f"them; add a comment or a hint:")
            for t in bad:
                lines.append(f"    {t}")
        misses = [r for r in self.results if not r.found and r.item.kind != "table"]
        if misses:
            lines.append(f"  {len(misses)} join/view question(s) missed a table:")
            for r in misses[:20]:
                lines.append(f"    {r.item.question!r} -> missing {', '.join(r.missing)}")
            if len(misses) > 20:
                lines.append(f"    ... and {len(misses) - 20} more")
        for s in self.skipped:
            lines.append(f"  skipped: {s}")
        return "\n".join(lines)


# ---------------------------------------------------------------- words --

def _words(name: str) -> str:
    return " ".join(tokenize(name)) or name.lower()


def _clause(text: Optional[str]) -> Optional[str]:
    """The first clause of a comment, cut to a few words."""
    text = _sentence(text)
    if not text:
        return None
    first = re.split(r"[.;:\n(]", text, maxsplit=1)[0].strip()
    words = first.split()
    if not words:
        return None
    return " ".join(words[:_MAX_PHRASE_WORDS]).rstrip(",")


def _object_words(doc) -> str:
    return _clause(doc.hint) or _clause(doc.description) or _words(doc.name)


def _column_words(col) -> str:
    return _clause(col.comment) or _words(col.name)


def _distinctive_columns(doc, df: Counter, n: int = 2) -> list:
    """The columns that say most about this table and least about others:
    not keys, not housekeeping, rarest name tokens first, commented ones
    ahead of bare names at a tie."""
    fk_cols = {c.lower() for fk in doc.foreign_keys for c in fk.columns}
    scored = []
    for i, c in enumerate(doc.columns):
        low = c.name.lower()
        if c.pk or low in fk_cols or low in _HOUSEKEEPING or low.endswith(("_id", "_key", "_fk")):
            continue
        toks = [t for t in tokenize(c.name) if len(t) > 1]
        if not toks:
            continue
        rarity = sum(1.0 / df.get(t, 1) for t in toks) / len(toks)
        scored.append((-(rarity + (0.5 if c.comment else 0.0)), i, c))
    scored.sort()
    return [c for _, _, c in scored[:n]]


# ------------------------------------------------------------ synthesis --

def synthesize(cat, principal=None, joins_per_table: int = 2) -> List[Golden]:
    """One question per visible table, per foreign key and per view."""
    docs = [d for d in cat._docs.values() if cat._visible(d, principal)]
    by_name = {}
    for d in docs:
        by_name.setdefault(d.name.lower(), d)
        by_name[d.qname.lower()] = d
    df: Counter = Counter()
    for d in docs:
        for c in d.columns:
            df.update(set(t for t in tokenize(c.name) if len(t) > 1))
    out: List[Golden] = []
    for d in sorted(docs, key=lambda x: x.qname):
        head = _object_words(d)
        cols = _distinctive_columns(d, df)
        detail = ", ".join(_column_words(c) for c in cols)
        q = f"{head}: {detail}" if detail else head
        out.append(Golden(q, [d.qname], "view" if d.kind == "VIEW" else "table", source=d.qname))
        seen = set()
        for fk in d.foreign_keys:
            ref = by_name.get((fk.ref_table or "").lower()) or by_name.get((fk.ref_table or "").split(".")[-1].lower())
            if ref is None or ref is d or ref.qname in seen:
                continue
            seen.add(ref.qname)
            if len(seen) > joins_per_table:
                break
            out.append(Golden(f"{head} by {_object_words(ref)}", [d.qname, ref.qname], "join", source=d.qname))
    return out


# ------------------------------------------------------------ paraphrase --

_PARAPHRASE_SYSTEM = (
    "You rewrite schema-derived phrases into the question a business user would ask. "
    "Each rewrite must be answerable from exactly the tables named, must not use the "
    "table names or column names literally, and must stay one sentence. "
    "Reply with a JSON array of strings, one per input, in the same order, nothing else.")


def paraphrase(items: Sequence[Golden], provider, batch: int = 20) -> List[Golden]:
    """Rewrite each question in a user's words with ``provider.complete``.

    A batch the model answers badly (not JSON, wrong length) keeps its
    original questions; the run never fails because the model did.
    """
    out: List[Golden] = []
    for start in range(0, len(items), batch):
        chunk = list(items[start:start + batch])
        lines = [f"{i + 1}. tables {', '.join(g.tables)}: {g.question}" for i, g in enumerate(chunk)]
        try:
            reply = provider.complete(_PARAPHRASE_SYSTEM, "\n".join(lines), max_tokens=4096)
            m = re.search(r"\[.*\]", reply, re.S)
            rewritten = json.loads(m.group(0)) if m else []
        except Exception:                  # noqa: BLE001 -- keep the originals
            rewritten = []
        if len(rewritten) != len(chunk) or not all(isinstance(x, str) and x.strip() for x in rewritten):
            out.extend(chunk)
            continue
        for g, text in zip(chunk, rewritten):
            out.append(Golden(text.strip(), g.tables, g.kind, source=g.source))
    return out


# ------------------------------------------------------------------- run --

def run(cat, items: Iterable[Golden], top_k: int = 10, principal=None, **select_kw) -> Report:
    results = []
    for g in items:
        sel = cat.select(g.question, top_k=top_k, principal=principal, **select_kw)
        picked = {d.qname.lower() for d in sel.objects} | {d.name.lower() for d in sel.objects}
        missing = [t for t in g.tables if t.lower() not in picked and t.split(".")[-1].lower() not in picked]
        results.append(Result(g, sorted(d.qname for d in sel.objects), not missing, missing))
    return Report(results, top_k)


# -------------------------------------------------------------- files --

def save(items: Sequence[Golden], path: str) -> int:
    with open(path, "w", encoding="utf-8") as f:
        for g in items:
            f.write(json.dumps(g.to_dict(), ensure_ascii=False) + "\n")
    return len(items)


def load(path: str) -> List[Golden]:
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{n}: not JSON ({e.msg})") from e
            if not isinstance(rec, dict) or not isinstance(rec.get("question"), str) \
                    or not isinstance(rec.get("tables"), list) or not rec["tables"]:
                raise ValueError(f'{path}:{n}: each line needs {{"question": str, "tables": [name, ...]}}')
            out.append(Golden(rec["question"], [str(t) for t in rec["tables"]], str(rec.get("kind", "user"))))
    return out


def main(cat, questions_path: Optional[str] = None, save_path: Optional[str] = None,
         top_k: int = 10, provider=None, principal=None) -> int:
    """The `certify --golden` entry point. Returns 1 when a table is unreachable."""
    if questions_path:
        items = load(questions_path)
        print(f"golden: {len(items)} question(s) from {questions_path}")
    else:
        items = synthesize(cat, principal)
        print(f"golden: {len(items)} question(s) written from the schema's own words")
        if provider is not None:
            items = paraphrase(items, provider)
            print(f"golden: rewritten by {getattr(provider, 'name', type(provider).__name__)}")
    if save_path:
        print(f"golden: saved {save(items, save_path)} question(s) to {save_path}")
    report = run(cat, items, top_k=top_k, principal=principal)
    print(report)
    return 1 if report.unreachable() else 0
