"""Program-level constants and tunables for Racik.

Everything here is *policy*, not physics: values are editable per SPPG / region.
Sources are cited inline so a reviewer can trace every number to a document.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# ---------------------------------------------------------------- paths
PKG_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PKG_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "racik.db"
UI_DIR = PROJECT_DIR / "ui"


# ---------------------------------------------------------------- MBG program
@dataclass(frozen=True)
class MBGConfig:
    """Makan Bergizi Gratis program parameters.

    budget_per_portion_idr
        Rp10,000 is the standing national figure for 2025-2026 (cut from an
        original Rp15,000 target by Presidential decision, 29 Nov 2024). It
        covers ingredients + preparation + distribution.
    ingredient_budget_share
        BGN's per-SPPG allocation splits ~70% raw ingredients / 20% operational
        / 10% incentives (Dadan Hindayana, Feb 2026) -> ~Rp7,000 of the Rp10,000
        is realistically available for raw ingredients. This is a per-kitchen
        allocation, NOT a legislated per-portion line item; treat as a planning
        assumption, editable per region.
    akg_fraction
        One MBG meal is designed to cover ~1/3 of daily AKG (BGN Deputy Head
        Nanik Sudaryati Deyang, Mar 2026).
    fat_energy_ceiling
        Fat capped at 30% of meal energy — standard Indonesian dietary guidance.
    """

    budget_per_portion_idr: float = 10_000.0
    ingredient_budget_share: float = 0.70
    akg_fraction: float = 1.0 / 3.0
    fat_energy_ceiling: float = 0.30
    # Regional cost index: ingredient budget is "at cost tergantung indeks
    # kemahalan daerah". 1.0 = national baseline.
    regional_cost_index: float = 1.0

    @property
    def ingredient_budget_idr(self) -> float:
        """Rupiah available per portion for raw ingredients."""
        return (
            self.budget_per_portion_idr
            * self.ingredient_budget_share
            * self.regional_cost_index
        )


# ---------------------------------------------------------------- Isi Piringku
# Kemenkos "Isi Piringku" (Permenkes 41/2014) tray composition. The MBG tray is
# staple + animal protein + plant protein + vegetable + fruit, with milk where
# budget and cold chain allow.
SLOTS = ("staple", "hewani", "nabati", "sayur", "buah")
SLOT_LABELS_ID = {
    "staple": "Makanan pokok",
    "hewani": "Lauk hewani",
    "nabati": "Lauk nabati",
    "sayur": "Sayur",
    "buah": "Buah",
}
SLOT_LABELS_EN = {
    "staple": "Staple",
    "hewani": "Animal protein",
    "nabati": "Plant protein",
    "sayur": "Vegetable",
    "buah": "Fruit",
}

# Reference served weight per slot, grams of edible food per portion.
# Anchors: "Isi Piringku" reference portions (~150 g nasi, 75 g animal protein
# or 100 g tahu) plus MBG kitchen practice.
REFERENCE_PORTION_G = {
    "staple": 150.0,
    "hewani": 75.0,
    "nabati": 60.0,
    "sayur": 100.0,
    "buah": 100.0,
}

# How many dishes may fill each slot on a single day.
SLOT_CARDINALITY = {
    "staple": (1, 1),
    "hewani": (1, 1),
    "nabati": (1, 1),
    "sayur": (1, 1),
    "buah": (1, 1),
}

# Slots the optimiser may leave empty if budget is binding. Deliberately empty:
# the full MBG tray is nasi + lauk hewani + lauk nabati + sayur + buah, and a
# fruit-less tray is a non-compliant tray, not a cheaper one. Making fruit
# optional simply taught the solver to drop it every day to save ~Rp1,500.
OPTIONAL_SLOTS: tuple[str, ...] = ()

# Slots filled from the standard served components rather than from the recipe
# corpus. An SPPG cooks three items a day; rice and fruit are standing issue,
# plated as-is. Restricting these slots also removes a whole class of
# misclassification: a battered tempe dish is mostly wheat flour by mass and
# would otherwise present itself as a credible "staple".
COMPONENT_ONLY_SLOTS = ("staple", "buah")

MBG = MBGConfig()


# ---------------------------------------------------------------- runtime
# Deployment policy rather than programme policy: how much CPU this process
# actually has, and the solver defaults that follow from it.
#
# CP-SAT spends whatever wall-clock you give it — at the full candidate pool it
# never proves optimality, so it always returns at the time limit. That makes
# the time limit the latency knob and the pool size the *quality per second*
# knob. Measured on one core, five days, SD/Jawa Tengah:
#
#   220 candidates / slot, 12 s  ->  adequacy 0.725, 17 floors relaxed
#    60 candidates / slot,  4 s  ->  adequacy 0.860, 14 floors relaxed
#
# A smaller pool is both faster and better when the CPU is scarce, because the
# solver stops spreading a fixed search budget over dishes it will never pick.

def _cgroup_cpu_quota() -> Optional[float]:
    """Cores this container may use, or None when not constrained by a cgroup.

    `os.cpu_count()` reports the *host's* cores, which on a shared PaaS instance
    is wildly optimistic — asking for 8 CP-SAT workers on a 0.1-vCPU share is
    slower than asking for one. The cgroup files are the only honest answer.
    """
    try:                                            # cgroup v2
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()[:2]
        if quota != "max":
            return int(quota) / int(period)
    except (OSError, ValueError, IndexError):
        pass
    try:                                            # cgroup v1
        quota = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text())
        period = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text())
        if quota > 0 and period > 0:
            return quota / period
    except (OSError, ValueError):
        pass
    return None


def _env(name: str, default, cast: Callable):
    """Read a tunable from the environment, ignoring anything unparseable."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError):
        return default


CPU_BUDGET: float = _env("RACIK_CPU_BUDGET", None, float) or _cgroup_cpu_quota() \
    or float(os.cpu_count() or 1)

# CP-SAT's parallel portfolio needs whole cores; below one, one worker it is.
SOLVER_WORKERS: int = max(1, min(8, int(CPU_BUDGET)))
LOW_CPU: bool = CPU_BUDGET < 2

# Below roughly 50 candidates per slot the variety constraints (no-repeat plus
# the two-per-ingredient-family cap) deadlock and the solve returns INFEASIBLE.
# Measured cliff: 60 solves, 40 does not. Override with care.
DEFAULT_CANDIDATES_PER_SLOT: int = _env(
    "RACIK_CANDIDATES_PER_SLOT", 60 if LOW_CPU else 220, int)
DEFAULT_SOLVE_SECONDS: float = _env(
    "RACIK_SOLVE_SECONDS", 4.0 if LOW_CPU else 12.0, float)
