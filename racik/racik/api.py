"""HTTP API and static host for the Racik planner.

Run:  python -m uvicorn racik.api:app --reload --port 8000
Then: http://127.0.0.1:8000
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import (FRONTEND_DIR, MBG, PROJECT_DIR, SLOT_LABELS_EN,
                     SLOT_LABELS_ID, SLOTS, UI_DIR, MBGConfig)

# Load racik/.env before anything below reads os.environ (make_client(),
# SEALION_API_KEY, BEDROCK_MODEL_ARN, ...) — nothing did this before, so a
# filled-in .env silently had no effect unless someone remembered to
# `export` each variable by hand. Absolute path: works regardless of the
# directory uvicorn was launched from. override=False: a real environment
# variable (CI, systemd, docker) still wins over the file.
load_dotenv(PROJECT_DIR / ".env", override=False)

from .akg import (ADVISORY_NUTRIENTS, BINDING_NUTRIENTS, NUTRIENT_META,
                  SCHOOL_STAGES, STAGE_LABELS, stage_band)
from .history import PlanHistory
from .i18n import DEFAULT_LANG, LANG_NAMES, LANGS, norm_lang, t, unit
from .optimizer import MenuOptimizer, PlanRequest, PlanResult, _tray_cache
from .orchestrator import TOOL_SCHEMAS, RacikGenerateError, RacikOrchestrator
from .procurement import aggregate, totals
from .recipes import CustomDishStore, compute_dish
from .report import build_report, plan_notes
from .serialize import compliance_rows, serialise_plan, slot_payload
from .bedrock import make_client
from .sealion import SeaLionClient
from .statedb import StateStore
from .store import RacikStore
from .substitution import SubstitutionAgent
from .translate import DishTranslator
from .recipe_text import StepsTranslator

app = FastAPI(title="Racik", version="0.1.0",
              description="AKG-grounded MBG menu planning for Indonesia")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


@lru_cache(maxsize=1)
def _store() -> RacikStore:
    return RacikStore()


@lru_cache(maxsize=1)
def _optimizer() -> MenuOptimizer:
    return MenuOptimizer(_store().load_dishes())


@lru_cache(maxsize=1)
def _state() -> StateStore:
    return StateStore()


@lru_cache(maxsize=1)
def _history() -> PlanHistory:
    return PlanHistory()


@lru_cache(maxsize=1)
def _substitution_agent() -> SubstitutionAgent:
    return SubstitutionAgent(_store(), make_client())


@lru_cache(maxsize=1)
def _custom_dishes() -> CustomDishStore:
    return CustomDishStore()


# ---------------------------------------------------------------- schemas


class PlanBody(BaseModel):
    days: int = Field(5, ge=1, le=7)
    stage: str = "sd"
    portions: int = Field(100, ge=1, le=100_000)
    province: str = ""
    island: str = ""
    budget_per_portion_idr: float = Field(MBG.budget_per_portion_idr, gt=0)
    ingredient_budget_share: float = Field(MBG.ingredient_budget_share, gt=0, le=1)
    regional_cost_index: float = Field(1.0, gt=0, le=5)
    exclude_terms: list[str] = []
    exclude_dish_ids: list[int] = []
    enforce_micronutrients: bool = False
    max_solve_seconds: float = Field(12.0, gt=0, le=60)
    random_seed: int = 0
    lang: str = DEFAULT_LANG
    # User-entered nutrient targets, e.g. {"protein_g": 22}. A direct number
    # the person typed, not a model guess — AKG stays the default for every
    # key left out. See optimizer.PlanRequest.target_overrides.
    target_overrides: dict[str, float] = {}
    # Confirmed leftover stock to use up this plan — [{"tkpi_code":...,
    # "usable_within_days": int}]. The client fetches /api/pantry to show
    # what's on record, lets the kitchen uncheck anything gone bad, and
    # sends only the confirmed subset here — storage isn't trusted blindly.
    pantry_items: list[dict] = []

    def to_request(self, recency_weights: Optional[dict] = None,
                   extra_dishes: Optional[list] = None) -> PlanRequest:
        config = MBGConfig(
            budget_per_portion_idr=self.budget_per_portion_idr,
            ingredient_budget_share=self.ingredient_budget_share,
            regional_cost_index=self.regional_cost_index,
        )
        if self.stage not in SCHOOL_STAGES:
            raise HTTPException(400, f"unknown stage '{self.stage}'")
        return PlanRequest(
            days=self.days, stage=self.stage, portions=self.portions,
            province=self.province, island=self.island, config=config,
            exclude_terms=self.exclude_terms,
            exclude_dish_ids=self.exclude_dish_ids,
            enforce_micronutrients=self.enforce_micronutrients,
            max_solve_seconds=self.max_solve_seconds,
            random_seed=self.random_seed,
            recency_weights=recency_weights or {},
            target_overrides=self.target_overrides,
            pantry_items=self.pantry_items,
            extra_dishes=extra_dishes or (),
        )


# ---------------------------------------------------------------- endpoints


@app.get("/api/meta")
def meta() -> dict:
    store = _store()
    provinces = store.provinces()
    # On a CPU-constrained host, scope the demo to only the provinces with
    # a precomputed tray bank — every one of them then generates instantly
    # with guaranteed full AKG compliance, instead of occasionally landing
    # on a province that falls through to a live solve the host is too slow
    # to finish well. Off by default; local dev always sees every province.
    if os.environ.get("RACIK_LIMIT_PROVINCES_TO_CACHE"):
        bank = _tray_cache()
        if bank and bank.get("regions"):
            allowed = set(bank["regions"])
            provinces = [p for p in provinces if p[0] in allowed]
    return {
        "stats": store.stats(),
        "stages": [
            {
                "key": key, "label": STAGE_LABELS[key],
                "targets": {
                    n: round(v, 1)
                    for n, v in stage_band(key).per_meal(MBG.akg_fraction).items()
                },
            }
            for key in SCHOOL_STAGES
        ],
        "provinces": [
            {"province": p, "island": i, "dishes": n}
            for p, i, n in provinces
        ],
        "slots": [
            {"key": s, "label_id": SLOT_LABELS_ID[s], "label_en": SLOT_LABELS_EN[s]}
            for s in SLOTS
        ],
        "nutrients": [
            {
                "key": key, "label_id": meta_[0], "label_en": meta_[1],
                "unit": meta_[2], "status": meta_[3],
                "binding": key in BINDING_NUTRIENTS,
                "advisory": key in ADVISORY_NUTRIENTS,
            }
            for key, meta_ in NUTRIENT_META.items()
        ],
        "languages": [{"code": c, "name": LANG_NAMES[c]} for c in LANGS],
        "default_lang": DEFAULT_LANG,
        "budget": {
            "per_portion_idr": MBG.budget_per_portion_idr,
            "ingredient_share": MBG.ingredient_budget_share,
            "ingredient_idr": MBG.ingredient_budget_idr,
            "akg_fraction": MBG.akg_fraction,
        },
    }


def _solve(body: PlanBody):
    """The one place every endpoint gets a PlanRequest from a PlanBody —
    so /api/plan, /api/procurement and /api/report all solve with the
    identical recency weighting, not just the same body. Before this,
    only /api/plan fetched recency_weights; the other two solved with an
    empty {}, meaning the shopping list or printed report could silently
    reflect a different menu than the one actually on screen.

    Also folds in this scope's saved Recipe Workshop dishes (recipes.py)
    as extra_dishes — a school-authored recipe that's been saved should be
    genuinely eligible for future plans, not just sit in a list nobody's
    plan ever considers.
    """
    weights = _history().recency_weights(body.province, body.stage)
    extra = _custom_dishes().list_dishes(body.province, body.stage)
    return _optimizer().solve(
        body.to_request(recency_weights=weights, extra_dishes=extra))


@app.post("/api/plan")
def plan(body: PlanBody) -> dict:
    history = _history()
    result = _solve(body)
    if not result.feasible:
        raise HTTPException(
            422, f"no menu could be built (solver status: {result.status})")
    # Record what this scope was served before returning it: history.py turns
    # that plus any rating into the recency weight the next solve is penalised
    # by, which is the whole point of the feature.
    served = [dish.dish_id for day in result.days for dish in day.selected]
    history.record(body.province, body.stage, served)
    return serialise_plan(result, norm_lang(body.lang))


class RateBody(BaseModel):
    dish_id: int
    rating: float = Field(..., ge=1, le=5)
    province: str = ""
    stage: str = "sd"


@app.post("/api/rate")
def rate(body: RateBody) -> dict:
    """Fold a kitchen's end-of-day rating into a dish's running score.

    Feeds directly into the next solve's recency weighting (history.py):
    a well-rated dish eases back into rotation sooner, a poorly-rated one
    is pushed away harder — replacing a flat "never repeat" rule with one
    that responds to whether the kids actually liked it.
    """
    mean = _history().rate(body.province, body.stage, body.dish_id, body.rating)
    return {"dish_id": body.dish_id, "mean_rating": round(mean, 2)}


class RateReasonBody(BaseModel):
    dish_id: int
    rating: float = Field(..., ge=1, le=5)
    province: str = ""
    stage: str = "sd"
    dish_name: str = ""
    reason: str = Field(..., min_length=1)  # e.g. "too_expensive" /
                      # "not_regional" / "nutrition" / "kids_disliked" /
                      # "other" — same categories main branch's reject-
                      # reason chips offered, now actually logged (see
                      # history.feedback_log) rather than shown and
                      # discarded. Separate from /api/rate on purpose: this
                      # never touches the running mean, so it can't
                      # double-count a rating already submitted.


@app.post("/api/rate/reason")
def rate_reason(body: RateReasonBody) -> dict:
    """Attach a *why* to a rating that already happened."""
    _history().log_reason(body.province, body.stage, body.dish_id,
                          body.dish_name, body.reason, body.rating)
    return {"ok": True}


@app.get("/api/feedback")
def feedback(province: str = "", stage: str = "sd", limit: int = 50) -> dict:
    """The reasons behind low ratings, most recent first — a real feedback
    log, unlike main branch's version which displayed the same categories
    but never persisted or used them beyond one page view."""
    return {"entries": _history().feedback_log(province, stage, limit)}


class PantryReportBody(BaseModel):
    province: str = ""
    stage: str = "sd"
    tkpi_code: str
    ingredient_name: str
    remaining_g: float = Field(..., ge=0)
    usable_within_days: Optional[int] = Field(None, ge=1, le=14)


@app.get("/api/pantry")
def pantry(province: str = "", stage: str = "sd") -> dict:
    """Current leftover stock for this scope — what the setup screen shows
    before generating a plan, so a kitchen doesn't have to re-enter what
    it's already reported."""
    return {"items": _history().pantry_items(province, stage)}


@app.post("/api/pantry/report")
def pantry_report(body: PantryReportBody) -> dict:
    """Record (or update) how much of an ingredient is left over, and for
    how many of the next plan's days it's still good to use.

    Feeds optimizer.py's pantry bonus (the mirror of the recency penalty):
    a dish using this ingredient gets nudged toward selection, but only for
    days within usable_within_days — after that it fades out like anything
    else, same as a dish's recency avoidance fades back to zero.
    """
    _history().report_leftover(
        body.province, body.stage, body.tkpi_code, body.ingredient_name,
        body.remaining_g, body.usable_within_days)
    return {"ok": True}


@app.post("/api/pantry/clear")
def pantry_clear(province: str = "", stage: str = "sd",
                 tkpi_code: str = "") -> dict:
    """Remove one item — used it all, or it went bad before it could be."""
    _history().clear_pantry_item(province, stage, tkpi_code)
    return {"ok": True}


class RecipeComputeBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    ingredient_lines: list[str] = Field(..., min_length=1, max_length=40)
    steps: str = ""
    province: str = ""
    island: str = ""


def _ingredient_rows(dish) -> list[dict]:
    """Per-ingredient dict for a live-built Dish (recipes.py, not yet
    persisted to the corpus SQLite tables) in the same shape store.lines()
    gives for a corpus dish — so the dish detail dialog renders a custom
    dish identically to any other."""
    rows = []
    for ln in dish.lines:
        rows.append({
            "raw": ln.parsed.raw, "name": ln.name,
            "gross_g": round(ln.gross_g, 1), "edible_g": round(ln.edible_g, 1),
            "cost_idr": round(ln.cost_idr),
            "tkpi_code": ln.match.food.code if ln.matched else "",
            "tkpi_name": ln.food_name if ln.matched else "",
            "match_method": ln.match.method if ln.matched else "",
            "urt_confidence": str(ln.parsed.confidence.value
                                  if hasattr(ln.parsed.confidence, "value")
                                  else ln.parsed.confidence),
            "urt_rule": ln.parsed.rule, "unquantified": ln.parsed.unquantified,
        })
    return rows


@app.post("/api/recipe/compute")
def recipe_compute(body: RecipeComputeBody) -> dict:
    """Preview a school-authored dish without saving it — the same
    deterministic pipeline every corpus recipe goes through (see
    recipes.py), so what's shown here is exactly what would be saved."""
    dish = compute_dish(-1, body.name, body.ingredient_lines,
                        steps=body.steps, province=body.province,
                        island=body.island)
    if dish is None:
        raise HTTPException(
            422, "Could not compute a dish from these ingredient lines — "
            "check the names and quantities.")
    payload = dish.to_dict()
    payload["steps"] = dish.steps
    payload["main_food"] = dish.main_food_name
    payload["ingredients"] = _ingredient_rows(dish)
    return payload


class RecipeSaveBody(BaseModel):
    province: str = ""
    stage: str = "sd"
    name: str = Field(..., min_length=1, max_length=200)
    ingredient_lines: list[str] = Field(..., min_length=1, max_length=40)
    steps: str = ""
    island: str = ""


@app.post("/api/recipe/save")
def recipe_save(body: RecipeSaveBody) -> dict:
    """Persist a school-authored dish, scoped like ratings and pantry —
    and from the next solve onward it's a genuine candidate (see _solve's
    extra_dishes), not just a saved record nothing reads."""
    dish = compute_dish(-1, body.name, body.ingredient_lines,
                        steps=body.steps, province=body.province,
                        island=body.island)
    if dish is None:
        raise HTTPException(
            422, "Could not compute a dish from these ingredient lines — "
            "check the names and quantities.")
    dish_id = _custom_dishes().save(
        body.province, body.stage, body.name, body.ingredient_lines,
        steps=body.steps, island=body.island)
    return {"dish_id": dish_id}


@app.get("/api/recipe/list")
def recipe_list(province: str = "", stage: str = "sd") -> dict:
    dishes = _custom_dishes().list_dishes(province, stage)
    return {"dishes": [d.to_dict() for d in dishes]}


class RecipeDeleteBody(BaseModel):
    province: str = ""
    stage: str = "sd"
    dish_id: int


@app.post("/api/recipe/delete")
def recipe_delete(body: RecipeDeleteBody) -> dict:
    _custom_dishes().delete(body.province, body.stage, body.dish_id)
    return {"ok": True}


@app.get("/api/dish/{dish_id}")
def dish(dish_id: int, province: str = "", stage: str = "sd") -> dict:
    # Negative ids are Recipe Workshop dishes (recipes.py) — never in the
    # shared corpus store, but real once saved: they can be selected into
    # an actual plan (see _solve's extra_dishes) and need to open the same
    # detail dialog any other tray tile does. province/stage locate the
    # right scope, same as every other Recipe Workshop/pantry/rating call.
    if dish_id < 0:
        found = _custom_dishes().get(province, stage, dish_id)
        if found is None:
            raise HTTPException(404, f"dish {dish_id} not found")
        payload = found.to_dict()
        payload["steps"] = found.steps
        payload["main_food"] = found.main_food_name
        payload["ingredients"] = _ingredient_rows(found)
        return payload

    store = _store()
    found = store.dish(dish_id)
    if found is None:
        raise HTTPException(404, f"dish {dish_id} not found")
    payload = found.to_dict()
    rewritten = _steps_translator().translate(dish_id, found.steps)
    payload.update(rewritten.to_dict())
    payload["main_food"] = found.main_food_name
    payload["ingredients"] = [
        {
            "raw": line.raw, "name": line.name, "gross_g": round(line.gross_g, 1),
            "edible_g": round(line.edible_g, 1),
            "cost_idr": round(line.cost_idr), "tkpi_code": line.tkpi_code,
            "tkpi_name": line.tkpi_name, "match_method": line.match_method,
            "urt_confidence": line.urt_confidence, "urt_rule": line.urt_rule,
            "unquantified": line.unquantified,
        }
        for line in store.lines(dish_id)
    ]
    return payload


class SubstituteBody(BaseModel):
    dish_id: int
    ingredient: str = Field(..., min_length=1, max_length=200)
    lang: str = DEFAULT_LANG
    # Only needed when dish_id is a Recipe Workshop dish (negative id) —
    # scopes the lookup, same as /api/dish/{id}.
    province: str = ""
    stage: str = "sd"


@app.post("/api/substitute")
def substitute(body: SubstituteBody) -> dict:
    """The Reviewer agent: what to do when one ingredient isn't available.

    A different question than /api/plan — not a re-optimisation, a judgment
    call over one ingredient in an already-chosen dish. See substitution.py.
    """
    try:
        if body.dish_id < 0:
            found = _custom_dishes().get(body.province, body.stage, body.dish_id)
            if found is None:
                raise HTTPException(404, f"dish {body.dish_id} not found")
            result = _substitution_agent().review_custom(
                found, body.ingredient, lang=norm_lang(body.lang))
        else:
            result = _substitution_agent().review(
                body.dish_id, body.ingredient, lang=norm_lang(body.lang))
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return result.to_dict()


@app.post("/api/procurement")
def procurement(body: PlanBody, day: Optional[int] = None) -> dict:
    result = _solve(body)
    if not result.feasible:
        raise HTTPException(422, "no menu could be built")
    lines = aggregate(result, _store(),
                      day_indexes=[day] if day is not None else None)
    return {
        "portions": body.portions,
        "days": len(result.days) if day is None else 1,
        "totals": totals(lines),
        "lines": [line.to_dict() for line in lines],
    }


@app.post("/api/candidates")
def candidates(body: PlanBody) -> dict:
    """The pre-filter rubric and its effect, without running a solve.

    Answers "why was this dish never considered?" — the gates in order, the
    score formula with its weights, and how many dishes each gate removed.
    Includes this scope's saved Recipe Workshop dishes as extra_dishes, same
    as _solve() — otherwise "why wasn't my saved recipe eligible" would get
    an answer computed without it in the pool at all.
    """
    extra = _custom_dishes().list_dishes(body.province, body.stage)
    return _optimizer().explain_candidates(body.to_request(extra_dishes=extra))


class SwapBody(PlanBody):
    day_index: int = 0
    slot: str
    # The day's current lineup, {slot: dish_id or null} — everything except
    # `slot` stays exactly as-is; only the named slot gets replaced. Sent by
    # the client because this endpoint recomputes the whole day (cost,
    # nutrients, compliance) rather than touching just the swapped tile.
    day_slots: dict[str, Optional[int]] = {}


@app.post("/api/swap")
def swap_dish(body: SwapBody) -> dict:
    """Replace one dish in one already-built day, holding every other slot
    fixed — the "give me something else for this slot" gesture an operator
    review needs, distinct from both a full reshuffle (redecides everything)
    and ingredient substitution (which is about availability, not a dish
    the operator would simply rather not serve).

    Doesn't re-run the solver: the replacement is the next-best dish this
    slot's own candidate pool already ranked (the same pool a real solve
    draws from — same gates, same score), skipping whatever's already
    somewhere in this day. A full re-optimisation would rebalance every
    other slot's cost/nutrition too, which defeats the point of a scoped
    swap — the operator asked to change one dish, not the whole day.
    """
    if body.slot not in SLOTS:
        raise HTTPException(400, f"unknown slot '{body.slot}'")

    weights = _history().recency_weights(body.province, body.stage)
    extra = _custom_dishes().list_dishes(body.province, body.stage)
    request = body.to_request(recency_weights=weights, extra_dishes=extra)
    targets = stage_band(request.stage).per_meal(request.config.akg_fraction)
    if request.target_overrides:
        targets = {**targets, **{k: v for k, v in request.target_overrides.items()
                                 if k in targets and v is not None}}

    pool = _optimizer()._candidates(request, targets).get(body.slot, [])
    taken = {v for v in body.day_slots.values() if v is not None}
    replacement = next((d for d in pool if d.dish_id not in taken), None)
    if replacement is None:
        raise HTTPException(
            422, "No alternative dish is available for this slot under the "
            "current budget and exclusion constraints.")

    store = _store()
    dishes = {}
    for slot in SLOTS:
        if slot == body.slot:
            dishes[slot] = replacement
            continue
        dish_id = body.day_slots.get(slot)
        if dish_id is None:
            dishes[slot] = None
        elif dish_id < 0:
            dishes[slot] = _custom_dishes().get(body.province, body.stage, dish_id)
        else:
            dishes[slot] = store.dish(dish_id)

    from .tkpi import NUTRIENT_KEYS
    nutrients = {k: 0.0 for k in NUTRIENT_KEYS}
    cost = 0.0
    for dish_ in dishes.values():
        if dish_ is None:
            continue
        cost += dish_.cost_per_portion_idr
        for k in NUTRIENT_KEYS:
            nutrients[k] += dish_.per_portion.get(k, 0.0)
    binding_scores = [min(1.0, nutrients.get(n, 0.0) / targets[n])
                      for n in BINDING_NUTRIENTS if targets.get(n)]
    adequacy = sum(binding_scores) / len(binding_scores) if binding_scores else 0.0

    lang = norm_lang(body.lang)
    slots_payload = {slot: slot_payload(dish_, body.portions)
                     for slot, dish_ in dishes.items()}

    return {
        "index": body.day_index,
        "cost_per_portion_idr": round(cost),
        "cost_total_idr": round(cost * body.portions),
        "adequacy": round(adequacy, 3),
        "nutrients": {k: round(v, 2) for k, v in nutrients.items()},
        "compliance": compliance_rows(nutrients, targets, lang),
        "slots": slots_payload,
    }


class TranslateBody(BaseModel):
    names: list[str] = Field(..., min_length=1, max_length=200)
    use_model: bool = True


@app.post("/api/translate")
def translate_names(body: TranslateBody) -> dict:
    """Gloss Indonesian dish names into English with SEA-LION.

    The gloss is carried alongside the name, never instead of it, and each
    result reports whether it came from the model or the offline glosser.
    """
    glosses = _translator().translate(body.names, use_model=body.use_model)
    return {
        "count": len(glosses),
        "model": _translator().client.model,
        "configured": _translator().client.configured,
        "glosses": [g.to_dict() for g in glosses],
    }


class ReportBody(PlanBody):
    sppg_name: str = ""


@app.post("/api/report")
def report(body: ReportBody) -> HTMLResponse:
    """The printable compliance + procurement document.

    One page an SPPG hands to a supervisor or auditor: the menu, its AKG
    compliance, every relaxed floor, the shopping list, and the methodology
    caveats. Prints to PDF from any browser.
    """
    result = _solve(body)
    if not result.feasible:
        raise HTTPException(422, "no menu could be built")
    lines = aggregate(result, _store())
    html_doc = build_report(result, lines, lang=norm_lang(body.lang),
                            sppg_name=body.sppg_name)
    return HTMLResponse(html_doc)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "dishes": _store().stats()["dishes"]}


# ---------------------------------------------------------------- orchestrator


@lru_cache(maxsize=1)
def _translator() -> DishTranslator:
    return DishTranslator(make_client())


@lru_cache(maxsize=1)
def _steps_translator() -> StepsTranslator:
    # Deliberately hosted SEA-LION (SeaLionClient's own default), not
    # make_client()/Bedrock: the source text is Bahasa Indonesia home-cook
    # notes, and SEA-LION is trained specifically on Southeast Asian
    # languages — a better fit for this rewrite than the general-purpose
    # model driving Agen Gizi/Agen Biaya. Needs SEALION_API_KEY in .env;
    # falls back to the same-language rule-based cleanup without one.
    return StepsTranslator()


@lru_cache(maxsize=1)
def _orchestrator() -> RacikOrchestrator:
    return RacikOrchestrator(_store(), _optimizer(), make_client(),
                             history=_history())


class AskBody(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=20)
    lang: str = DEFAULT_LANG


@app.get("/api/orchestrator")
def orchestrator_status() -> dict:
    """Which model is driving, and whether it is reachable.

    `describe()`'s own "provider" field already names which of the five
    supported providers (openai/anthropic/bedrock/bedrock-sealion-import/
    sealion) is live — "mode" here is deliberately provider-agnostic rather
    than a second, easily-stale label for the same fact.
    """
    client = _orchestrator().client
    return {
        **client.describe(),
        "tools": [t["function"]["name"] for t in TOOL_SCHEMAS],
        "max_steps": _orchestrator().max_steps,
        # "sealion" is a legacy tag meaning "a real LLM is configured and
        # answering" — the redesigned UI branches on exactly that string in
        # five places, so it stays. It does not mean the provider IS SEA-LION;
        # that is in the "provider"/"model" fields above.
        "mode": "sealion" if client.configured else "fallback",
        # Same fact without the archaeology, for anything written from here on.
        "llm_configured": bool(client.configured),
        "hint": (f"{client.model} is configured and answering via "
                 f"{client.describe().get('provider', 'the configured provider')}."
                 if client.configured else
                 "No LLM provider configured (see racik/.env.example) — "
                 "Racik answers with a rule-based planner instead. Any of "
                 "SEALION_API_KEY, ANTHROPIC_API_KEY, BEDROCK_MODEL_ID, "
                 "BEDROCK_MODEL_ARN, or BEDROCK_NATIVE_MODEL_ID turns this on."),
    }


@app.post("/api/ask")
def ask(body: AskBody) -> dict:
    """Natural-language planning, orchestrated by SEA-LION.

    Numbers in the answer are produced by the deterministic engine; the returned
    `trace` lists every tool call that produced them.
    """
    result = _orchestrator().ask(body.question, body.history,
                                 lang=norm_lang(body.lang))
    return result.to_dict()


# ---------------------------------------------------------------- generate pipeline
#
# The workflow the operator actually drives from the styled frontend:
# preprocessing -> Agen Gizi -> Agen Biaya -> CP-SAT -> Validator -> menu plan,
# with the result persisted so Operator review and Menu history (below) have
# something to act on. See orchestrator.RacikOrchestrator.generate().


class GenerateBody(BaseModel):
    days: int = Field(5, ge=1, le=7)
    portions: int = Field(100, ge=1, le=100_000)
    province: str = ""
    stage: str = ""                     # "" = let Agen Gizi infer (defaults to "sd")
    budget_mode: str = "total"          # "total" | "per_portion"
    budget_value: float = Field(MBG.budget_per_portion_idr, gt=0)
    notes: str = ""                     # free-text allergy/preference notes
    exclude_dish_ids: list[int] = []    # operator vetoes carried from a prior run
    history_days: int = Field(14, ge=0, le=60)   # rotation/decay window
    lang: str = DEFAULT_LANG


@app.post("/api/generate")
def generate(body: GenerateBody) -> dict:
    if body.budget_mode not in ("total", "per_portion"):
        raise HTTPException(400, "budget_mode must be 'total' or 'per_portion'")
    try:
        result = _orchestrator().generate(
            days=body.days, portions=body.portions, province=body.province,
            stage=body.stage or None, budget_mode=body.budget_mode,
            budget_value=body.budget_value, notes_text=body.notes,
            exclude_dish_ids=body.exclude_dish_ids,
            history_days=body.history_days, lang=norm_lang(body.lang),
            state=_state())
    except RacikGenerateError as exc:
        raise HTTPException(422, str(exc)) from exc
    return result.to_dict()


# ---------------------------------------------------------------- operator review


class ReviewBody(BaseModel):
    run_id: int
    day_index: int
    decision: str            # "accept" | "reject"
    reason: str = ""
    replace: bool = False    # solve a one-day replacement for a rejected day
    lang: str = DEFAULT_LANG


@app.post("/api/review")
def review(body: ReviewBody) -> dict:
    """Persist an accept/reject decision. A reject can ask for a same-day
    replacement, solved with the rejected dish excluded — "operator review"
    feeding straight back into the CP-SAT solver, per the workflow diagram."""
    if body.decision not in ("accept", "reject"):
        raise HTTPException(400, "decision must be 'accept' or 'reject'")
    state = _state()
    state.record_review(body.run_id, body.day_index, body.decision, body.reason)
    response: dict = {"ok": True}
    if body.decision == "reject" and body.replace:
        try:
            response["replacement_day"] = _orchestrator().replace_day(
                run_id=body.run_id, day_index=body.day_index,
                lang=norm_lang(body.lang), state=state)
        except RacikGenerateError as exc:
            raise HTTPException(422, str(exc)) from exc
    return response


@app.get("/api/history")
def history(limit: int = 30) -> dict:
    """Recently served dishes (menu history / rotation) and rejection reasons
    (feedback the Settings tab shows, and Agen Gizi reads on the next run)."""
    state = _state()
    return {
        "recent_served": state.recent_served(limit=limit),
        "rejections": state.rejection_log(limit=limit),
    }


# ---------------------------------------------------------------- stock & audit


class StockBody(BaseModel):
    run_id: int
    day_index: int
    ingredient_name: str
    received_pct: Optional[float] = Field(None, ge=0, le=200)
    used_pct: Optional[float] = Field(None, ge=0, le=200)
    actual_cost_idr: Optional[float] = Field(None, ge=0)
    note: Optional[str] = None


@app.post("/api/stock")
def stock_upsert(body: StockBody) -> dict:
    _state().upsert_stock(
        body.run_id, body.day_index, body.ingredient_name,
        received_pct=body.received_pct, used_pct=body.used_pct,
        actual_cost_idr=body.actual_cost_idr, note=body.note)
    return {"ok": True}


@app.get("/api/stock")
def stock_list(run_id: int) -> dict:
    return {"run_id": run_id, "records": _state().stock_for_run(run_id)}


# ---------------------------------------------------------------- static UI
#
# Two frontends ship, and both are real. The root index.html/css/js is the
# primary operator UI: a tab-per-stage workflow (onboarding, plan, day
# detail, procurement, stock audit) built as ES modules. `ui/index.html` is
# the agent-first single-file UI, where the main "build menu" action goes
# through /api/ask rather than calling the solver directly; it stays mounted
# at /agent so the two can be compared against the same live backend.


class _NoCacheStaticFiles(StaticFiles):
    """Serves ETag/Last-Modified as usual but forces revalidation on every
    request. Without this, browsers apply heuristic caching to JS/CSS with
    no Cache-Control header and can keep serving a stale frontend build
    indefinitely after a redeploy or local edit."""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


if FRONTEND_DIR.exists() and (FRONTEND_DIR / "index.html").exists():
    if (FRONTEND_DIR / "css").exists():
        app.mount("/css", _NoCacheStaticFiles(directory=FRONTEND_DIR / "css"),
                 name="frontend-css")
    if (FRONTEND_DIR / "js").exists():
        app.mount("/js", _NoCacheStaticFiles(directory=FRONTEND_DIR / "js"),
                 name="frontend-js")
    if (FRONTEND_DIR / "assets").exists():
        app.mount("/assets", _NoCacheStaticFiles(directory=FRONTEND_DIR / "assets"),
                 name="frontend-assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html",
                            headers={"Cache-Control": "no-cache"})

elif UI_DIR.exists():
    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(UI_DIR / "index.html")

if UI_DIR.exists():
    app.mount("/agent", StaticFiles(directory=UI_DIR, html=True), name="agent-ui")


_ARCHITECTURE_SVG = PROJECT_DIR / "docs" / "architecture.svg"

if _ARCHITECTURE_SVG.exists():
    @app.get("/architecture.svg", include_in_schema=False)
    def architecture() -> FileResponse:
        """The system diagram, served from docs/ so there is one copy of it."""
        return FileResponse(_ARCHITECTURE_SVG, media_type="image/svg+xml")
