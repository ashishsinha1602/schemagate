# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Learn from SQL that ran: the tool gets better the more it is used.

A question that was answered correctly once is the best evidence there is
about how to answer it the next time -- better than a description, better
than a hint, because it is not a guess about the schema, it is a query that
executed against it. Every text-to-SQL tool people actually adopt has this
loop; schemagate did not, and a tool that answers the same question the same
way after a thousand uses as after one is a tool nobody trains.

What is remembered is a pair: the question as asked, and the SELECT that
answered it, plus the tables that SELECT read. What is done with it, given
a new question, is two things:

**Pin the tables.** The tables the most similar remembered questions used
are handed to `Catalog.select(pin=...)`. Pinning never bypasses identity:
`select` admits a pin only if the object is in this caller's `allowed_set`,
so a remembered table the caller may not see is silently not pinned. That
is the same code path a hand-written pin takes; nothing here is a second
door.

**Show the SQL.** The pairs go into the SQL-writing prompt as worked
examples, between the DDL and the question. An example is shown only if
every table it names is visible to the caller -- a remembered query against
`hr_compensation` is not shown to a caller who cannot see `hr_compensation`,
because the SQL would name it, and the name is the disclosure.

Three rules, the same three the audit log lives by.

**Only SQL that passed the read-only check is stored**, at write time and
again at read time, so a stored entry that somebody edited into a write is
refused before it reaches a prompt.

**Never rows.** A remembered entry is a question and a query. The answer
the query produced is not kept; a memory that keeps answers is a second
database with weaker access control than the first.

**Nothing on disk unless asked.** `SCHEMAGATE_MEMORY=<path>` (or `=1` for
`~/.schemagate/memory/<catalog>.jsonl`) turns the file on. Without it the
memory lives for the process, which is enough for a Studio session and
nothing for a server that restarts -- which is the honest trade, stated
rather than made on the operator's behalf.

Similarity is the catalog's own embedder -- hashed n-grams by default, so
it is deterministic, offline and needs no key. It is a weak notion of
"similar": it matches wording, not meaning. That is acceptable here because
the examples are advisory and the pins are gated; a bad match costs a
wasted slot, not a wrong answer.

The audit log is the natural source. `learn_from_audit` ingests its
successful `run_query` and `answer` records, so an operator who has been
running with `SCHEMAGATE_AUDIT_LOG` on already has a training set.
"""
from __future__ import annotations

import collections
import datetime as _dt
import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import (Any, Deque, Dict, Iterable, List, Mapping, Optional,
                    Sequence, Set, Tuple)

__all__ = ["Memory", "Entry", "ENV_PATH", "format_examples",
           "learn_from_audit", "default_path"]

ENV_PATH = "SCHEMAGATE_MEMORY"
#: Entries kept in memory. Older ones fall off; the file keeps everything.
RING = 2000
#: How many remembered questions to consult for one new question.
DEFAULT_K = 3
#: Below this cosine similarity a remembered question is not "similar"; it
#: is just the nearest of many unrelated ones, and pinning its tables would
#: spend a slot on noise. Measured on the hashed embedder: unrelated
#: questions in the commerce fixture sit around 0.05-0.20; paraphrases of
#: the same question sit above 0.5.
MIN_SIMILARITY = 0.35

Entry = Dict[str, Any]

_TABLE_REF = re.compile(r"\b(?:from|join)\s+([`\"\[]?[\w.]+[`\"\]]?)", re.I)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")


def _bare(name: str) -> str:
    return name.strip('`"[]').split(".")[-1].lower()


def referenced_tables(sql: str) -> List[str]:
    """Base tables a SELECT reads, lower-cased, CTE names removed."""
    body = re.sub(r"--[^\n]*", " ", sql)
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    body = re.sub(r"'(?:[^']|'')*'", "''", body)
    ctes = {m.lower() for m in re.findall(r"(?:\bwith\b|,)\s*([A-Za-z_]\w*)\s+as\s*\(", body, re.I)}
    out: List[str] = []
    for raw in _TABLE_REF.findall(body):
        t = _bare(raw)
        if t and t not in ctes and t not in out:
            out.append(t)
    return out


def default_path(catalog_name: str) -> Path:
    from . import remember
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", catalog_name or "default")[:60]
    return remember.path().parent / "memory" / f"{safe}.jsonl"


def format_examples(pairs: Sequence[Tuple[str, str]]) -> str:
    """The block that goes between the DDL and the question. Empty input,
    empty string -- so a prompt with no memory is byte-identical to the
    prompt before memory existed."""
    if not pairs:
        return ""
    lines = ["Queries that answered similar questions against these tables:", ""]
    for q, sql in pairs:
        lines.append(f"Question: {q}")
        lines.append(f"SQL: {sql}")
        lines.append("")
    return "\n".join(lines)


class Memory:
    """Question -> SQL pairs, with the catalog's own embedder for similarity."""

    def __init__(self, embedder, *, path: Optional[os.PathLike] = None,
                 ring: int = RING, k: int = DEFAULT_K,
                 min_similarity: float = MIN_SIMILARITY) -> None:
        self.embedder = embedder
        self.path: Optional[Path] = Path(path) if path else None
        self.k, self.min_similarity = int(k), float(min_similarity)
        self._entries: Deque[Entry] = collections.deque(maxlen=ring)
        self._vectors: Dict[str, List[float]] = {}
        self._lock = threading.Lock()
        self.stats: Dict[str, int] = {"remembered": 0, "rejected": 0,
                                      "consulted": 0, "write_failures": 0}
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    @classmethod
    def from_env(cls, embedder, catalog_name: str = "default",
                 env: Optional[Mapping[str, str]] = None) -> "Memory":
        src = os.environ if env is None else env
        raw = (src.get(ENV_PATH) or "").strip()
        if not raw or raw == "0":
            return cls(embedder)
        if raw.lower() in ("1", "default", "on", "true"):
            return cls(embedder, path=default_path(catalog_name))
        return cls(embedder, path=raw)

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def __len__(self) -> int:
        return len(self._entries)

    # -- writing ---------------------------------------------------------------

    @staticmethod
    def _key(question: str) -> str:
        return hashlib.sha256(question.strip().lower().encode("utf-8")).hexdigest()[:16]

    def remember(self, question: str, sql: str, *,
                 tables: Optional[Iterable[str]] = None,
                 source: str = "api") -> Optional[Entry]:
        """Store one pair. Returns the entry, or None if the SQL was refused.

        The read-only check runs here, on the way in, so a write statement
        never becomes an example. The same check runs again on the way out.
        """
        from .answer import UnsafeSQL, check_read_only
        question = str(question or "").strip()
        if not question:
            return None
        try:
            sql = check_read_only(str(sql or ""))
        except UnsafeSQL:
            self.stats["rejected"] += 1
            return None
        tabs = sorted({_bare(t) for t in (tables or referenced_tables(sql)) if t})
        entry: Entry = {"ts": _now(), "question": question[:500], "sql": sql[:4000],
                        "tables": tabs, "source": source}
        key = self._key(question)
        with self._lock:
            # the same question asked again replaces its earlier answer
            self._entries = collections.deque(
                (e for e in self._entries if self._key(e["question"]) != key),
                maxlen=self._entries.maxlen)
            self._entries.append(entry)
            self._vectors[key] = self.embedder.embed([question])[0]
            self.stats["remembered"] += 1
            if self.path is not None:
                try:
                    with self.path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
                except OSError:
                    self.stats["write_failures"] += 1
        return entry

    def forget(self, question: Optional[str] = None) -> int:
        """Drop one question's entry, or everything. Returns how many went.
        The file is rewritten, because a memory that cannot forget is a
        liability the moment a remembered query turns out to be wrong."""
        with self._lock:
            before = len(self._entries)
            if question is None:
                self._entries.clear(); self._vectors.clear()
            else:
                key = self._key(question)
                self._entries = collections.deque(
                    (e for e in self._entries if self._key(e["question"]) != key),
                    maxlen=self._entries.maxlen)
                self._vectors.pop(key, None)
            gone = before - len(self._entries)
            if self.path is not None and gone:
                try:
                    with self.path.open("w", encoding="utf-8") as fh:
                        for e in self._entries:
                            fh.write(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n")
                except OSError:
                    self.stats["write_failures"] += 1
        return gone

    def _load(self) -> None:
        assert self.path is not None
        if not self.path.exists():
            return
        from .answer import UnsafeSQL, check_read_only
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    check_read_only(e["sql"])            # a tampered file is refused
                except (ValueError, KeyError, UnsafeSQL):
                    self.stats["rejected"] += 1
                    continue
                key = self._key(e["question"])
                self._entries = collections.deque(
                    (x for x in self._entries if self._key(x["question"]) != key),
                    maxlen=self._entries.maxlen)
                self._entries.append(e)
        questions = [e["question"] for e in self._entries]
        if questions:
            for e, v in zip(self._entries, self.embedder.embed(questions)):
                self._vectors[self._key(e["question"])] = v

    # -- reading -------------------------------------------------------------

    def similar(self, question: str, k: Optional[int] = None) -> List[Tuple[float, Entry]]:
        """The ``k`` most similar remembered questions above the threshold,
        best first, as ``(similarity, entry)``."""
        from .embedder import cosine_distance
        question = str(question or "").strip()
        if not question or not self._entries:
            return []
        qv = self.embedder.embed([question])[0]
        with self._lock:
            scored = []
            for e in self._entries:
                v = self._vectors.get(self._key(e["question"]))
                if v is None:
                    continue
                sim = 1.0 - cosine_distance(qv, v)
                if sim >= self.min_similarity:
                    scored.append((sim, e))
            self.stats["consulted"] += 1
        scored.sort(key=lambda p: (-p[0], p[1]["question"]))
        return scored[: (k or self.k)]

    def pins_for(self, question: str, k: Optional[int] = None) -> List[str]:
        """Tables the similar remembered queries read. Hand to
        ``Catalog.select(pin=...)``, which enforces visibility itself."""
        out: List[str] = []
        for _, e in self.similar(question, k):
            for t in e.get("tables", []):
                if t not in out:
                    out.append(t)
        return out

    def examples_for(self, question: str, *, visible: Iterable[str],
                     k: Optional[int] = None) -> List[Tuple[str, str]]:
        """``(question, sql)`` pairs safe to show this caller: every table the
        SQL names must be in ``visible`` (bare or qualified names accepted),
        and the SQL is re-checked read-only on the way out."""
        from .answer import UnsafeSQL, check_read_only
        vis: Set[str] = set()
        for name in visible:
            n = str(name).lower()
            vis.add(n)
            vis.add(n.split(".")[-1])
        pairs: List[Tuple[str, str]] = []
        for _, e in self.similar(question, k):
            tabs = e.get("tables") or referenced_tables(e["sql"])
            if not tabs or any(t not in vis for t in tabs):
                continue
            try:
                pairs.append((e["question"], check_read_only(e["sql"])))
            except UnsafeSQL:
                continue
        return pairs

    def describe(self) -> Dict[str, Any]:
        """For `health`: counts and whether a file is on. No questions."""
        return {"file": str(self.path) if self.path else None,
                "entries": len(self._entries), **self.stats}


def learn_from_audit(memory: Memory, records: Iterable[Mapping[str, Any]]) -> int:
    """Feed a memory from audit records: every successful `run_query` or
    `answer` that carries a question and SQL becomes an example. Returns
    how many were remembered. `run_query` records only carry a question when
    the client passed one, which the MCP server does when `answer` drove it."""
    n = 0
    for rec in records:
        if not rec.get("ok") or rec.get("tool") not in ("run_query", "answer"):
            continue
        q, sql = rec.get("question"), rec.get("sql")
        if not q or not sql:
            continue
        if memory.remember(q, sql, tables=rec.get("tables"), source="audit") is not None:
            n += 1
    return n
