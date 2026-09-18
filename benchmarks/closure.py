"""FK closure: how many objects a selection carries beyond the ranked budget.

    closure(K) = returned(K) - min(K, supply)

`returned(K)` is what select(top_k=K) actually hands back and `supply` is the
number of objects in the schema, so closure counts what arrived that ranking
alone could not have put there. In this library that is foreign-key expansion:
a ranked pick drags in the table it references, and the result is wider than
the budget asked for.

Hence **FK closure**, not "closure". The coverage pass also appends, but over
the 2,074 selections measured here it returns a `covers` pick three times
(0 commerce, 0 health, 0 warehouse, 1 finance, 2 telemetry) and it is
budget-neutral in both branches -- inside the budget it displaces a ranked
pick, and when nothing is droppable it abandons the pick rather than growing
the answer. It cannot enter closure. FK expansion can, and does.

Why not a min/max pair
----------------------
Both endpoints are artifacts of the grid rather than facts about the system.

The floor is arithmetic. Once K reaches supply the ranked set is everything,
min(K, supply) is supply, and closure is 0 because there is nothing left to
add -- a clamp, not a measurement. Across these five schemas most of the zeros
on a coarse grid are clamp-forced that way.

The ceiling moves with the grid: a maximum taken over an arbitrary set of K
values is a property of that set, not of the system. Counting how many
questions peak higher on a dense grid than a coarse one measures the two
grids against each other and tells you nothing about foreign-key expansion,
so it is not reported here either.

So this reports the whole curve for K < supply, with the grid and the supply
printed beside it, and the argmax K -- where the expansion does the most work
-- rather than two numbers that look like bounds and are not.

    python benchmarks/closure.py            # every schema
    python benchmarks/closure.py health     # one

Deterministic: the hashed embedder, which is what `pip install schemagate`
gives you. sentence-transformers ranks differently and produces a different
curve -- health's reference sequence peaks at 8 hashed and 5 with MiniLM --
so the embedder is named in the output.
"""
from __future__ import annotations

import os
import pathlib
import sys
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from schemagate import Catalog                               # noqa: E402
import paraphrase_eval as EV                                 # noqa: E402
import run_paraphrase_eval as RPE                            # noqa: E402

#: The five schemas with a question set and a known object count. `complex` is
#: left out: its questions are six, and its supply of 260 makes the dense sweep
#: 1,560 selections on its own for no extra signal.
SCHEMAS = ["commerce", "health", "warehouse", "finance", "telemetry"]


def curve(cat, question, supply, reasons=None):
    """closure(K) for K = 1 .. supply. The last entry is always the clamp.

    One select() per K, not two: the reason tally is taken from the same
    selection rather than re-running it, which halves 2,074 selections.
    """
    out = []
    for k in range(1, supply + 1):
        sel = cat.select(question, top_k=k)
        if reasons is not None:
            for sc in sel.hits:
                reasons[sc.reason] += 1
        out.append(len(sel.object_list) - min(k, supply))
    return out


def main(argv=None):
    names = list(argv or sys.argv[1:]) or SCHEMAS
    print("FK closure(K) = returned(K) - min(K, supply)")
    print("embedder: %s" % Catalog(name="_probe").embedder.name)
    print()

    reasons = Counter()
    covers_by_schema = Counter()
    total_selections = 0

    for name in names:
        cat = RPE.build(name)
        supply = len(list(cat.objects()))
        questions = [q for q, _ in EV.ALL[name]]
        before_covers = reasons["covers"]
        print("--- %s: supply %d objects, %d questions, K = 1..%d ---"
              % (name, supply, len(questions), supply))
        for q in questions:
            c = curve(cat, q, supply, reasons)
            total_selections += supply
            # K < supply: the last point is the clamp and says nothing.
            body = c[:-1]
            peak = max(body) if body else 0
            argmax = body.index(peak) + 1 if body else 0
            # `body`, not `c`: the curve is reported for K < supply, and the
            # final point is the clamp -- at K = supply the ranked set is
            # everything, min(K, supply) is supply, and closure is 0 by
            # arithmetic. Printing it invites it to be read as a measurement.
            print("  %-46s argmax K=%-3d closure %d  |  %s"
                  % (q[:46], argmax, peak,
                     " ".join(str(x) for x in body)))
        covers_by_schema[name] = reasons["covers"] - before_covers
        print()

    print("over %d selections, the reason each returned object carried:" % total_selections)
    for r, n in reasons.most_common():
        print("  %-8s %6d" % (r, n))
    print()
    print("`covers` picks returned, by schema:")
    for name in names:
        print("  %-11s %d" % (name, covers_by_schema[name]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
