"""Recipe Workshop — turn raw ingredient text into a real costed dish.

Every corpus recipe already goes through one pipeline: raw ingredient text
-> parsed into grams (urt.py) -> matched to TKPI foods for real nutrition
and cost (tkpi.py) -> assembled into a scored dish (nutrition.py's
RecipeEngine.build). That pipeline doesn't care where the ingredient list
came from. So a dish a school types in by hand, and a dish the Recipe
Author agent proposes from a natural-language request, both end up here —
the same deterministic computation, never a model-stated number. See
racik/orchestrator.py's SYSTEM_PROMPT for the same contract applied to
menu planning; this is the recipe-level version of it.

compute_dish() is the shared entry point both paths call. CustomDishStore
persists what a kitchen has saved, scoped like ratings and pantry
(history.py) — not part of the shared 18k-dish corpus, so it's kept in its
own table rather than racik.db, which is a rebuildable derived artefact.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .config import DATA_DIR
from .nutrition import Dish, RecipeEngine
from .prices import PriceTable
from .tkpi import load_default

CUSTOM_DISH_DB_PATH = DATA_DIR / "history.db"  # shares the file with history.py's tables


@lru_cache(maxsize=1)
def _engine() -> RecipeEngine:
    return RecipeEngine(load_default(), PriceTable.load())


def compute_dish(dish_id: int, name: str, ingredient_lines: list[str],
                 steps: str = "", province: str = "",
                 island: str = "") -> Optional[Dish]:
    """Raw ingredient lines in, a real costed/scored Dish out — or None if
    nothing in the list resolves to a recognisable ingredient, or the mix
    doesn't classify into any tray slot. Both failure modes are the same
    ones any corpus recipe can hit; nothing here is more lenient."""
    raw = "|".join(line.strip() for line in ingredient_lines if line.strip())
    if not raw:
        return None
    return _engine().build(dish_id, name, raw, steps=steps,
                           province=province, island=island,
                           confidence="custom")


@dataclass
class CustomDishStore:
    """Persists school-authored/edited dishes, scoped by (province, stage)
    same as PlanHistory's ratings and pantry — no multi-tenant auth exists
    yet, so this is the same scoping unit already used everywhere else."""

    path: Path = CUSTOM_DISH_DB_PATH

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_dishes (
                scope TEXT NOT NULL,
                dish_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                ingredients_raw TEXT NOT NULL,
                steps TEXT NOT NULL DEFAULT '',
                province TEXT NOT NULL DEFAULT '',
                island TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                PRIMARY KEY (scope, dish_id)
            )
        """)
        self._conn.commit()

    @staticmethod
    def scope_key(province: str, stage: str) -> str:
        return f"{(province or '').strip().lower()}::{stage}"

    def save(self, province: str, stage: str, name: str,
             ingredient_lines: list[str], steps: str = "",
             island: str = "") -> int:
        """Persist a dish and return its (negative) dish_id — negative so
        it can never collide with a real corpus id, which are all
        positive (recipes) or in the 900000s (served components)."""
        scope = self.scope_key(province, stage)
        next_id = self._conn.execute(
            "SELECT COALESCE(MIN(dish_id), 0) - 1 FROM custom_dishes "
            "WHERE scope = ?", (scope,)).fetchone()[0]
        raw = "|".join(line.strip() for line in ingredient_lines if line.strip())
        self._conn.execute(
            "INSERT INTO custom_dishes (scope, dish_id, name, "
            "ingredients_raw, steps, province, island, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (scope, next_id, name, raw, steps, province, island, time.time()))
        self._conn.commit()
        return next_id

    def delete(self, province: str, stage: str, dish_id: int) -> None:
        scope = self.scope_key(province, stage)
        self._conn.execute(
            "DELETE FROM custom_dishes WHERE scope = ? AND dish_id = ?",
            (scope, dish_id))
        self._conn.commit()

    def get(self, province: str, stage: str, dish_id: int) -> Optional[Dish]:
        """One saved dish, recomputed fresh — the single-id counterpart to
        list_dishes, for looking up a custom dish that ended up selected
        into an actual plan (its dish_id shows up in a day's slots same as
        any corpus dish, see api.py's dish() endpoint)."""
        scope = self.scope_key(province, stage)
        row = self._conn.execute(
            "SELECT name, ingredients_raw, steps, province, island FROM "
            "custom_dishes WHERE scope = ? AND dish_id = ?",
            (scope, dish_id)).fetchone()
        if row is None:
            return None
        name, raw, steps, prov, isl = row
        return _engine().build(dish_id, name, raw, steps=steps,
                               province=prov, island=isl, confidence="custom")

    def list_dishes(self, province: str, stage: str) -> list[Dish]:
        """Every saved dish for this scope, recomputed fresh through the
        same pipeline rather than cached — so a price-table update or a
        TKPI fix is reflected immediately, same as it would be for any
        corpus dish on the next database rebuild."""
        scope = self.scope_key(province, stage)
        rows = self._conn.execute(
            "SELECT dish_id, name, ingredients_raw, steps, province, "
            "island FROM custom_dishes WHERE scope = ?", (scope,)).fetchall()
        out = []
        for dish_id, name, raw, steps, prov, isl in rows:
            dish = _engine().build(dish_id, name, raw, steps=steps,
                                   province=prov, island=isl,
                                   confidence="custom")
            if dish is not None:
                out.append(dish)
        return out

    def close(self) -> None:
        self._conn.close()
