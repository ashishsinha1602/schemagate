"""Offline check, no model calls: for every LiveSQLBench-Large task, does schemagate's table selection contain
every table the official solution touches, and how big is the prompt compared with the full-schema baseline?

    PYTHONPATH=<schemagate>/src python lsb_select.py --k 8 12 16 20
"""
import argparse
import json
import re
import statistics
from pathlib import Path

import sqlglot
from sqlglot import exp

import os

from schemagate import Catalog, Column, ForeignKey, ObjectDoc

USE_FKS = os.environ.get("LSB_FKS", "1") == "1"
KB_N = int(os.environ.get("LSB_KB", "0"))

BASE = Path(r"E:\livesqlbench")
PUB = BASE / "public"


def split_schema(text: str) -> dict:
    """{table_name_lower: block} — each block is the CREATE TABLE statement plus its sample rows."""
    blocks = {}
    for m in re.finditer(r"CREATE TABLE\s+\"?([^\s\"(]+)\"?\s*\((.*?)(?=\nCREATE TABLE|\Z)", text, re.S):
        blocks[m.group(1).lower()] = m.group(0).strip()
    return blocks


def columns_of(block: str) -> list:
    body = block.split("(", 1)[1].split("\n);", 1)[0]
    cols = []
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith(("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CONSTRAINT", "CHECK")):
            continue
        m = re.match(r'"?([^"\s]+)"?\s+(.+?)\s+(NOT NULL|NULL)?$', line)
        if m:
            cols.append((m.group(1), m.group(2)))
    return cols


class DB:
    def __init__(self, name: str):
        d = PUB / name
        self.name = name
        self.schema_text = (d / f"{name}_schema.txt").read_text("utf-8", errors="replace")
        self.blocks = split_schema(self.schema_text)
        self.meanings = {k.lower(): v for k, v in json.loads((d / f"{name}_column_meaning_base.json").read_text("utf-8")).items()}
        self.kb = [json.loads(l) for l in (d / f"{name}_kb.jsonl").read_text("utf-8").splitlines() if l.strip()]
        self.cat = Catalog(name=name)
        for t, block in self.blocks.items():
            cols = []
            for c, ty in columns_of(block):
                m = self.meanings.get(f"{name}|{t}|{c}".lower())
                cols.append(Column(c, ty, True, (str(m)[:300] if m else None), False))
            fks = [ForeignKey([c.strip('" ') for c in m.group(1).split(",")], m.group(2).strip('"').lower(),
                              [c.strip('" ') for c in m.group(3).split(",")])
                   for m in re.finditer(r'FOREIGN KEY\s*\(([^)]*)\)\s*REFERENCES\s+"?([^\s"(]+)"?\s*\(([^)]*)\)', block)]
            self.cat.add(ObjectDoc(name=t, schema=None, kind="TABLE", description=None, columns=cols,
                                   foreign_keys=fks if USE_FKS else []))
        self.cat.index()
        # the knowledge base, embedded once: the entries closest to a question are added to the text the
        # selector reads (the full KB still goes into the prompt, as in the baseline)
        self.kb_texts = [f"{e.get('knowledge','')}: {e.get('description','')} {e.get('definition','')}" for e in self.kb]
        self.kb_vecs = self.cat.embedder.embed(self.kb_texts) if self.kb_texts else []

    def selection_question(self, q: str, n: int) -> str:
        if not n or not self.kb_texts:
            return q
        qv = self.cat.embedder.embed([q])[0]
        score = lambda v: sum(a * b for a, b in zip(qv, v))     # noqa: E731  vectors are normalised
        best = sorted(range(len(self.kb_texts)), key=lambda i: -score(self.kb_vecs[i]))[:n]
        return q + "\n" + "\n".join(self.kb_texts[i] for i in best)

    def table_meanings(self, tables) -> dict:
        keep = {f"{self.name}|{t}|".lower() for t in tables}
        return {k: v for k, v in self.meanings.items() if any(k.startswith(p) for p in keep)}

    def kb_text(self) -> str:
        vis = [{k: e[k] for k in ("id", "knowledge", "description", "definition") if k in e} for e in self.kb]
        return json.dumps(vis, indent=2)

    def full_prompt_chars(self) -> int:
        return len(self.schema_text) + len(json.dumps(self.meanings, indent=2)) + len(self.kb_text())

    def selected_prompt_chars(self, tables) -> int:
        return (sum(len(self.blocks[t]) for t in tables) + len(json.dumps(self.table_meanings(tables), indent=2))
                + len(self.kb_text()))


def gold_tables(sqls, known) -> set:
    out = set()
    for s in sqls:
        try:
            for tree in sqlglot.parse(s, read="postgres"):
                if tree is None:
                    continue
                ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
                for t in tree.find_all(exp.Table):
                    n = t.name.lower()
                    if n in known and n not in ctes:
                        out.add(n)
        except Exception:                                   # noqa: BLE001
            out |= {n for n in known if re.search(rf'\b"?{re.escape(n)}"?\b', s, re.I)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, nargs="+", default=[8, 12, 16, 20])
    ap.add_argument("--field", default="query")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(BASE / "work/full.jsonl", encoding="utf-8")]
    dbs = {}
    stats = {k: {"hit": 0, "chars": []} for k in a.k}
    full_chars, n_tables = [], []
    for r in rows:
        name = r["selected_database"]
        if name not in dbs:
            dbs[name] = DB(name)
        db = dbs[name]
        gold = gold_tables(r["sol_sql"], set(db.blocks))
        n_tables.append(len(gold))
        full_chars.append(db.full_prompt_chars())
        for k in a.k:
            sel = {t.lower() for t in db.cat.select(db.selection_question(r[a.field], KB_N), top_k=k).table_names}
            stats[k]["hit"] += gold <= sel
            stats[k]["chars"].append(db.selected_prompt_chars(sel))
    n = len(rows)
    print(f"{n} tasks, {len(dbs)} databases, avg tables per db {statistics.mean(len(d.blocks) for d in dbs.values()):.1f}, "
          f"gold tables per task: median {statistics.median(n_tables)}, max {max(n_tables)}")
    print(f"full-schema prompt: median {statistics.median(full_chars)/4/1000:.1f}K tokens (chars/4)")
    for k in a.k:
        s = stats[k]
        print(f"top_k={k:>2}: all gold tables selected in {s['hit']}/{n} = {100*s['hit']/n:.1f}% | "
              f"prompt median {statistics.median(s['chars'])/4/1000:.1f}K tokens")


if __name__ == "__main__":
    main()
