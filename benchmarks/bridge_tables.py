# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Zero-overlap bridge tables: does the selection contain the join path, or only the obvious tables?

Suggested on r/LangChain: finding the two business tables is not enough if the selected DDL omits the
table that joins them, and that table often shares no word with the question. So this isolates them.

For every question, a gold table (one the reference SQL reads) is a *zero-overlap* table when no word
of its name appears in the question, after splitting names on `_` and comparing lowercased stems.
Reported, per setting: how many questions have one, and how often schemagate's selection holds every
such table, and every gold table, at the same top_k -- with plain FK expansion, and with
``expand_inward`` (tables that join *into* the selection) added.

    python benchmarks/bridge_tables.py                                   # BIRD dev, SQLite
    python benchmarks/bridge_tables.py --beaver beaver-query/dw.parquet \
        --mysql-url mysql+pymysql://root:...@127.0.0.1:3307/dw           # BEAVER dw, local MySQL

BIRD dev is unpacked at benchmarks/dev_20240627 (or BIRD_DIR). BEAVER is gated on Hugging Face
(beaverbench/beaver-query, beaver-table); its MySQL dump must be loaded with lower_case_table_names=1.
No model is called.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from schemagate import Catalog  # noqa: E402


def words(text: str):
    """Lowercased word stems: `subjects` and `SUBJECT_OFFERED` both give `subject`."""
    out = set()
    for w in re.findall(r"[A-Za-z]+", text):
        w = w.lower()
        for suf in ("ies", "es", "s"):
            if w.endswith(suf) and len(w) > len(suf) + 2:
                w = w[: -len(suf)] + ("y" if suf == "ies" else "")
                break
        if len(w) > 1:
            out.add(w)
    return out


def zero_overlap(question: str, gold):
    q = words(question)
    return {t for t in gold if not (words(t.replace("_", " ")) & q)}


def bird_cases():
    from bird import gold_tables
    root = pathlib.Path(os.environ.get("BIRD_DIR", str(HERE / "dev_20240627")))
    dev = json.loads((root / "dev.json").read_text("utf-8"))
    cats = {}
    for db in sorted({q["db_id"] for q in dev}):
        path = root / "dev_databases" / db / f"{db}.sqlite"
        cat = Catalog(name=db).bootstrap(f"sqlite:///{path.as_posix()}", sample_values=True)
        cat.infer_foreign_keys()
        cats[db] = cat.index()
    for q in dev:
        cat = cats[q["db_id"]]
        known = {d.name.lower() for d in cat.objects()}
        yield cat, q["question"], gold_tables(q["SQL"], known)


def beaver_cases(parquet: str, url: str):
    import pandas as pd
    import sqlalchemy as sa
    db = url.rsplit("/", 1)[-1].split("?")[0]
    cat = Catalog(name=db).bootstrap(sa.create_engine(url), schemas=[db], sample_values=True)
    cat.infer_foreign_keys()
    cat.index()
    for q in pd.read_parquet(parquet).to_dict("records"):
        gold = json.loads(q["tables"]) if isinstance(q["tables"], str) else list(q["tables"])
        yield cat, q["question"], {t.lower() for t in gold}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--top-k", type=int, default=0, help="default: 8 for BIRD, 25 for BEAVER")
    ap.add_argument("--inward", type=int, default=0, help="expand_inward window; default 2 x top_k")
    ap.add_argument("--beaver", help="a beaver-query parquet (e.g. dw); needs --mysql-url")
    ap.add_argument("--mysql-url")
    ap.add_argument("--limit", type=int, default=0, help="only the first N questions")
    a = ap.parse_args()
    if a.beaver and not a.mysql_url:
        ap.error("--beaver needs --mysql-url")
    k = a.top_k or (25 if a.beaver else 8)
    inward = a.inward or 2 * k
    cases = beaver_cases(a.beaver, a.mysql_url) if a.beaver else bird_cases()

    n = with_zero = 0
    stats = {"plain": [0, 0], "inward": [0, 0]}         # [all zero-overlap found, all gold found]
    for i, (cat, question, gold) in enumerate(cases):
        if a.limit and i >= a.limit:
            break
        if not gold:
            continue
        n += 1
        zero = zero_overlap(question, gold)
        with_zero += bool(zero)
        for name, kw in (("plain", {}), ("inward", {"expand_inward": inward})):
            sel = {h.doc.name.lower() for h in cat.select(question, top_k=k, **kw).hits}
            if zero and zero <= sel:
                stats[name][0] += 1
            if gold <= sel:
                stats[name][1] += 1
    print(f"{'BEAVER ' + pathlib.Path(a.beaver).stem if a.beaver else 'BIRD dev'}: {n} questions, top_k={k}")
    print(f"questions with a zero-overlap gold table: {with_zero} ({100 * with_zero / max(1, n):.1f}%)")
    for name, (z, g) in stats.items():
        label = "FK expansion" if name == "plain" else f"+ expand_inward={inward}"
        print(f"  {label:24s} zero-overlap tables all selected: {z}/{with_zero} ({100 * z / max(1, with_zero):.1f}%)"
              f"   every gold table selected: {g}/{n} ({100 * g / max(1, n):.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
