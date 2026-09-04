"""Tests for operator review: pinning accepted days and re-solving around them.

The property under test throughout is that a pin is honest. An accepted day
either comes back exactly as the operator left it, or it is reported as
dropped with a reason — never quietly rebuilt. A pin that could override a
gate would be worse than no pin at all, because the kitchen would cook a dish
containing an ingredient it does not have.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from racik.config import SLOTS
from racik.optimizer import MenuOptimizer, Pin, PlanRequest
from racik.store import RacikStore


@pytest.fixture(scope="module")
def store():
    return RacikStore()


@pytest.fixture(scope="module")
def optimizer(store):
    return MenuOptimizer(store.load_dishes())


@pytest.fixture(scope="module")
def base(optimizer):
    """A plan to review. Everything below pins some part of this."""
    return optimizer.solve(PlanRequest(days=3, stage="sd", max_solve_seconds=12))


def pins_for(result, day_index, slots=("hewani", "nabati", "sayur")):
    return [Pin(day_index, s, result.days[day_index].dishes[s].dish_id)
            for s in slots if result.days[day_index].dishes[s]]


# ---------------------------------------------------------------- pinning

def test_pinned_slots_survive_a_different_seed(optimizer, base):
    """The point of the feature: an accepted day does not move underneath you."""
    pins = pins_for(base, 0)
    result = optimizer.solve(PlanRequest(days=3, stage="sd", pins=pins,
                                         random_seed=4242, max_solve_seconds=12))
    assert result.feasible
    assert not result.dropped_pins
    for pin in pins:
        assert result.days[0].dishes[pin.slot].dish_id == pin.dish_id


def test_unpinned_days_are_still_free_to_change(optimizer, base):
    pins = pins_for(base, 0)
    result = optimizer.solve(PlanRequest(days=3, stage="sd", pins=pins,
                                         exclude_terms=["telur"],
                                         max_solve_seconds=12))
    assert result.feasible
    for day in result.days[1:]:
        for dish in day.selected:
            assert "telur" not in (dish.name + " " + dish.ingredient_index).lower()


def test_pin_never_beats_an_exclusion(optimizer, base):
    """An ingredient that has run out removes the dish, pinned or not."""
    dish = base.days[0].dishes["hewani"]
    term = dish.name.split()[0].lower()
    result = optimizer.solve(PlanRequest(days=3, stage="sd",
                                         pins=pins_for(base, 0),
                                         exclude_terms=[term],
                                         max_solve_seconds=12))
    assert result.feasible
    dropped = {(d.pin.slot, d.reason) for d in result.dropped_pins}
    assert ("hewani", "excluded") in dropped
    assert result.days[0].dishes["hewani"].dish_id != dish.dish_id


def test_pin_never_beats_an_operator_veto(optimizer, base):
    dish = base.days[0].dishes["nabati"]
    result = optimizer.solve(PlanRequest(days=3, stage="sd",
                                         pins=pins_for(base, 0),
                                         exclude_dish_ids=[dish.dish_id],
                                         max_solve_seconds=12))
    assert result.feasible
    assert any(d.pin.slot == "nabati" and d.reason == "rejected"
               for d in result.dropped_pins)
    for day in result.days:
        assert day.dishes["nabati"].dish_id != dish.dish_id


def test_pinned_dish_reaches_the_solver_past_the_ranking_cap(optimizer, base):
    """A cap of one candidate per slot would normally cut every other dish."""
    from racik.akg import stage_band
    from racik.config import MBG

    pin = pins_for(base, 0, slots=("sayur",))[0]
    request = PlanRequest(days=3, stage="sd", pins=[pin], candidates_per_slot=1)
    targets = stage_band("sd").per_meal(MBG.akg_fraction)
    pool, funnel = optimizer._candidates_with_funnel(request, targets)["sayur"]
    assert pin.dish_id in {d.dish_id for d in pool}
    assert funnel.selected == 2, "the cap still holds for everything but the pin"


def test_conflicting_pins_cost_the_pins_not_the_menu(optimizer, base):
    """Pins are hard, so a set of them can contradict the variety rules.

    The same reasoning that makes nutrient floors soft applies: hand the
    kitchen a menu and an explanation, never an error.
    """
    dish = base.days[0].dishes["sayur"]
    pins = [Pin(0, "sayur", dish.dish_id), Pin(1, "sayur", dish.dish_id)]
    result = optimizer.solve(PlanRequest(days=3, stage="sd", pins=pins,
                                         max_solve_seconds=12))
    assert result.feasible
    assert {d.reason for d in result.dropped_pins} == {"conflict"}


def test_kept_pins_and_summary_agree(optimizer, base):
    pins = pins_for(base, 0)
    result = optimizer.solve(PlanRequest(days=3, stage="sd", pins=pins,
                                         max_solve_seconds=12))
    assert len(result.kept_pins) + len(result.dropped_pins) == len(pins)
    assert result.summary()["pins_kept"] == len(result.kept_pins)
    assert result.summary()["pins_dropped"] == len(result.dropped_pins)


def test_unknown_pin_is_reported_not_raised(optimizer):
    result = optimizer.solve(PlanRequest(days=2, stage="sd",
                                         pins=[Pin(0, "hewani", -1),
                                               Pin(9, "sayur", 1)],
                                         max_solve_seconds=12))
    assert result.feasible, "a bad pin must not cost the kitchen its menu"
    reasons = {d.reason for d in result.dropped_pins}
    assert reasons == {"not_in_slot", "day_out_of_range"}


# ---------------------------------------------------------------- endpoint

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from racik.api import app
    return TestClient(app)


BASE_BODY = {"days": 3, "stage": "sd", "portions": 100, "max_solve_seconds": 12}


@pytest.fixture(scope="module")
def planned(client):
    res = client.post("/api/plan", json=BASE_BODY)
    assert res.status_code == 200
    return res.json()


def body_pins(plan, day=0):
    slots = plan["days"][day]["slots"]
    return [{"day": day, "slot": s, "dish_id": slots[s]["dish_id"]}
            for s in slots if slots[s]]


def test_replan_holds_the_accepted_day(client, planned):
    pins = body_pins(planned)
    res = client.post("/api/replan",
                      json={**BASE_BODY, "pins": pins, "random_seed": 77})
    assert res.status_code == 200
    out = res.json()
    assert out["replan"]["held_days"] == [0]
    assert out["replan"]["changed_days"] == [1, 2]
    for pin in pins:
        assert out["days"][0]["slots"][pin["slot"]]["dish_id"] == pin["dish_id"]


def test_replan_reports_the_pin_an_unavailable_ingredient_broke(client, planned):
    dish = planned["days"][0]["slots"]["hewani"]
    term = dish["name"].split()[0].lower()
    res = client.post("/api/replan", json={**BASE_BODY, "pins": body_pins(planned),
                                           "unavailable": [term]})
    assert res.status_code == 200
    out = res.json()
    assert out["replan"]["unavailable"] == [term]
    assert any(d["slot"] == "hewani" and d["reason"] == "excluded"
               for d in out["pins"]["dropped"])
    assert 0 not in out["replan"]["held_days"]


def test_replan_removes_a_rejected_dish_everywhere(client, planned):
    dish_id = planned["days"][0]["slots"]["hewani"]["dish_id"]
    res = client.post("/api/replan",
                      json={**BASE_BODY, "reject_dish_ids": [dish_id]})
    assert res.status_code == 200
    for day in res.json()["days"]:
        for slot in SLOTS:
            if day["slots"][slot]:
                assert day["slots"][slot]["dish_id"] != dish_id


def test_unavailable_does_not_discard_the_form_exclusions(client, planned):
    """A stock-out is merged with the allergy list, never substituted for it."""
    res = client.post("/api/replan", json={**BASE_BODY,
                                           "exclude_terms": ["udang"],
                                           "unavailable": ["telur"]})
    assert res.status_code == 200
    for day in res.json()["days"]:
        for dish in day["slots"].values():
            if not dish:
                continue
            name = dish["name"].lower()
            assert "udang" not in name and "telur" not in name


def test_impossible_stockout_names_the_empty_slots(client):
    """The 422 has to be actionable: which slot emptied, and which gate did it."""
    res = client.post("/api/replan", json={
        **BASE_BODY, "unavailable": ["a", "i", "u", "e", "o", "n", "g"]})
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["status"] == "NO_CANDIDATES"
    assert detail["empty_slots"], "an empty pool must name the slots it emptied"
    for entry in detail["empty_slots"]:
        assert entry["slot"] in SLOTS
        assert entry["binding_gate"]


def test_plain_plan_reports_an_empty_pin_block(client, planned):
    """Every surface reports pins, so a reader never has to know which endpoint ran."""
    assert planned["pins"] == {"kept": [], "dropped": []}
