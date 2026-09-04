"""Precompute a bank of verified single-day trays for the Render demo.

For each of 5 well-covered regions x 4 AKG stages, solves ~20 diverse
single-day plans (not a full week — a single day is a far smaller, faster
CP-SAT problem) and keeps only the ones that are already fully compliant
(zero relaxed floors, zero budget overrun). The live app can then assemble
a week for any of these regions by picking non-repeating trays from the
bank instantly, with no CP-SAT solve on the request path at all.

This does NOT replace live generation for other regions or edge cases —
those still hit the normal solver. It's a fast, honestly-labeled path for
a curated set of demo-friendly regions.

Writes racik/data/precomputed_trays.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from racik.akg import SCHOOL_STAGES
from racik.config import MBGConfig, SLOTS
from racik.optimizer import MenuOptimizer, PlanRequest, dish_key
from racik.store import RacikStore

REGIONS = [
    ("Jawa Tengah", "jawa"), ("Sumatera Barat", "sumatera"),
    ("Jawa Barat", "jawa"), ("Jawa Timur", "jawa"),
    ("Sumatera Selatan", "sumatera"),
]
STAGES = list(SCHOOL_STAGES)
TARGET_TRAYS = 20
MAX_ATTEMPTS = 60  # generous ceiling in case some seeds collide or fail
# Matches the onboarding form's default — a real budget any typical
# request will meet or exceed, not the bare dataclass default (10,000).
DEMO_CONFIG = MBGConfig(budget_per_portion_idr=14_000.0)


def tray_signature(day) -> tuple:
    dishes = day.dishes
    return tuple(dishes[s].dish_id if dishes[s] else None for s in SLOTS)


def family_of(dish) -> str:
    return dish.main_food_code or dish_key(dish)


def collect_trays(opt: MenuOptimizer, province: str, island: str, stage: str) -> list[dict]:
    seen_signatures: set[tuple] = set()
    exclude_ids: set[int] = set()
    trays: list[dict] = []

    for attempt in range(MAX_ATTEMPTS):
        if len(trays) >= TARGET_TRAYS:
            break
        req = PlanRequest(
            days=1, stage=stage, portions=80, province=province, island=island,
            config=DEMO_CONFIG, exclude_dish_ids=list(exclude_ids),
            max_solve_seconds=5.0, candidates_per_slot=150,
            random_seed=attempt,
        )
        r = opt.solve(req)
        if not r.feasible or r.relaxations or r.budget_overrun_idr > 0:
            continue
        day = r.days[0]
        sig = tray_signature(day)
        if sig in seen_signatures or None in sig:
            continue
        seen_signatures.add(sig)
        trays.append({
            "dish_ids": {s: day.dishes[s].dish_id for s in SLOTS},
            "cost_per_portion_idr": round(day.cost_per_portion_idr, 1),
            "nutrients": {k: round(v, 3) for k, v in day.nutrients.items()},
        })
        # Push the next search away from families just used, so the bank
        # doesn't converge on one "best" tray repeated with minor variation.
        for s in SLOTS:
            if s in ("staple", "buah"):
                continue
            exclude_ids.add(day.dishes[s].dish_id)
        # Cap how much we exclude so the pool doesn't starve near the end.
        if len(exclude_ids) > 40:
            exclude_ids = set(list(exclude_ids)[-40:])

    return trays


def main() -> None:
    store = RacikStore()
    dishes = store.load_dishes()
    opt = MenuOptimizer(dishes)

    bank: dict[str, dict[str, list[dict]]] = {}
    for province, island in REGIONS:
        bank[province] = {}
        for stage in STAGES:
            t0 = time.time()
            trays = collect_trays(opt, province, island, stage)
            dt = time.time() - t0
            print(f"{province}/{stage}: {len(trays)} trays in {dt:.1f}s")
            bank[province][stage] = trays

    out_path = Path(__file__).resolve().parent.parent / "data" / "precomputed_trays.json"
    out_path.write_text(json.dumps({
        "budget_per_portion_idr": DEMO_CONFIG.budget_per_portion_idr,
        "regions": {p: isl for p, isl in REGIONS},
        "trays": bank,
    }, indent=2))
    print(f"\nwrote {out_path}")

    short = [(p, s, len(bank[p][s])) for p, _ in REGIONS for s in STAGES if len(bank[p][s]) < 7]
    if short:
        print("\nWARNING — these (region, stage) pools are too small for a 7-day plan:")
        for p, s, n in short:
            print(f"  {p}/{s}: only {n} trays")
    else:
        print("\nAll pools have enough trays for a full 7-day plan.")


if __name__ == "__main__":
    main()
