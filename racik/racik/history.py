"""Cross-request plan memory: what was served, and whether kids liked it.

The optimizer's own variety constraints (`no_repeat_slots`, `repeat_window`)
only cover the days inside *one* solve. Nothing stopped two separate calls
with identical parameters (same province, same stage, same budget — exactly
what a kitchen re-running its weekly plan looks like) from returning the same
menu, since CP-SAT is deterministic and `random_seed` only reorders search,
it does not change the objective's optimum.

The first version of this fix treated every recently-served dish the same:
serve it, and it's avoided for two weeks, full stop. That's wrong for a
school menu — a dish the kids rated well *should* be able to come back
sooner than one they rated poorly. So the actual signal here is two things
combined, per dish:

- how recently it was served (decays linearly to zero over the window —
  a dish from three weeks ago is fair game again regardless of rating)
- its running average rating, if the kitchen has rated it (1-5 stars,
  updated as an incremental mean — one bad day doesn't crater a dish that's
  usually rated well, but the average does move toward new ratings)

Those combine into one continuous weight per dish (`recency_weights`), which
the optimizer applies as a soft penalty — nudged, not forbidden, so a
genuinely better dish can still win, and a well-liked one can recur sooner
than an unrated or poorly-rated one.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .config import DATA_DIR

HISTORY_DB_PATH = DATA_DIR / "history.db"

# How far back a served dish still counts toward the recency weight at all.
DEFAULT_WINDOW_SECONDS = 14 * 24 * 3600   # 14 days
DEFAULT_PLAN_LIMIT = 3                     # or the last N recorded plans, whichever is fewer

# Rating -> multiplier on the recency weight. 3 stars (or unrated) is neutral;
# below that the dish is pushed away harder than the default, above that the
# avoidance eases off — but even 5 stars keeps a small residual weight, so a
# favourite doesn't win literally every single day either.
RATING_MULTIPLIER = {1: 1.5, 2: 1.2, 3: 1.0, 4: 0.5, 5: 0.15}
UNRATED_MULTIPLIER = 1.0


@dataclass
class PlanHistory:
    """Records what a (province, stage) scope was served, and how it rated."""

    path: Path = HISTORY_DB_PATH

    def __post_init__(self) -> None:
        # FastAPI runs sync endpoints in a thread pool, so this single
        # connection (check_same_thread=False, deliberately shared) can be
        # entered by two requests at once — e.g. one day's five dishes each
        # firing a rating/reason write in parallel, as the UI does on a day
        # reject. Concurrent calls into the same sqlite3.Connection with no
        # serialization intermittently raised "bad parameter or other API
        # misuse" under exactly that burst. A single lock around every
        # method serializes access; SQLite itself is fast enough per-call
        # that this isn't a real throughput concern for this workload.
        self._lock = threading.RLock()  # RLock: recency_weights() calls rating() while already holding it
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS served (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL,
                plan_id INTEGER NOT NULL,
                dish_id INTEGER NOT NULL,
                served_at REAL NOT NULL
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_served_scope ON served(scope, served_at)")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                scope TEXT NOT NULL,
                dish_id INTEGER NOT NULL,
                mean_rating REAL NOT NULL,
                n INTEGER NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (scope, dish_id)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS rating_reasons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL,
                dish_id INTEGER NOT NULL,
                dish_name TEXT NOT NULL,
                reason TEXT NOT NULL,
                rating REAL NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS pantry (
                scope TEXT NOT NULL,
                tkpi_code TEXT NOT NULL,
                ingredient_name TEXT NOT NULL,
                remaining_g REAL NOT NULL,
                usable_within_days INTEGER,
                updated_at REAL NOT NULL,
                PRIMARY KEY (scope, tkpi_code)
            )
        """)
        self._conn.commit()

    @staticmethod
    def scope_key(province: str, stage: str) -> str:
        return f"{(province or '').strip().lower()}::{stage}"

    # ------------------------------------------------------------ serving history

    def record(self, province: str, stage: str, dish_ids: Iterable[int]) -> None:
        scope = self.scope_key(province, stage)
        now = time.time()
        rows_ids = [int(d) for d in dish_ids if d is not None]
        if not rows_ids:
            return
        with self._lock:
            cur = self._conn.execute(
                "SELECT COALESCE(MAX(plan_id), 0) + 1 FROM served WHERE scope = ?",
                (scope,))
            plan_id = cur.fetchone()[0]
            rows = [(scope, plan_id, d, now) for d in rows_ids]
            self._conn.executemany(
                "INSERT INTO served (scope, plan_id, dish_id, served_at) "
                "VALUES (?, ?, ?, ?)", rows)
            self._conn.commit()
            # Housekeeping: keep only the last 20 plans per scope so the
            # table never grows unbounded across a long-running deployment.
            self._conn.execute(
                "DELETE FROM served WHERE scope = ? AND plan_id <= "
                "(SELECT COALESCE(MAX(plan_id), 0) - 20 FROM served WHERE scope = ?)",
                (scope, scope))
            self._conn.commit()

    # ------------------------------------------------------------ ratings

    def rate(self, province: str, stage: str, dish_id: int, rating: float) -> float:
        """Fold one new 1-5 rating into the dish's running average. Returns
        the updated mean. An incremental mean, not an overwrite — a dish
        that's usually loved doesn't get wrecked by one off day, but the
        average genuinely moves toward whatever was just rated."""
        rating = max(1.0, min(5.0, float(rating)))
        scope = self.scope_key(province, stage)
        with self._lock:
            row = self._conn.execute(
                "SELECT mean_rating, n FROM ratings WHERE scope = ? AND dish_id = ?",
                (scope, dish_id)).fetchone()
            if row is None:
                mean, n = rating, 1
            else:
                old_mean, old_n = row
                n = old_n + 1
                mean = (old_mean * old_n + rating) / n
            self._conn.execute(
                "INSERT INTO ratings (scope, dish_id, mean_rating, n, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(scope, dish_id) DO UPDATE SET "
                "mean_rating = excluded.mean_rating, n = excluded.n, "
                "updated_at = excluded.updated_at",
                (scope, dish_id, mean, n, time.time()))
            self._conn.commit()
            return mean

    def log_reason(self, province: str, stage: str, dish_id: int,
                   dish_name: str, reason: str, rating: float) -> None:
        """Attach a *why* to a rating that already happened (mirroring main
        branch's reject-reason chips — too expensive, not regional,
        nutrition, kids didn't like it, other). Deliberately separate from
        rate(): calling this doesn't touch the running mean, so a chip
        picked after the fact can't double-count the same rating event."""
        scope = self.scope_key(province, stage)
        with self._lock:
            self._conn.execute(
                "INSERT INTO rating_reasons (scope, dish_id, dish_name, "
                "reason, rating, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (scope, dish_id, dish_name, reason.strip(), rating, time.time()))
            self._conn.commit()

    def rating(self, province: str, stage: str, dish_id: int) -> Optional[float]:
        scope = self.scope_key(province, stage)
        with self._lock:
            row = self._conn.execute(
                "SELECT mean_rating FROM ratings WHERE scope = ? AND dish_id = ?",
                (scope, dish_id)).fetchone()
            return row[0] if row else None

    # ------------------------------------------------------------ the combined signal

    def recency_weights(self, province: str, stage: str,
                        window_seconds: float = DEFAULT_WINDOW_SECONDS,
                        plan_limit: int = DEFAULT_PLAN_LIMIT) -> dict[int, float]:
        """A continuous avoidance weight per recently-served dish, 0-1.5+,
        for the optimizer to apply as a soft penalty (0 = no avoidance).

        weight = time_decay(days since it was last served) x rating_multiplier

        time_decay is 1.0 the day it was served, fading linearly to 0 at the
        window edge. rating_multiplier eases the avoidance off for a dish
        rated well and strengthens it for one rated poorly — see
        RATING_MULTIPLIER. A dish served more than once recently uses its
        *most recent* serving for the decay (the more relevant one)."""
        scope = self.scope_key(province, stage)
        cutoff = time.time() - window_seconds
        with self._lock:
            rows = self._conn.execute(
                "SELECT dish_id, plan_id, MAX(served_at) served_at FROM served "
                "WHERE scope = ? AND served_at >= ? "
                "GROUP BY dish_id, plan_id",
                (scope, cutoff)).fetchall()
        if not rows:
            return {}
        recent_plan_ids = sorted({r[1] for r in rows}, reverse=True)[:plan_limit]
        last_served: dict[int, float] = {}
        for dish_id, plan_id, served_at in rows:
            if plan_id not in recent_plan_ids:
                continue
            last_served[dish_id] = max(last_served.get(dish_id, 0.0), served_at)

        now = time.time()
        weights: dict[int, float] = {}
        for dish_id, served_at in last_served.items():
            days_ago = (now - served_at) / 86400
            time_decay = max(0.0, 1.0 - days_ago / (window_seconds / 86400))
            if time_decay <= 0:
                continue
            r = self.rating(province, stage, dish_id)
            mult = (RATING_MULTIPLIER[round(min(5, max(1, r)))]
                    if r is not None else UNRATED_MULTIPLIER)
            weights[dish_id] = time_decay * mult
        return weights

    # ------------------------------------------------------------ pantry

    def report_leftover(self, province: str, stage: str, tkpi_code: str,
                        ingredient_name: str, remaining_g: float,
                        usable_within_days: Optional[int] = None) -> None:
        """Record what's currently left over for this scope. An overwrite,
        not an accumulation — a kitchen reporting "we have 2kg chicken now"
        is stating a fresh snapshot, not adding to a running ledger no one
        is tracking purchases-minus-usage for yet. remaining_g <= 0 clears
        the item, same as calling clear_pantry_item."""
        scope = self.scope_key(province, stage)
        if remaining_g <= 0:
            self.clear_pantry_item(province, stage, tkpi_code)
            return
        with self._lock:
            self._conn.execute(
                "INSERT INTO pantry (scope, tkpi_code, ingredient_name, "
                "remaining_g, usable_within_days, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(scope, tkpi_code) DO UPDATE SET "
                "ingredient_name = excluded.ingredient_name, "
                "remaining_g = excluded.remaining_g, "
                "usable_within_days = excluded.usable_within_days, "
                "updated_at = excluded.updated_at",
                (scope, tkpi_code, ingredient_name, remaining_g,
                 usable_within_days, time.time()))
            self._conn.commit()

    def clear_pantry_item(self, province: str, stage: str, tkpi_code: str) -> None:
        scope = self.scope_key(province, stage)
        with self._lock:
            self._conn.execute(
                "DELETE FROM pantry WHERE scope = ? AND tkpi_code = ?",
                (scope, tkpi_code))
            self._conn.commit()

    def pantry_items(self, province: str, stage: str) -> list[dict]:
        """Current leftover stock for this scope — what the setup screen
        shows before generating a plan, and what optimizer.py's pantry
        bonus reads from (via the tkpi_code + usable_within_days pair)."""
        scope = self.scope_key(province, stage)
        with self._lock:
            rows = self._conn.execute(
                "SELECT tkpi_code, ingredient_name, remaining_g, "
                "usable_within_days, updated_at FROM pantry WHERE scope = ? "
                "ORDER BY updated_at DESC",
                (scope,)).fetchall()
        return [
            {"tkpi_code": r[0], "ingredient_name": r[1], "remaining_g": r[2],
             "usable_within_days": r[3], "updated_at": r[4]}
            for r in rows
        ]

    def feedback_log(self, province: str, stage: str, limit: int = 50) -> list[dict]:
        """Every reason logged with a rating for this scope, most recent
        first — the read side of rating()'s optional reason, mirroring the
        feedback list main branch's Settings tab showed (never wired to
        anything there either; this one at least feeds the score)."""
        scope = self.scope_key(province, stage)
        with self._lock:
            rows = self._conn.execute(
                "SELECT dish_id, dish_name, reason, rating, created_at "
                "FROM rating_reasons WHERE scope = ? "
                "ORDER BY created_at DESC LIMIT ?", (scope, limit)).fetchall()
        return [
            {"dish_id": r[0], "dish_name": r[1], "reason": r[2],
             "rating": r[3], "created_at": r[4]}
            for r in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
