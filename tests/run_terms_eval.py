"""Business-language recall with and without a glossary (``Catalog.term``), on the three HELD-OUT schemas.

Protocol, so the number means something: each glossary in tests/glossaries/ was written from the schema's
object names alone, before its paraphrase questions were read, the way an analyst at that company would list
the words people use. The questions are tests/paraphrase_eval.py, unchanged. Paired per question, with
McNemar's exact test on the discordant pairs.

    PYTHONPATH=src python tests/run_terms_eval.py
"""
from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import paraphrase_eval as EV  # noqa: E402
import run_paraphrase_eval as R  # noqa: E402

SCHEMAS = ("finance", "telemetry", "complex")


def mcnemar_p(b: int, c: int) -> float:
    """Exact two-sided McNemar: binomial on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def hits(cat, questions, top_k):
    out = []
    for q, gold in questions:
        got = {n.split(".")[-1] for n in cat.select(q, top_k=top_k).table_names}
        out.append(bool(gold & got))
    return out


def main(top_k: int = 6):
    print(f"embedder: {R._embedder_name()}   top_k={top_k}")
    print(f"{'schema':<11}{'terms':>6}{'without':>12}{'with':>12}{'fixed':>7}{'broken':>8}")
    tb = tc = tn = tw = tg = 0
    for name in SCHEMAS:
        qs = EV.ALL[name]
        base = hits(R.build(name), qs, top_k)
        cat = R.build(name)
        with open(os.path.join(HERE, "glossaries", f"{name}.json"), encoding="utf-8") as fh:
            gloss = json.load(fh)
        for phrase, objs in gloss.items():
            cat.term(phrase, objs)
        withg = hits(cat, qs, top_k)
        b = sum(1 for x, y in zip(base, withg) if y and not x)
        c = sum(1 for x, y in zip(base, withg) if x and not y)
        n = len(qs)
        print(f"{name:<11}{len(gloss):>6}{sum(base):>7}/{n:<4}{sum(withg):>7}/{n:<4}{b:>7}{c:>8}")
        tb += b; tc += c; tn += n; tw += sum(base); tg += sum(withg)
    print(f"{'HELD OUT':<17}{tw:>7}/{tn:<4}{tg:>7}/{tn:<4}{tb:>7}{tc:>8}"
          f"   {tw / tn * 100:.1f}% -> {tg / tn * 100:.1f}%   McNemar p={mcnemar_p(tb, tc):.4f}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
