# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Bring an ontology you already have: dbt, Snowflake semantic models, CSV glossaries.

Every importer adds concepts to a ``Catalog`` (``Catalog.concept``) and returns
an ``ImportReport``: what was added, what was skipped and why. An entry that
names a table or column this database does not have is skipped and listed,
not fatal -- a company glossary always describes more than one database.

* ``import_dbt(cat, "target/semantic_manifest.json")`` -- measures, metrics and
  entities of dbt semantic models. JSON, no extra dependency.
* ``import_snowflake(cat, "model.yaml")`` -- a Snowflake Cortex Analyst semantic
  model: logical tables, dimensions, facts, measures and named filters, with
  their synonyms. Its ``verified_queries`` come back on the report, ready for
  ``Catalog.learn_concepts``. YAML needs ``pip install pyyaml``; a JSON file
  of the same shape does not.
* ``import_csv(cat, "glossary.csv")`` -- one term per row. Header names are
  matched loosely, so Collibra and Microsoft Purview exports work as they are:
  Name/Term, Synonyms/Acronym/Nick Name, Definition/Description,
  Parent Term Name/Broader, Table, Column, Filter, Maps.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass
class ImportReport:
    added: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    #: Snowflake ``verified_queries``: (question, sql) pairs for ``learn_concepts``.
    examples: List[Tuple[str, str]] = field(default_factory=list)

    def __str__(self) -> str:
        out = [f"{len(self.added)} concept(s) added, {len(self.skipped)} skipped"]
        out += [f"  skipped: {s}" for s in self.skipped[:20]]
        if len(self.skipped) > 20:
            out.append(f"  ... and {len(self.skipped) - 20} more")
        return "\n".join(out)


def _words(name: str) -> str:
    return re.sub(r"[_\s]+", " ", str(name or "")).strip()


def _add(cat, report: ImportReport, name: str, *, maps: Sequence[str], source: str,
         synonyms: Sequence[str] = (), filter: Optional[str] = None,
         definition: Optional[str] = None, broader: Sequence[str] = ()) -> None:
    """Add one concept, dropping the mappings this catalog cannot resolve."""
    name = _words(name)
    if not name:
        return
    good, bad = [], []
    for m in maps:
        try:
            cat._resolve_map(m)
            good.append(m)
        except KeyError:
            bad.append(m)
    if maps and not good:
        report.skipped.append(f"{name!r}: {', '.join(bad)} not in this catalog")
        return
    syn = [_words(s) for s in synonyms if _words(s) and _words(s).lower() != name.lower()]
    try:
        cat.concept(name, synonyms=syn, maps=good, filter=filter or None,
                    definition=(definition or "").strip() or None,
                    broader=[_words(b) for b in broader if _words(b)], source=source)
    except (KeyError, ValueError) as e:
        report.skipped.append(f"{name!r}: {e}")
        return
    report.added.append(name)
    if bad:
        report.skipped.append(f"{name!r}: kept, but {', '.join(bad)} not in this catalog")


def _column_or_table(cat, table: str, expr: Optional[str]) -> str:
    """``table.expr`` when expr is a plain column of that table, else ``table``."""
    e = (expr or "").strip().strip('"')
    if e and re.fullmatch(r"[A-Za-z_][\w$#]*", e):
        try:
            cat._resolve_map(f"{table}.{e}")
            return f"{table}.{e}"
        except KeyError:
            pass
    return table


# ------------------------------------------------------------------------ dbt

def import_dbt(cat, path) -> ImportReport:
    """Concepts from a dbt ``semantic_manifest.json`` (``dbt parse`` writes it to target/)."""
    data = json.loads(Path(path).read_text("utf-8"))
    report = ImportReport()
    measure_home: Dict[str, Tuple[str, str]] = {}
    for sm in data.get("semantic_models") or []:
        rel = sm.get("node_relation") or {}
        table = rel.get("alias") or sm.get("name")
        try:
            cat._resolve_object(table)
        except KeyError:
            report.skipped.append(f"semantic model {sm.get('name')!r}: table {table!r} not in this catalog")
            continue
        for ent in sm.get("entities") or []:
            if (ent.get("type") or "").lower() == "primary":
                _add(cat, report, ent.get("name"), maps=[table], source="dbt",
                     definition=sm.get("description"))
        for m in sm.get("measures") or []:
            target = _column_or_table(cat, table, m.get("expr") or m.get("name"))
            measure_home[m.get("name")] = (table, target)
            agg = (m.get("agg") or "").lower()
            how = f"{agg} of {m.get('expr') or m.get('name')}" if agg else None
            definition = "; ".join(x for x in (m.get("description"), how) if x)
            _add(cat, report, m.get("label") or m.get("name"), maps=[target], source="dbt",
                 synonyms=[m.get("name")] if m.get("label") else [], definition=definition)
    for metric in data.get("metrics") or []:
        tp = metric.get("type_params") or {}
        measure = (tp.get("measure") or {}).get("name") if isinstance(tp.get("measure"), dict) else tp.get("measure")
        if measure not in measure_home:
            report.skipped.append(f"metric {metric.get('name')!r}: its measure is not mapped")
            continue
        flt = _dbt_filter(metric.get("filter"))
        _add(cat, report, metric.get("label") or metric.get("name"), maps=[measure_home[measure][1]],
             source="dbt", synonyms=[metric.get("name")] if metric.get("label") else [],
             filter=flt, definition=metric.get("description"))
    return report


def _dbt_filter(flt: Any) -> Optional[str]:
    """dbt's ``{{ Dimension('order__status') }} = 'issued'`` as plain SQL: ``status = 'issued'``."""
    if not flt:
        return None
    if isinstance(flt, dict):
        flt = " AND ".join(w.get("where_sql_template", "") for w in flt.get("where_filters") or [])
    if isinstance(flt, list):
        flt = " AND ".join(str(f) for f in flt)
    out = re.sub(r"\{\{\s*(?:Dimension|TimeDimension|Entity)\(\s*'(?:[^'_]+__)?([^']+)'[^)]*\)\s*\}\}", r"\1", str(flt))
    return out.strip() or None


# ------------------------------------------------------------------ snowflake

def _load_yaml_or_json(path) -> Any:
    text = Path(path).read_text("utf-8")
    if str(path).lower().endswith(".json"):
        return json.loads(text)
    try:
        import yaml
    except ImportError as e:
        raise ImportError("reading a YAML semantic model needs: pip install pyyaml "
                          "(or pass the same model as a .json file)") from e
    return yaml.safe_load(text)


def import_snowflake(cat, path) -> ImportReport:
    """Concepts from a Snowflake Cortex Analyst semantic model (YAML or JSON)."""
    data = _load_yaml_or_json(path) or {}
    report = ImportReport()
    for t in data.get("tables") or []:
        base = t.get("base_table") or {}
        table = base.get("table") or t.get("name")
        candidates = [f"{base.get('schema')}.{table}" if base.get("schema") else None, table]
        resolved = None
        for c in candidates:
            if not c:
                continue
            try:
                cat._resolve_object(c)
                resolved = c
                break
            except KeyError:
                continue
        if resolved is None:
            report.skipped.append(f"logical table {t.get('name')!r}: {table!r} not in this catalog")
            continue
        _add(cat, report, t.get("name"), maps=[resolved], source="snowflake",
             synonyms=t.get("synonyms") or [], definition=t.get("description"))
        for kind in ("dimensions", "time_dimensions", "facts", "measures", "metrics"):
            for f in t.get(kind) or []:
                target = _column_or_table(cat, resolved, f.get("expr"))
                definition = f.get("description")
                if target == resolved and f.get("expr"):
                    definition = "; ".join(x for x in (definition, f"computed as {f['expr']}") if x)
                _add(cat, report, f.get("name"), maps=[target], source="snowflake",
                     synonyms=f.get("synonyms") or [], definition=definition)
        for f in t.get("filters") or []:
            _add(cat, report, f.get("name"), maps=[resolved], source="snowflake",
                 synonyms=f.get("synonyms") or [], filter=f.get("expr"),
                 definition=f.get("description"))
    for vq in data.get("verified_queries") or []:
        if vq.get("question") and vq.get("sql"):
            report.examples.append((vq["question"], vq["sql"]))
    return report


# ------------------------------------------------------------------------ csv

_HEADERS = {
    "name": ("name", "term", "business term", "term name", "concept", "label"),
    "synonyms": ("synonyms", "synonym", "acronym", "acronyms", "nick name", "nickname",
                 "alternative names", "also known as", "aliases"),
    "definition": ("definition", "description", "meaning"),
    "broader": ("parent term name", "parent term", "parent", "broader", "broader term", "category"),
    "table": ("table", "table name", "physical table", "object", "asset", "physical name"),
    "column": ("column", "column name", "physical column", "field"),
    "filter": ("filter", "rule", "condition", "where"),
    "maps": ("maps", "maps to", "mapping", "mapped to"),
}


def _split(v: Optional[str]) -> List[str]:
    return [x.strip() for x in re.split(r"[|;,]", v or "") if x.strip()]


def import_csv(cat, path) -> ImportReport:
    """One concept per row of a glossary CSV (Collibra, Purview, a spreadsheet)."""
    report = ImportReport()
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return report
    lookup = {}
    for h in rows[0].keys():
        key = (h or "").strip().lower()
        for field_, names in _HEADERS.items():
            if key in names and field_ not in lookup:
                lookup[field_] = h
    if "name" not in lookup:
        raise ValueError(f"{path}: no term column; expected one of {_HEADERS['name']}")

    def get(row, f):
        h = lookup.get(f)
        return (row.get(h) or "").strip() if h else ""

    for row in rows:
        maps = _split(get(row, "maps"))
        table, column = get(row, "table"), get(row, "column")
        if table:
            maps.append(f"{table}.{column}" if column else table)
        _add(cat, report, get(row, "name"), maps=maps, source="csv",
             synonyms=_split(get(row, "synonyms")), filter=get(row, "filter") or None,
             definition=get(row, "definition"), broader=_split(get(row, "broader")))
    return report
