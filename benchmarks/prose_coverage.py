"""How much prose does each benchmark's schema actually carry?

"One has descriptions and the other does not" is the hypothesis under test.
This turns it into a number: what fraction of tables carry a non-empty
description, and how long those descriptions are.

Counts every table in each benchmark's schema dump, not only the ones a
question happens to touch.
"""
import json
import pathlib
import statistics

HERE = pathlib.Path(__file__).resolve().parent


def report(label, descs, total, table_counts=None):
    have = [d for d in descs if d and str(d).strip()]
    words = [len(str(d).split()) for d in have]
    pct = 100 * len(have) / total if total else 0.0
    print(f"  {label:18} {len(have):5}/{total:<5} tables have a description "
          f"({pct:5.1f}%)", end="")
    if words:
        print(f"   mean {statistics.mean(words):6.1f} words, "
              f"median {statistics.median(words):.0f}")
    else:
        print("   -")
    if table_counts:
        print(f"  {'':18} tables/db: median "
              f"{statistics.median(table_counts):.0f}, max {max(table_counts)}, "
              f"n={len(table_counts)} databases")


print("prose carried by each benchmark's schema\n")

# ---- Spider 1.0: the published schema dump has no description field --------
rows = json.loads((HERE / "spider_schema.json").read_text("utf-8"))
n_tables, counts = 0, []
for r in rows:
    chunks = [c for c in r["Schema (values (type))"].split("|") if ":" in c]
    n_tables += len(chunks)
    counts.append(len(chunks))
report("Spider 1.0", [None] * n_tables, n_tables, counts)

# ---- BIRD: tables.json carries column descriptions, not table ones ---------
bird = json.loads((HERE / "dev_20240627" / "dev_tables.json").read_text("utf-8"))
n, counts = 0, []
for s in bird:
    k = len(s["table_names_original"])
    n += k
    counts.append(k)
report("BIRD", [None] * n, n, counts)

# ---- Spider 2.0: per-table json with a description field -------------------
root = HERE / "Spider2" / "spider2-lite" / "resource" / "databases"
descs, counts = [], []
for eng in root.iterdir():
    if not eng.is_dir():
        continue
    for db in eng.iterdir():
        if not db.is_dir():
            continue
        files = list(db.rglob("*.json"))
        counts.append(len(files))
        for f in files:
            try:
                d = json.loads(f.read_text("utf-8"))
            except Exception:                                # noqa: BLE001
                descs.append(None)
                continue
            v = d.get("description")
            if isinstance(v, (list, tuple)):
                v = " ".join(str(x) for x in v)
            descs.append(v)
report("Spider 2.0", descs, len(descs), counts)

print("\nnote: Spider 1.0's published dump carries types and keys but no prose"
      " at all;\nBIRD's tables.json carries column descriptions, which this"
      " harness does not\nload as table descriptions -- so both are 0% for"
      " the field the ablation removes.")
