"""Recall table and McNemar over the per-cap outcome files.

Separate from the runs so the expensive part happens once. Each
outcome_<embedder>_<cap>.json holds {k: {instance_id: bool}} for one cap in
one process, which is how this finally ran to completion -- five caps in one
process died twice on memory, silently, mid-run.
"""
import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
CAPS = ["0", "40", "200", "1000", "unlimited"]
KS = ["5", "10", "20"]


def mcnemar(b, c):
    """Exact two-sided binomial test on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def load(tag):
    out = {}
    for cap in CAPS:
        f = HERE / ("outcome_%s_%s.json" % (tag, cap))
        if not f.is_file():
            return None
        out[cap] = json.loads(f.read_text("utf-8"))
    return out


def main():
    for tag in ("hashed", "minilm"):
        data = load(tag)
        if data is None:
            print("%s: incomplete" % tag)
            continue
        n = data["unlimited"]["n"]
        emb = data["unlimited"]["embedder"]
        print("\n=== %s (%s), n=%d ===" % (tag, emb, n))
        print("  %10s " % "cap" + " ".join("%13s" % ("k=" + k) for k in KS))
        for cap in CAPS:
            cells = []
            for k in KS:
                h = sum(data[cap]["outcome"][k].values())
                cells.append("%3d/%d %5.1f%%" % (h, n, 100 * h / n))
            print("  %10s " % cap + " ".join("%13s" % c for c in cells))

        print("\n  McNemar vs unlimited  (b = fixed by the cap, c = broken by it)")
        for cap in CAPS[:-1]:
            for k in KS:
                u = data["unlimited"]["outcome"][k]
                v = data[cap]["outcome"][k]
                b = sum(1 for i in u if not u[i] and v.get(i))
                c = sum(1 for i in u if u[i] and not v.get(i))
                p = mcnemar(b, c)
                print("    cap=%-9s k=%-3s b=%-3d c=%-3d net=%+d  discordant=%-3d p=%.3f"
                      % (cap, k, b, c, b - c, b + c, p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
