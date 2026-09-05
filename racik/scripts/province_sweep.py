"""Plan for every province and report what each one had to give up.

Soft floors mean a solve always returns a menu, which is the right behaviour for
a cook -- "infeasible" helps nobody -- but it moves the question. It is no longer
"does this province work", it is "how much did this province have to relax to
get there", and that is invisible unless something asks.

This runs a plan for every province in the dish index and prints the relaxations
alongside the pool sizes, so a thin region shows up as a list of concessions
rather than as a menu that looks like all the others.

    python scripts/province_sweep.py            # 5 days, every province
    python scripts/province_sweep.py 3 Papua    # one province, 3 days
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from racik.optimizer import MenuOptimizer, PlanRequest       # noqa: E402
from racik.store import RacikStore                           # noqa: E402


def main() -> int:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    only = sys.argv[2] if len(sys.argv) > 2 else None

    store = RacikStore()
    provinces = store.provinces()
    if only:
        provinces = [p for p in provinces if only.lower() in p[0].lower()]

    # MenuOptimizer takes the dishes themselves, not the store (see api.py).
    optimizer = MenuOptimizer(store.load_dishes())

    print("%-26s %6s %8s %9s  %s" % ("PROVINCE", "DISHES", "COST/POR", "ADEQUACY", "RELAXED"))
    print("-" * 96)

    worst: list[tuple[int, str]] = []
    failures: list[tuple[str, str]] = []

    for province, island, dish_count in provinces:
        started = time.time()
        request = PlanRequest(days=days, province=province, island=island, portions=120)
        try:
            plan = optimizer.solve(request)
        except Exception as exc:                      # noqa: BLE001 - report, do not abort
            print("%-26s  solve failed: %s" % (province, exc))
            failures.append((province, str(exc)))
            continue

        # PlanResult.summary() already computes these, and reusing it means the
        # sweep can never quietly disagree with what the API reports.
        summary = plan.summary()
        names = sorted({r.nutrient for r in plan.relaxations})
        per_portion = summary["mean_cost_per_portion_idr"]
        adequacy_txt = "%5.1f%%" % (summary["mean_adequacy"] * 100)
        overrun = summary["budget_overrun_idr"]

        worst.append((len(names), province))
        note = ", ".join(names) if names else "none"
        if overrun > 0:
            note += "  budget +Rp %.0f" % overrun
        print("%-26s %6d %8.0f %9s  %s  (%.0fs)" % (
            province, dish_count, per_portion, adequacy_txt, note,
            time.time() - started))

    print()
    print("%d provinces planned, %d failed" % (len(provinces) - len(failures), len(failures)))
    for province, why in failures:
        print("   FAILED  %-24s %s" % (province, why))

    worst.sort(reverse=True)
    tight = [p for n, p in worst if n]
    if tight:
        print()
        print("Provinces that had to relax something (thinnest first):")
        for count, province in worst:
            if count:
                print("   %-24s %d relaxation(s)" % (province, count))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
