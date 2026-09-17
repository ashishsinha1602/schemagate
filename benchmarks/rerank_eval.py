"""Does the reranker actually help? Paired, on the business-language questions.

The hook has existed since the reranker landed and has never been measured.
`tests/test_rerank.py` proves it is *safe* -- a model that fails or replies with
nonsense leaves the maths order untouched, and a restricted object cannot be
promoted into an answer -- but safety is not usefulness, and no recall number
for it existed until this script.

Paired design, because that is the only kind that can answer the question.
Every question is scored twice against the *same* catalog, the same embedder
and the same top_k: once with `reranker=None` and once with a model reordering
the shortlist. Net margins cannot distinguish "fixed seven" from "fixed
fourteen and broke seven", so the report is b/c discordant pairs and McNemar's
exact test, the same standard BENCHMARKS.md holds the prose ablation to.

    ANTHROPIC_API_KEY=... python benchmarks/rerank_eval.py
    python benchmarks/rerank_eval.py --model claude-sonnet-4-5 --top-k 6

TUNE (commerce, health) and HELDOUT (warehouse, finance, telemetry, complex)
are reported separately and the overall verdict is read off HELDOUT, because
the ranking was tuned while looking at the first two.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(os.path.dirname(HERE), "tests")
sys.path.insert(0, TESTS)

import paraphrase_eval as EV                                  # noqa: E402
from run_paraphrase_eval import build                         # noqa: E402


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact p for the discordant pairs, no SciPy.

    Under the null a discordant pair is a fair coin, so the count of one kind
    is Binomial(b+c, 1/2). Concordant pairs carry no information about a
    difference and are excluded -- which is the whole point of the test, and
    why a net margin over 58 questions is not evidence.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1))
    return min(1.0, 2.0 * tail / (2 ** n))


def run(model: str, top_k: int, candidates: int, show_flips: bool,
        only=None):
    from schemagate.ai import providers as _p

    provider = _p.AnthropicProvider(model=model)
    print(f"reranker : {provider.name}   candidates={candidates}  top_k={top_k}")

    try:
        from schemagate import Catalog
        emb = Catalog(name="_probe").embedder.name
    except Exception:                                          # noqa: BLE001
        emb = "unknown"
    print(f"embedder : {emb}\n")

    print(f"{'schema':<12}{'set':<9}{'base':>8}{'rerank':>9}"
          f"{'b':>5}{'c':>5}{'p':>9}")
    print("-" * 57)

    totals = {"b": 0, "c": 0, "base": 0, "rr": 0, "n": 0}
    per = {}
    flips = []
    calls = 0
    t0 = time.time()

    sets = {k: v for k, v in EV.ALL.items() if not only or k in only}
    if not sets:
        raise SystemExit(f"no such schema(s): {sorted(only)}; "
                         f"choose from {sorted(EV.ALL)}")

    for name, questions in sets.items():
        cat = build(name)
        b = c = base_hits = rr_hits = 0

        for q, gold in questions:
            base = {t.split(".")[-1] for t in
                    cat.select(q, top_k=top_k).table_names}
            rr = {t.split(".")[-1] for t in
                  cat.select(q, top_k=top_k, reranker=provider,
                             rerank_candidates=candidates).table_names}
            calls += 1

            base_ok, rr_ok = bool(gold & base), bool(gold & rr)
            base_hits += base_ok
            rr_hits += rr_ok
            # b: the reranker fixed one the maths missed. c: it broke one the
            # maths had. Only these two carry information.
            if rr_ok and not base_ok:
                b += 1
                # The whole set, plus which gold member matched. An earlier
                # version printed sorted(rr)[:4], which alphabetically
                # truncated away the very table that had just been found, so
                # every FIXED line read like a miss.
                flips.append(("FIXED", name, q, sorted(gold),
                              sorted(rr), sorted(gold & rr)))
            elif base_ok and not rr_ok:
                c += 1
                flips.append(("BROKE", name, q, sorted(gold),
                              sorted(rr), sorted(gold & base)))

        n = len(questions)
        p = mcnemar_exact(b, c)
        kind = "TUNE" if name in EV.TUNE else "HELDOUT"
        per[name] = (base_hits, rr_hits, n, b, c, p)
        for key, val in (("b", b), ("c", c), ("base", base_hits),
                         ("rr", rr_hits), ("n", n)):
            totals[key] += val
        print(f"{name:<12}{kind:<9}{base_hits/n*100:7.1f}%{rr_hits/n*100:8.1f}%"
              f"{b:>5}{c:>5}{p:>9.3f}")

    print("-" * 57)

    def block(label, names):
        # Only what actually ran -- `--schemas` can leave a block empty, and a
        # summary row invented from schemas that were never scored would be
        # worse than no row at all.
        names = [k for k in names if k in per]
        if not names:
            return 0, 0, 1.0
        bb = sum(per[k][3] for k in names)
        cc = sum(per[k][4] for k in names)
        bs = sum(per[k][0] for k in names)
        rs = sum(per[k][1] for k in names)
        nn = sum(per[k][2] for k in names)
        p = mcnemar_exact(bb, cc)
        print(f"{label:<21}{bs/nn*100:7.1f}%{rs/nn*100:8.1f}%"
              f"{bb:>5}{cc:>5}{p:>9.3f}")
        return bb, cc, p

    block("TUNE", EV.TUNE)
    h_b, h_c, h_p = block("HELD OUT", EV.HELDOUT)
    o_b, o_c, o_p = block("OVERALL", EV.ALL)

    print(f"\n{calls} reranked selections in {time.time() - t0:.0f}s")

    if show_flips and flips:
        print("\nEvery question whose verdict changed:")
        for kind, schema, q, gold, got, matched in flips:
            label = "matched" if kind == "FIXED" else "lost   "
            print(f"  {kind} [{schema}] {q!r}\n"
                  f"          want    {gold}\n"
                  f"          top_k   {got}\n"
                  f"          {label} {matched}")

    print("\nVerdict, on HELD OUT only (TUNE was tuned on):")
    if not [k for k in EV.HELDOUT if k in per]:
        # Not the same thing as "it changed nothing", and saying so would be
        # a reassuring sentence about a measurement that never happened.
        print("  No held-out schema was run, so there is no verdict.")
    elif h_b == h_c == 0:
        print("  The reranker changed no held-out verdict at all.")
    elif h_p < 0.05:
        direction = "helps" if h_b > h_c else "HURTS"
        print(f"  {direction}: b={h_b} c={h_c}, p={h_p:.3f} -- clears 0.05.")
    else:
        print(f"  b={h_b} c={h_c}, p={h_p:.3f} -- does not clear 0.05. "
              f"The direction is {'positive' if h_b > h_c else 'negative'}, "
              f"but {h_b + h_c} discordant pairs cannot carry the claim.")
    return per


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="claude-sonnet-4-5")
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--candidates", type=int, default=20)
    ap.add_argument("--quiet", action="store_true",
                    help="omit the per-question flip list")
    ap.add_argument("--schemas", default="",
                    help="comma-separated subset, e.g. complex,telemetry "
                         "(default: all six)")
    args = ap.parse_args()
    only = {s.strip() for s in args.schemas.split(",") if s.strip()}

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set -- nothing would be measured.",
              file=sys.stderr)
        return 2
    run(args.model, args.top_k, args.candidates, not args.quiet, only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
