"""What a glossary is for: a miss a user sees is fixed by one term, and nothing else breaks.

For every question in tests/paraphrase_eval.py that misses at top_k=6 (on this embedder), add ONE short term
taken from that question -> its gold object, on top of the blind glossary where one exists. Then re-score
EVERY question of that schema and count fixed and broken. Tuning by design -- this measures repairability,
not blind recall (tests/run_terms_eval.py is the blind number).

    PYTHONPATH=src python tests/run_terms_repair.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import paraphrase_eval as EV  # noqa: E402
import run_paraphrase_eval as R  # noqa: E402

#: The short phrase a user would add after seeing each miss. Written per question, from the question.
REPAIR = {
    "entries that do not add up": ("do not add up", "v_unbalanced_journals"),
    "how much do we expect to lose on lending": ("expect to lose", "v_expected_credit_loss"),
    "how long until someone responds": ("someone responds", "v_alarm_time_to_ack"),
    "boxes that stopped talking to us": ("stopped talking", "v_silent_devices"),
    "units about to run flat": ("run flat", "v_low_battery"),
    "when may we take things offline": ("take things offline", "ops_maintenance_window"),
    "staff numbers per division": ("staff numbers", "v_headcount_by_unit"),
    "how much are we exposed to each party": ("exposed to", "v_counterparty_exposure"),
    "things we're running out of": ("running out of", "v_stock_shortfall"),
    "how many people work in each team": ("people work", "v_employee_headcount"),
    "parcels that arrived late": ("arrived late", "v_order_fulfilment"),
    "who do we buy things from": ("buy things from", "sup_supplier"),
    "what is sitting in each depot": ("depot", "inv_stock_level"),
    "money we gave back to shoppers": ("gave back", "billing_credit_note"),
    "people living with long term conditions": ("long term conditions", "v_chronic_cohort"),
    "what the doctor wrote down as the problem": ("wrote down as the problem", "enc_diagnosis"),
    "money the insurer actually sent us": ("insurer actually sent", "clm_remittance"),
    "what medicines were handed over": ("medicines", "rx_fill"),
    "how well are we scoring on standards": ("scoring on standards", "qm_measure_result"),
    "how long between the visit and the money": ("between the visit and the money", "v_service_lag"),
    "average cost per person per month": ("cost per person per month", "v_pmpm"),
    "patients coming back too soon": ("coming back too soon", "v_readmissions"),
    "which doctors get turned down most": ("doctors get turned down", "v_denial_rate_by_provider"),
    "people with ongoing illnesses": ("ongoing illnesses", "v_chronic_members"),
}


def gloss(name):
    p = os.path.join(HERE, "glossaries", f"{name}.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def score(cat, qs):
    return [bool(g & {n.split(".")[-1] for n in cat.select(q, top_k=6).table_names}) for q, g in qs]


def main():
    print(f"embedder: {R._embedder_name()}")
    total_fixed = total_broken = total_miss = 0
    unrepaired = []
    for name, qs in EV.ALL.items():
        cat = R.build(name)
        for p, o in gloss(name).items():
            cat.term(p, o)
        before = score(cat, qs)
        misses = [q for (q, _), ok in zip(qs, before) if not ok]
        added = 0
        for q in misses:
            if q in REPAIR:
                phrase, obj = REPAIR[q]
                cat.term(phrase, obj); added += 1
            else:
                unrepaired.append((name, q))
        after = score(cat, qs)
        fixed = sum(1 for a, b in zip(before, after) if b and not a)
        broken = sum(1 for a, b in zip(before, after) if a and not b)
        total_fixed += fixed; total_broken += broken; total_miss += len(misses)
        print(f"{name:<10} {sum(before):>2}/{len(qs):<3} -> {sum(after):>2}/{len(qs):<3}  "
              f"terms added {added}  fixed {fixed}  broken {broken}")
    print(f"ALL: {total_miss} misses, fixed {total_fixed}, broken {total_broken}")
    for name, q in unrepaired:
        print(f"   (no repair term written) {name}: {q!r}")


if __name__ == "__main__":
    main()
