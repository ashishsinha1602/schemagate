# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""The record of every decision the server made about who saw what.

schemagate's claim is that a caller never sees a table they may not read.
A claim like that is only worth anything if it can be checked after the
fact -- by the operator, by whoever reviews the deployment, by the person
whose data it was -- and "checked after the fact" needs a record that was
written *at* the fact. The catalog changes, roles change, the question is
gone; `Selection.to_dict` exists because none of that can be reconstructed
later. This is where those records go.

One line of JSON per tool call, appended, never rewritten. What each line
holds is what an auditor asks for: when, which tool, which principal with
which roles, what they asked, what they were shown, what was held back, what
SQL ran and how many rows came back, and whether the call was refused and
why. What each line never holds is decided by three rules.

**No row data.** `run_query` returns rows to the caller; the log records the
count. A log that copies results is a second database with weaker access
control than the first.

**No names of what was withheld.** A selection records how many columns were
kept back from each object, never which. A log that lists the columns it
withheld has disclosed them to everyone who can read the log -- which, being
a file, is a wider set than the principal it withheld them from.

**No secrets.** The database URL is never written here; the SQL is the
caller's own text and contains none. If a caller puts a secret in a
question, the question is recorded as they sent it, because rewriting the
record is worse than the disclosure.

Nothing is written to disk unless asked. `SCHEMAGATE_AUDIT_LOG=<path>` (or
`=1` for the default under `~/.schemagate/`) turns the file on; without it
the last few hundred records are kept in memory so `health` can still say
what the server has been doing. That matches `remember.py`: a tool whose
pitch is that it stores nothing does not start writing files on its own.

The log is read by operators, from the file. It is deliberately **not** a
tool: exposing "recent decisions" to any MCP client would hand every caller
the questions every other caller asked.
"""
from __future__ import annotations

import collections
import datetime as _dt
import json
import os
import threading
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Mapping, Optional

__all__ = ["AuditLog", "ENV_PATH", "summarize", "Record"]

ENV_PATH = "SCHEMAGATE_AUDIT_LOG"
#: Rotate at this size: rename to `.1` and start over. One file, one
#: predecessor. An audit log that grows without bound is one that gets
#: deleted in a hurry, which is the worst outcome for an audit log.
DEFAULT_MAX_BYTES = 50 * 1024 * 1024
#: Kept in memory whether or not a file is configured, for `health`.
RING = 500
#: Tools whose calls are identity decisions. `health` and `refresh_catalog`
#: are about the server, not a caller, and are not recorded.
AUDITED = ("select_schema", "list_objects", "describe_object", "run_query", "answer")

Record = Dict[str, Any]


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")


def default_path() -> Path:
    from . import remember
    return remember.path().parent / "audit.jsonl"


def summarize(tool: str, args: Mapping[str, Any], result: Mapping[str, Any]) -> Record:
    """The auditable part of one call: what was asked, what came back.

    Written per tool rather than by copying the result, so that adding a
    field to a tool's output never quietly adds it to the log. Row data is
    the reason: `run_query` returns rows; this returns their count.
    """
    who = args.get("principal")
    roles = args.get("roles") or []
    rec: Record = {
        "ts": _now(),
        "tool": tool,
        "principal": str(who) if who else None,
        "roles": sorted(str(r) for r in roles),
        "ok": "error" not in result,
    }
    if "error" in result:
        rec["error"] = str(result["error"])[:300]

    if tool == "select_schema":
        rec["question"] = str(args.get("question", ""))[:500]
        rec["selected"] = result.get("selected")
        rec["total_objects"] = result.get("total_objects")
        rec["objects"] = list(result.get("objects") or [])
        # how much of the catalog this caller could not see: a count
        vis = result.get("_visible_objects")
        if vis is not None and result.get("total_objects") is not None:
            rec["objects_withheld"] = int(result["total_objects"]) - int(vis)
        cw = result.get("_columns_withheld")
        if cw is not None:
            rec["columns_withheld"] = int(cw)

    elif tool == "list_objects":
        rec["count"] = result.get("count")
        rec["total_objects"] = result.get("total_objects")
        if rec["count"] is not None and rec["total_objects"] is not None:
            rec["objects_withheld"] = int(rec["total_objects"]) - int(rec["count"])

    elif tool == "describe_object":
        rec["name"] = str(args.get("name", ""))[:200]
        # `_denied_reason` is set server-side only; the caller's reply is the
        # same for restricted and missing, the log may know which.
        if result.get("_denied_reason"):
            rec["denied"] = result["_denied_reason"]

    elif tool in ("run_query", "answer"):
        if tool == "answer":
            rec["question"] = str(args.get("question", ""))[:500]
            if result.get("refused"):
                rec["refused"] = str(result["refused"])[:300]
        sql = result.get("sql") or args.get("sql")
        if sql:
            rec["sql"] = str(sql)[:4000]
        if result.get("_tables"):
            rec["tables"] = list(result["_tables"])
        if "row_count" in result:
            rec["row_count"] = result["row_count"]
            rec["truncated"] = bool(result.get("truncated"))
        if result.get("_refused_reason"):
            rec["refused"] = result["_refused_reason"]
    return rec


class AuditLog:
    """Append-only JSON Lines, plus an in-memory ring for `health`."""

    def __init__(self, path: Optional[os.PathLike] = None, *,
                 max_bytes: int = DEFAULT_MAX_BYTES, ring: int = RING) -> None:
        self.path: Optional[Path] = Path(path) if path else None
        self.max_bytes = int(max_bytes)
        self._ring: Deque[Record] = collections.deque(maxlen=ring)
        self._lock = threading.Lock()
        self.stats: Dict[str, int] = {"records": 0, "refused": 0, "errors": 0,
                                      "write_failures": 0}
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "AuditLog":
        """`SCHEMAGATE_AUDIT_LOG` unset -> memory only. `1`/`default`/`on`
        -> the default file. Anything else -> that path."""
        src = os.environ if env is None else env
        raw = (src.get(ENV_PATH) or "").strip()
        if not raw or raw == "0":
            return cls(None)
        if raw.lower() in ("1", "default", "on", "true"):
            return cls(default_path())
        return cls(raw)

    @property
    def enabled(self) -> bool:
        return self.path is not None

    # -- writing -----------------------------------------------------------

    def record(self, rec: Record) -> Record:
        """Append one record. Never raises: an audit log that can take the
        server down is a denial-of-service lever, so a failed write is
        counted and logged, and the call it was recording still returns."""
        with self._lock:
            self._ring.append(rec)
            self.stats["records"] += 1
            if not rec.get("ok", True):
                self.stats["errors"] += 1
            if rec.get("refused") or rec.get("denied"):
                self.stats["refused"] += 1
            if self.path is None:
                return rec
            try:
                self._rotate_if_needed()
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
                    fh.write("\n")
            except OSError:
                self.stats["write_failures"] += 1
                import logging
                logging.getLogger("schemagate.audit").exception("audit write failed")
        return rec

    def _rotate_if_needed(self) -> None:
        assert self.path is not None
        try:
            size = self.path.stat().st_size
        except FileNotFoundError:
            return
        if size < self.max_bytes:
            return
        prev = self.path.with_suffix(self.path.suffix + ".1")
        if prev.exists():
            prev.unlink()
        self.path.rename(prev)

    # -- reading -----------------------------------------------------------

    def recent(self, n: int = 50) -> List[Record]:
        """The last ``n`` records held in memory. Server-side use only."""
        with self._lock:
            items = list(self._ring)
        return items[-n:]

    def describe(self) -> Dict[str, Any]:
        """For `health`: counts and whether a file is on. No content."""
        return {"file": str(self.path) if self.path else None,
                "in_memory": len(self._ring), **self.stats}

    @staticmethod
    def read(path: os.PathLike, *, since: Optional[str] = None,
             principal: Optional[str] = None) -> Iterable[Record]:
        """Stream records back from a file, optionally filtered. This is the
        operator's reader; nothing on the server calls it."""
        with Path(path).open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if since and rec.get("ts", "") < since:
                    continue
                if principal and rec.get("principal") != principal:
                    continue
                yield rec
