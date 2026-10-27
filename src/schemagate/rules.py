# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Business rules: the knowledge a schema does not carry.

"Our fiscal year starts 1 July", "always leave out the test tenant",
"churned means no order in 90 days". None of these is a table, a column or a
term, so none of them can be found in the database, and a model that is not
told writes SQL that runs and answers the wrong question.

A rule is a short piece of text, written in a Markdown file a person keeps::

    ## Fiscal year
    Our fiscal year starts 1 July.

    ## Test accounts
    tables: contacts, deals
    Always exclude tenant_id 6, the internal test tenant.

    ## Bonus formula
    roles: payroll
    bonus = base_salary * rating_multiplier, paid in March.

Each ``##`` heading is one rule. ``tables:`` ties it to objects, and it is
then sent only when one of them is in the selection. ``roles:`` keeps it from
callers without one of those roles, the same way a restricted table is kept
from them. A rule with no tables is sent when the question shares a word with
it. At most a handful go into any one prompt.

With no rules, nothing changes: the prompt is byte-for-byte what it was.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

__all__ = ["Rule", "parse_markdown", "to_markdown", "relevant", "MAX_RULES"]

#: Rules sent with one question, at most.
MAX_RULES = 5

_HEADING = re.compile(r"^\s{0,3}#{2,3}\s+(.+?)\s*#*\s*$")
_FIELD = re.compile(r"^\s*(tables|roles)\s*:\s*(.*)$", re.I)

#: Words too common to make a rule relevant on their own.
_STOP = frozenset("""a an the and or of to in on for by with at from is are was be this that these those
what which who how many much all any each per our we us my me show list give get find number count total
there their it its as into than then when where why do does did not no yes""".split())


@dataclass
class Rule:
    title: str
    text: str
    tables: Tuple[str, ...] = ()
    roles: Tuple[str, ...] = ()
    _words: frozenset = field(default=frozenset(), repr=False, compare=False)

    def line(self) -> str:
        return f"- {self.title}: {self.text}" if self.title else f"- {self.text}"


def _split(v: str) -> Tuple[str, ...]:
    return tuple(x.strip() for x in v.split(",") if x.strip())


def _words(text: str) -> frozenset:
    from .ontology import _stem
    from .embedder import tokenize
    return frozenset(_stem(t) for t in tokenize(text) if t not in _STOP and len(t) > 2)


def parse_markdown(text: str) -> List[Rule]:
    """Rules from Markdown: one per ``##`` heading. Text before the first heading is ignored."""
    rules: List[Rule] = []
    title: Optional[str] = None
    body: List[str] = []
    tables: Tuple[str, ...] = ()
    roles: Tuple[str, ...] = ()

    def flush():
        if title is None:
            return
        t = " ".join(" ".join(body).split())
        if t:
            r = Rule(title, t, tables, roles)
            r._words = _words(title + " " + t)
            rules.append(r)

    for raw in (text or "").splitlines():
        m = _HEADING.match(raw)
        if m:
            flush()
            title, body, tables, roles = m.group(1).strip(), [], (), ()
            continue
        if title is None:
            continue
        f = _FIELD.match(raw)
        if f and not body:
            if f.group(1).lower() == "tables":
                tables = _split(f.group(2))
            else:
                roles = _split(f.group(2))
            continue
        body.append(raw.strip())
    flush()
    return rules


def to_markdown(rules: Iterable[Rule]) -> str:
    out = []
    for r in rules:
        out.append(f"## {r.title}")
        if r.tables:
            out.append("tables: " + ", ".join(r.tables))
        if r.roles:
            out.append("roles: " + ", ".join(r.roles))
        out.append(r.text)
        out.append("")
    return "\n".join(out)


def _bare(name: str) -> str:
    return name.rsplit(".", 1)[-1].strip('"').lower()


def relevant(rules: Sequence[Rule], question: str, selected: Iterable[str],
             roles: Iterable[str] = (), limit: int = MAX_RULES) -> List[Rule]:
    """The rules to send with this question, for this caller, best first.

    A rule with ``roles`` is skipped unless the caller holds one of them. A rule
    with ``tables`` is a candidate only when one of them was selected; one
    without is a candidate when it shares a word with the question.
    """
    if not rules:
        return []
    held = {r.lower() for r in roles or ()}
    chosen = {_bare(s) for s in selected or ()}
    q = _words(question)
    scored = []
    for i, r in enumerate(rules):
        if r.roles and not held & {x.lower() for x in r.roles}:
            continue
        overlap = len(q & r._words)
        if r.tables:
            if not chosen & {_bare(t) for t in r.tables}:
                continue
            score = 1 + overlap
        elif overlap:
            score = overlap
        else:
            continue
        scored.append((-score, i, r))
    scored.sort()
    return [r for _, _, r in scored[:max(0, limit)]]
