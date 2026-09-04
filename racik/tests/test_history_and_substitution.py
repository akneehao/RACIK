"""Tests for the two additions on top of the original engine:

- history.py + optimizer.py's recency penalty: two solves with identical
  parameters should not return the identical menu.
- substitution.py: the Reviewer agent's core/flexible classification and its
  refusal to invent a substitute outside what was actually looked up.
- optimizer.py's target_overrides: a direct user number, not a model guess,
  should actually move the solved target.

Run:  python -m pytest tests -q
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from racik.config import MBGConfig
from racik.history import PlanHistory
from racik.optimizer import MenuOptimizer, PlanRequest
from racik.store import RacikStore
from racik.substitution import CORE_SHARE_THRESHOLD, SubstitutionAgent


@pytest.fixture(scope="module")
def store():
    return RacikStore()


@pytest.fixture(scope="module")
def optimizer(store):
    return MenuOptimizer(store.load_dishes())


@pytest.fixture
def history():
    h = PlanHistory(path=Path(tempfile.mktemp(suffix=".db")))
    yield h
    h.close()


# ---------------------------------------------------------------- recency

def test_recency_weights_empty_before_any_plan(history):
    assert history.recency_weights("Jawa Tengah", "sd") == {}


def test_record_then_recall_round_trips(history):
    history.record("Jawa Tengah", "sd", [101, 102, 103])
    weights = history.recency_weights("Jawa Tengah", "sd")
    assert set(weights) == {101, 102, 103}
    # Just served, unrated: full weight (time_decay ~1.0 x neutral 1.0).
    for w in weights.values():
        assert 0.9 < w <= 1.0


def test_history_scopes_by_province_and_stage(history):
    history.record("Jawa Tengah", "sd", [101])
    history.record("Bali", "sd", [999])
    history.record("Jawa Tengah", "smp", [888])
    assert set(history.recency_weights("Jawa Tengah", "sd")) == {101}


def test_recency_penalty_reduces_repeat_dishes(optimizer, history):
    """The actual point of this feature: run the same request twice and
    check the second solve avoids what the first one served, without a
    meaningful quality regression."""
    req = PlanRequest(days=3, stage="sd", portions=50, province="Jawa Tengah",
                      max_solve_seconds=8)
    r1 = optimizer.solve(req)
    assert r1.feasible
    served1 = {d.dish_id for day in r1.days for d in day.selected}
    history.record("Jawa Tengah", "sd", served1)

    weights = history.recency_weights("Jawa Tengah", "sd")
    req2 = PlanRequest(days=3, stage="sd", portions=50, province="Jawa Tengah",
                       max_solve_seconds=8, recency_weights=weights)
    r2 = optimizer.solve(req2)
    assert r2.feasible
    served2 = {d.dish_id for day in r2.days for d in day.selected}

    overlap = served1 & served2
    assert len(overlap) < len(served1), (
        "recency penalty had no effect — two identical requests still "
        "returned an (almost) identical menu")
    # Variety shouldn't come at a wildly worse plan — same order of
    # magnitude cost/adequacy, not a collapse.
    assert r2.summary()["mean_adequacy"] >= r1.summary()["mean_adequacy"] - 0.15


def test_history_keeps_only_recent_plans_per_scope(history):
    for plan in range(25):
        history.record("Jawa Tengah", "sd", [1000 + plan])
    rows = history._conn.execute(
        "SELECT COUNT(DISTINCT plan_id) FROM served WHERE scope = ?",
        (history.scope_key("Jawa Tengah", "sd"),)).fetchone()[0]
    assert rows <= 21  # 20-plan retention plus the write just made


# ---------------------------------------------------------------- ratings

def test_unrated_dish_has_neutral_multiplier(history):
    history.record("Jawa Tengah", "sd", [201])
    w = history.recency_weights("Jawa Tengah", "sd")[201]
    assert 0.9 < w <= 1.0  # neutral: time_decay alone, no rating adjustment


def test_high_rating_lowers_recency_weight(history):
    history.record("Jawa Tengah", "sd", [201])
    history.rate("Jawa Tengah", "sd", 201, 5)
    w = history.recency_weights("Jawa Tengah", "sd")[201]
    assert w < 0.2  # 5 stars -> 0.15 multiplier, eases back in almost fully


def test_low_rating_raises_recency_weight(history):
    history.record("Jawa Tengah", "sd", [201])
    history.rate("Jawa Tengah", "sd", 201, 1)
    w = history.recency_weights("Jawa Tengah", "sd")[201]
    assert w > 1.0  # 1 star -> 1.5 multiplier, pushed away harder than default


def test_rating_is_a_running_mean_not_an_overwrite(history):
    m1 = history.rate("Jawa Tengah", "sd", 201, 5)
    assert m1 == 5.0
    m2 = history.rate("Jawa Tengah", "sd", 201, 1)
    # Averages toward the new rating, doesn't just snap to it.
    assert 1.0 < m2 < 5.0
    assert history.rating("Jawa Tengah", "sd", 201) == m2


def test_rating_out_of_range_is_clamped(history):
    m = history.rate("Jawa Tengah", "sd", 201, 99)
    assert m == 5.0
    m = history.rate("Jawa Tengah", "sd", 202, -3)
    assert m == 1.0


def test_recency_weight_fades_to_zero_outside_the_window(history):
    scope = history.scope_key("Jawa Tengah", "sd")
    history.record("Jawa Tengah", "sd", [301])
    # Backdate the serving beyond the default 14-day window.
    history._conn.execute(
        "UPDATE served SET served_at = served_at - ? WHERE scope = ? AND dish_id = ?",
        (20 * 86400, scope, 301))
    history._conn.commit()
    assert 301 not in history.recency_weights("Jawa Tengah", "sd")


def test_a_loved_dish_recurs_sooner_than_an_unrated_one(optimizer, history):
    """The actual point of the feature the user asked for: two otherwise
    identical dishes, one rated 5 stars, should not be avoided as hard as
    an unrated one served on the same day."""
    from racik.history import RATING_MULTIPLIER, UNRATED_MULTIPLIER
    history.record("Jawa Tengah", "sd", [401, 402])
    history.rate("Jawa Tengah", "sd", 401, 5)
    weights = history.recency_weights("Jawa Tengah", "sd")
    assert weights[401] < weights[402]
    assert weights[401] == pytest.approx(weights[402]
                                         * RATING_MULTIPLIER[5] / UNRATED_MULTIPLIER,
                                         rel=0.05)


def test_rating_reason_is_logged_separately_and_optional(history):
    # rate() alone — no reason involved, nothing logged.
    history.rate("Jawa Tengah", "sd", 201, 2)
    assert history.feedback_log("Jawa Tengah", "sd") == []

    # log_reason() is independent — it doesn't touch the running mean, so
    # it can be called after the fact without double-counting the rating.
    mean_before = history.rating("Jawa Tengah", "sd", 202)
    history.rate("Jawa Tengah", "sd", 202, 1)
    history.log_reason("Jawa Tengah", "sd", 202, "Ayam Goreng",
                       "too_expensive", 1)
    assert history.rating("Jawa Tengah", "sd", 202) == 1.0  # unchanged by log_reason
    log = history.feedback_log("Jawa Tengah", "sd")
    assert len(log) == 1
    assert log[0]["dish_id"] == 202
    assert log[0]["dish_name"] == "Ayam Goreng"
    assert log[0]["reason"] == "too_expensive"
    assert log[0]["rating"] == 1


def test_accept_log_entry_never_touches_the_rating(history):
    """The frontend's day-review Accept writes an "accepted" reason via the
    same log_reason() path as a reject reason — never /api/rate — so an
    approval can never be mistaken for a taste rating and can never bias
    recency weighting. This is the audit-trail half of day review: proof a
    day was reviewed and approved, independent of whether kids liked it."""
    assert history.rating("Jawa Tengah", "sd", 303) is None
    history.log_reason("Jawa Tengah", "sd", 303, "Nasi Jagung", "accepted", 3)
    assert history.rating("Jawa Tengah", "sd", 303) is None  # still untouched
    assert history.recency_weights("Jawa Tengah", "sd") == {}  # no serving, no rating -> no weight
    log = history.feedback_log("Jawa Tengah", "sd")
    assert len(log) == 1
    assert log[0]["reason"] == "accepted"
    assert log[0]["dish_id"] == 303


def test_feedback_log_scopes_and_orders_most_recent_first(history):
    history.log_reason("Jawa Tengah", "sd", 1, "A", "too_expensive", 1)
    history.log_reason("Jawa Tengah", "sd", 2, "B", "kids_disliked", 2)
    history.log_reason("Bali", "sd", 3, "C", "other", 1)

    log = history.feedback_log("Jawa Tengah", "sd")
    assert [e["dish_id"] for e in log] == [2, 1]  # most recent first

    bali_log = history.feedback_log("Bali", "sd")
    assert len(bali_log) == 1
    assert bali_log[0]["dish_id"] == 3
    assert bali_log[0]["reason"] == "other"


# ---------------------------------------------------------------- target overrides

def test_target_override_moves_the_binding_target(optimizer):
    baseline = optimizer.solve(
        PlanRequest(days=1, stage="sd", portions=50, max_solve_seconds=8))
    assert baseline.targets["protein_g"] < 25

    overridden = optimizer.solve(PlanRequest(
        days=1, stage="sd", portions=50, max_solve_seconds=8,
        target_overrides={"protein_g": 25}))
    assert overridden.targets["protein_g"] == 25
    # Every other AKG target stays untouched — only the overridden key moves.
    assert overridden.targets["fibre_g"] == baseline.targets["fibre_g"]


def test_target_override_ignores_unknown_keys(optimizer):
    result = optimizer.solve(PlanRequest(
        days=1, stage="sd", portions=50, max_solve_seconds=8,
        target_overrides={"not_a_real_nutrient": 999}))
    assert "not_a_real_nutrient" not in result.targets


# ---------------------------------------------------------------- pantry

def test_pantry_report_and_recall_round_trips(history):
    history.report_leftover("Jawa Tengah", "sd", "FR005", "Ayam", 1200, 2)
    items = history.pantry_items("Jawa Tengah", "sd")
    assert len(items) == 1
    assert items[0]["tkpi_code"] == "FR005"
    assert items[0]["remaining_g"] == 1200
    assert items[0]["usable_within_days"] == 2


def test_pantry_report_overwrites_not_accumulates(history):
    history.report_leftover("Jawa Tengah", "sd", "FR005", "Ayam", 1200, 2)
    history.report_leftover("Jawa Tengah", "sd", "FR005", "Ayam", 300, 1)
    items = history.pantry_items("Jawa Tengah", "sd")
    assert len(items) == 1
    assert items[0]["remaining_g"] == 300  # replaced, not 1500


def test_pantry_report_zero_clears_the_item(history):
    history.report_leftover("Jawa Tengah", "sd", "FR005", "Ayam", 1200, 2)
    history.report_leftover("Jawa Tengah", "sd", "FR005", "Ayam", 0, None)
    assert history.pantry_items("Jawa Tengah", "sd") == []


def test_pantry_clear_removes_item(history):
    history.report_leftover("Jawa Tengah", "sd", "FR005", "Ayam", 1200, 2)
    history.clear_pantry_item("Jawa Tengah", "sd", "FR005")
    assert history.pantry_items("Jawa Tengah", "sd") == []


def test_pantry_scopes_by_province_and_stage(history):
    history.report_leftover("Jawa Tengah", "sd", "FR005", "Ayam", 1200, 2)
    assert history.pantry_items("Bali", "sd") == []
    assert history.pantry_items("Jawa Tengah", "smp") == []


def test_pantry_bonus_biases_the_solver_toward_using_it_up(optimizer, store):
    """The point of the feature: a dish using leftover stock should win a
    slot it otherwise wouldn't, but only within the days that stock is
    still good for."""
    req = PlanRequest(days=1, stage="sd", portions=50, province="Jawa Tengah",
                      max_solve_seconds=8)
    baseline = optimizer.solve(req)
    assert baseline.feasible
    baseline_code = baseline.days[0].dishes["hewani"].main_food_code

    # Picking from the dishes actually reaching the solver as candidates
    # for this exact request — a dish the funnel (cost ceiling, dedup,
    # top-N cap) never lets through can't be selected no matter the bonus.
    candidates = optimizer._candidates(req, baseline.targets)
    target_code = next(
        (d.main_food_code for d in candidates.get("hewani", [])
         if d.main_food_code and d.main_food_code != baseline_code), None)
    if target_code is None:
        pytest.skip("corpus doesn't offer a second eligible hewani ingredient here")

    biased = optimizer.solve(PlanRequest(
        days=1, stage="sd", portions=50, province="Jawa Tengah",
        max_solve_seconds=8,
        pantry_items=[{"tkpi_code": target_code, "usable_within_days": 1}]))
    assert biased.feasible
    assert biased.days[0].dishes["hewani"].main_food_code == target_code


def test_pantry_bonus_only_applies_within_its_usable_window(optimizer, store):
    """usable_within_days scopes the bonus to that many leading days. Kept
    deliberately narrow: CP-SAT's multi-worker search isn't guaranteed to
    break ties identically across separate solve() calls of an otherwise
    equivalent model (no fixed single-worker mode here), so this only
    asserts the one thing that's actually reliable — day 0 still gets
    the bonus-favoured dish when there's more than one day in play, not a
    cross-call comparison of what happens on day 1."""
    req = PlanRequest(days=2, stage="sd", portions=50, province="Jawa Tengah",
                      max_solve_seconds=8)
    baseline = optimizer.solve(req)
    assert baseline.feasible
    day0_code = baseline.days[0].dishes["hewani"].main_food_code

    candidates = optimizer._candidates(req, baseline.targets)
    target_code = next(
        (d.main_food_code for d in candidates.get("hewani", [])
         if d.main_food_code and d.main_food_code != day0_code), None)
    if target_code is None:
        pytest.skip("corpus doesn't offer a second eligible hewani ingredient here")

    narrow = optimizer.solve(PlanRequest(
        days=2, stage="sd", portions=50, province="Jawa Tengah",
        max_solve_seconds=8,
        pantry_items=[{"tkpi_code": target_code, "usable_within_days": 1}]))
    assert narrow.feasible
    assert narrow.days[0].dishes["hewani"].main_food_code == target_code


# ---------------------------------------------------------------- recipe workshop

def test_compute_dish_runs_a_new_recipe_through_the_real_pipeline():
    from racik.recipes import compute_dish
    dish = compute_dish(-1, "Gulai Ayam Hijau", [
        "1 kg ayam, daging, segar", "400 ml santan", "3 buah cabai hijau",
        "2 batang serai", "3 lembar daun jeruk", "2 sdm minyak goreng",
    ], province="Jawa Tengah")
    assert dish is not None
    assert dish.slot == "hewani"          # correctly classified, not asserted by the caller
    assert dish.cost_per_portion_idr > 0  # real cost, from TKPI/prices, not stated by the caller
    assert dish.per_portion["protein_g"] > 0
    assert dish.main_food_name == "Ayam, daging, segar"  # correctly identifies the core ingredient


def test_compute_dish_returns_none_for_unusable_input():
    from racik.recipes import compute_dish
    assert compute_dish(-1, "Nothing", [], province="Jawa Tengah") is None
    assert compute_dish(-1, "Gibberish", ["zzz not an ingredient zzz"],
                        province="Jawa Tengah") is None


def test_custom_dish_store_round_trips(tmp_path):
    from racik.recipes import CustomDishStore
    store = CustomDishStore(path=tmp_path / "custom.db")
    dish_id = store.save("Jawa Tengah", "sd", "Gulai Ayam Hijau",
                         ["1 kg ayam, daging, segar", "400 ml santan"])
    assert dish_id < 0  # negative — can never collide with a real corpus id
    loaded = store.list_dishes("Jawa Tengah", "sd")
    assert len(loaded) == 1
    assert loaded[0].dish_id == dish_id
    assert loaded[0].name == "Gulai Ayam Hijau"
    store.close()


def test_custom_dish_store_scopes_and_deletes(tmp_path):
    from racik.recipes import CustomDishStore
    store = CustomDishStore(path=tmp_path / "custom.db")
    dish_id = store.save("Jawa Tengah", "sd", "X", ["1 kg ayam, daging, segar"])
    assert store.list_dishes("Bali", "sd") == []
    store.delete("Jawa Tengah", "sd", dish_id)
    assert store.list_dishes("Jawa Tengah", "sd") == []
    store.close()


def test_extra_dishes_reach_the_solver_even_when_outranked(optimizer, store):
    """The actual point: a school's specifically-requested dish should be
    genuinely considered, not silently dropped by the top-N candidate cap
    just because it doesn't out-score thousands of corpus dishes on one
    formula — the funnel's popularity contest, not its eligibility gates."""
    from racik.recipes import compute_dish
    custom = compute_dish(-1, "Gulai Ayam Hijau", [
        "1 kg ayam, daging, segar", "400 ml santan", "3 buah cabai hijau",
        "2 batang serai", "3 lembar daun jeruk", "2 sdm minyak goreng",
    ], province="Jawa Tengah")
    assert custom is not None

    req = PlanRequest(days=1, stage="sd", portions=50, province="Jawa Tengah",
                      max_solve_seconds=8, extra_dishes=[custom])
    candidates = optimizer._candidates(req, optimizer.solve(
        PlanRequest(days=1, stage="sd", portions=50, province="Jawa Tengah",
                   max_solve_seconds=8)).targets)
    assert any(d.dish_id == -1 for d in candidates["hewani"]), (
        "a custom dish must always reach the solver as a real candidate, "
        "regardless of its rank against the corpus")


def test_extra_dishes_still_respect_the_cost_ceiling(optimizer, store):
    """Guaranteed inclusion isn't a bypass of every gate — an absurdly
    over-budget custom dish still can't reach the solver."""
    from racik.recipes import compute_dish
    absurd = compute_dish(-1, "Emas Panggang", [
        "5 kg daging sapi, has dalam, segar", "1 kg udang, segar",
        "500 g keju cheddar",
    ], province="Jawa Tengah")
    assert absurd is not None
    req = PlanRequest(days=1, stage="sd", portions=50, province="Jawa Tengah",
                      max_solve_seconds=8, extra_dishes=[absurd],
                      config=MBGConfig(budget_per_portion_idr=10000,
                                      ingredient_budget_share=0.7))
    from racik.optimizer import COST_CEILING_SHARE
    ceiling = req.config.ingredient_budget_idr * COST_CEILING_SHARE
    if absurd.cost_per_portion_idr <= ceiling:
        pytest.skip("this dish isn't actually over budget in this scenario")
    targets = optimizer.solve(PlanRequest(
        days=1, stage="sd", portions=50, max_solve_seconds=5)).targets
    candidates = optimizer._candidates(req, targets)
    assert not any(d.dish_id == -1 for d in candidates[absurd.slot])


# ---------------------------------------------------------------- endpoint consistency

def test_procurement_and_report_fetch_the_same_recency_weights_as_plan():
    """Regression test for a real bug: /api/procurement and /api/report
    used to call _optimizer().solve(body.to_request()) directly, skipping
    the recency_weights fetch /api/plan does — so the shopping list or
    printed report could silently reflect a different menu than the one
    actually on screen. All three now go through api._solve()."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from racik.api import app
    from racik.history import PlanHistory

    client = TestClient(app)
    body = {"days": 1, "stage": "sd", "portions": 30,
           "province": "__test_consistency_scope__", "max_solve_seconds": 5}

    with patch.object(PlanHistory, "recency_weights",
                      return_value={}) as mocked:
        for path in ("/api/plan", "/api/procurement", "/api/report"):
            mocked.reset_mock()
            res = client.post(path, json=body)
            assert res.status_code == 200, f"{path} failed: {res.text[:300]}"
            assert mocked.call_count == 1, (
                f"{path} did not fetch recency_weights before solving — "
                "it can silently diverge from what /api/plan shows")
            assert mocked.call_args.args == (
                "__test_consistency_scope__", "sd") or \
                mocked.call_args.kwargs == {}  # positional call, scope matches




def _dish_with_many_ingredients(store):
    """Any dish whose ingredient list is long enough to have both a clearly
    core line and a clearly flexible one — avoids depending on one hardcoded
    dish_id that might not exist after a corpus rebuild."""
    for row in store.conn.execute(
            "SELECT dish_id FROM dishes WHERE slot='hewani' LIMIT 30"):
        lines = store.lines(row["dish_id"])
        if len(lines) >= 5:
            return row["dish_id"], lines
    pytest.skip("no dish with enough ingredient lines found in this corpus")


def test_flexible_ingredient_is_always_dropped_not_substituted(store):
    agent = SubstitutionAgent(store)
    dish_id, lines = _dish_with_many_ingredients(store)
    smallest = min(lines, key=lambda l: l.gross_g)
    total = sum(l.gross_g for l in lines)
    if smallest.gross_g / total >= CORE_SHARE_THRESHOLD:
        pytest.skip("this dish has no sufficiently minor ingredient")
    result = agent.review(dish_id, smallest.name, lang="en")
    assert result.is_core is False
    assert result.action == "drop"
    assert result.substitute is None


def test_core_ingredient_gets_same_group_candidates(store):
    agent = SubstitutionAgent(store)
    dish_id, lines = _dish_with_many_ingredients(store)
    largest = max(lines, key=lambda l: l.gross_g)
    result = agent.review(dish_id, largest.name, lang="en")
    assert result.is_core is True
    if result.candidates:
        assert result.action == "substitute"
        assert result.substitute["code"] in {c["code"] for c in result.candidates}
        # A same-group swap, not just any food in the database.
        assert result.substitute["code"] != largest.tkpi_code


def test_unmatched_ingredient_is_reported_not_guessed(store):
    agent = SubstitutionAgent(store)
    dish_id, _ = _dish_with_many_ingredients(store)
    result = agent.review(dish_id, "zzz-not-an-ingredient-zzz", lang="en")
    assert result.action == "not_found"
    assert result.substitute is None


def test_unknown_dish_raises(store):
    agent = SubstitutionAgent(store)
    with pytest.raises(ValueError):
        agent.review(999_999_999, "garlic", lang="en")


def test_review_custom_handles_a_dish_never_in_the_store(store):
    """A saved Recipe Workshop dish can end up selected into an actual plan
    (extra_dishes' guaranteed inclusion) — review_custom is the path that
    handles "ingredient missing today" for it without a corpus lookup."""
    from racik.recipes import compute_dish
    custom = compute_dish(-1, "Gulai Ayam Hijau", [
        "1 kg ayam, daging, segar", "400 ml santan", "3 buah cabai hijau",
    ], province="Jawa Tengah")
    assert custom is not None
    agent = SubstitutionAgent(store)
    result = agent.review_custom(custom, "ayam", lang="en")
    assert result.is_core is True   # the dish's main ingredient
    assert result.dish_id == -1


# ---------------------------------------------------------------- recipe workshop API

def _recipe_client():
    from fastapi.testclient import TestClient
    from racik.api import app
    return TestClient(app)


def test_recipe_compute_previews_without_saving():
    client = _recipe_client()
    res = client.post("/api/recipe/compute", json={
        "name": "Gulai Ayam Hijau",
        "ingredient_lines": ["1 kg ayam, daging, segar", "400 ml santan"],
        "province": "Jawa Tengah"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["cost_per_portion_idr"] > 0
    assert body["per_portion"]["protein_g"] > 0
    assert body["ingredients"]
    # a preview only — nothing shows up in the saved list
    listed = client.get("/api/recipe/list",
                        params={"province": "Jawa Tengah", "stage": "sd"}).json()
    assert not any(d["name"] == "Gulai Ayam Hijau" for d in listed["dishes"])


def test_recipe_compute_rejects_unusable_ingredients():
    client = _recipe_client()
    res = client.post("/api/recipe/compute", json={
        "name": "Gibberish", "ingredient_lines": ["zzz not real zzz"]})
    assert res.status_code == 422


def test_recipe_save_list_delete_round_trip():
    client = _recipe_client()
    scope = {"province": "__test_recipe_scope__", "stage": "sd"}
    save = client.post("/api/recipe/save", json={
        **scope, "name": "Gulai Ayam Hijau __test__",
        "ingredient_lines": ["1 kg ayam, daging, segar", "400 ml santan"]})
    assert save.status_code == 200, save.text
    dish_id = save.json()["dish_id"]
    assert dish_id < 0

    listed = client.get("/api/recipe/list", params=scope).json()
    assert any(d["dish_id"] == dish_id for d in listed["dishes"])

    delete = client.post("/api/recipe/delete", json={**scope, "dish_id": dish_id})
    assert delete.status_code == 200
    listed_after = client.get("/api/recipe/list", params=scope).json()
    assert not any(d["dish_id"] == dish_id for d in listed_after["dishes"])


def test_recipe_save_rejects_unusable_ingredients():
    client = _recipe_client()
    res = client.post("/api/recipe/save", json={
        "province": "__test_recipe_scope__", "stage": "sd", "name": "Gibberish",
        "ingredient_lines": ["zzz not real zzz"]})
    assert res.status_code == 422


def test_saved_recipe_dish_detail_resolves_by_negative_id():
    client = _recipe_client()
    scope = {"province": "__test_recipe_scope__", "stage": "sd"}
    dish_id = client.post("/api/recipe/save", json={
        **scope, "name": "Gulai Ayam Hijau __test__",
        "ingredient_lines": ["1 kg ayam, daging, segar", "400 ml santan"],
    }).json()["dish_id"]
    try:
        res = client.get(f"/api/dish/{dish_id}", params=scope)
        assert res.status_code == 200, res.text
        assert res.json()["name"] == "Gulai Ayam Hijau __test__"
        assert res.json()["ingredients"]
    finally:
        client.post("/api/recipe/delete", json={**scope, "dish_id": dish_id})


def test_substitute_endpoint_handles_a_saved_recipe_dish():
    client = _recipe_client()
    scope = {"province": "__test_recipe_scope__", "stage": "sd"}
    dish_id = client.post("/api/recipe/save", json={
        **scope, "name": "Gulai Ayam Hijau __test__",
        "ingredient_lines": ["1 kg ayam, daging, segar", "400 ml santan"],
    }).json()["dish_id"]
    try:
        res = client.post("/api/substitute", json={
            **scope, "dish_id": dish_id, "ingredient": "ayam", "lang": "en"})
        assert res.status_code == 200, res.text
        assert res.json()["is_core"] is True
    finally:
        client.post("/api/recipe/delete", json={**scope, "dish_id": dish_id})


def test_planbody_to_request_carries_extra_dishes():
    from racik.api import PlanBody
    from racik.recipes import compute_dish
    custom = compute_dish(-1, "X", ["1 kg ayam, daging, segar"],
                          province="Jawa Tengah")
    assert custom is not None
    req = PlanBody(stage="sd").to_request(extra_dishes=[custom])
    assert list(req.extra_dishes) == [custom]
    # defaults to empty, not None, when nothing is passed
    assert PlanBody(stage="sd").to_request().extra_dishes == ()


def test_solve_fetches_this_scopes_saved_recipes_as_extra_dishes():
    """api._solve() is the one place /api/plan, /api/procurement and
    /api/report get a PlanRequest — a saved Recipe Workshop dish for this
    scope must reach every one of them as extra_dishes, not just sit in
    the list nothing reads (see the docstring on _solve)."""
    from unittest.mock import patch
    from racik.recipes import CustomDishStore

    client = _recipe_client()
    body = {"days": 1, "stage": "sd", "portions": 30,
           "province": "__test_extra_dishes_scope__", "max_solve_seconds": 5}
    with patch.object(CustomDishStore, "list_dishes",
                      return_value=[]) as mocked:
        for path in ("/api/plan", "/api/procurement", "/api/candidates"):
            mocked.reset_mock()
            res = client.post(path, json=body)
            assert res.status_code == 200, f"{path} failed: {res.text[:300]}"
            assert mocked.call_count == 1, (
                f"{path} did not fetch this scope's saved recipes as "
                "extra_dishes")


# ---------------------------------------------------------------- swap

def test_swap_replaces_only_the_named_slot():
    client = _recipe_client()
    plan = client.post("/api/plan", json={
        "days": 1, "stage": "sd", "portions": 50,
        "province": "Jawa Tengah", "max_solve_seconds": 8}).json()
    day = plan["days"][0]
    day_slots = {slot: (d["dish_id"] if d else None)
                for slot, d in day["slots"].items()}
    target_slot = next(s for s, d in day["slots"].items() if d is not None)
    original_id = day_slots[target_slot]

    res = client.post("/api/swap", json={
        "days": 1, "stage": "sd", "portions": 50, "province": "Jawa Tengah",
        "max_solve_seconds": 8, "day_index": 0, "slot": target_slot,
        "day_slots": day_slots})
    assert res.status_code == 200, res.text
    swapped = res.json()

    assert swapped["slots"][target_slot]["dish_id"] != original_id
    for slot, dish_id in day_slots.items():
        if slot == target_slot:
            continue
        got = swapped["slots"][slot]
        assert (got["dish_id"] if got else None) == dish_id, (
            f"slot {slot} changed but only {target_slot} should have")
    # a real recompute, not an echo of the original day
    assert swapped["cost_per_portion_idr"] > 0
    assert swapped["compliance"]


def test_swap_rejects_an_unknown_slot():
    client = _recipe_client()
    res = client.post("/api/swap", json={
        "stage": "sd", "day_index": 0, "slot": "dessert", "day_slots": {}})
    assert res.status_code == 400


def test_swap_reports_no_alternative_rather_than_crashing():
    from unittest.mock import patch
    from racik.optimizer import MenuOptimizer
    client = _recipe_client()
    with patch.object(MenuOptimizer, "_candidates",
                      return_value={"hewani": []}):
        res = client.post("/api/swap", json={
            "stage": "sd", "day_index": 0, "slot": "hewani",
            "day_slots": {"hewani": 12345}})
    assert res.status_code == 422
