"""HTTP API and static host for the Racik planner.

Run:  python -m uvicorn racik.api:app --reload --port 8000
Then: http://127.0.0.1:8000
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .akg import (ADVISORY_NUTRIENTS, BINDING_NUTRIENTS, NUTRIENT_META,
                  SCHOOL_STAGES, STAGE_LABELS, stage_band)
from .config import (MBG, PROJECT_DIR, SLOT_LABELS_EN, SLOT_LABELS_ID, SLOTS,
                     UI_DIR, MBGConfig)
from .i18n import DEFAULT_LANG, LANG_NAMES, LANGS, norm_lang, t, unit
from .optimizer import MenuOptimizer, PlanRequest, PlanResult
from .orchestrator import TOOL_SCHEMAS, RacikOrchestrator
from .procurement import aggregate, totals
from .report import build_report, plan_notes
from .bedrock import make_client
from .sealion import SeaLionClient
from .store import RacikStore
from .translate import DishTranslator

app = FastAPI(title="Racik", version="0.1.0",
              description="AKG-grounded MBG menu planning for Indonesia")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

DAY_LABELS = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
DAY_LABELS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                 "Saturday", "Sunday"]


@lru_cache(maxsize=1)
def _store() -> RacikStore:
    return RacikStore()


@lru_cache(maxsize=1)
def _optimizer() -> MenuOptimizer:
    return MenuOptimizer(_store().load_dishes())


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

    def to_request(self) -> PlanRequest:
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
        )


# ---------------------------------------------------------------- endpoints


@app.get("/api/meta")
def meta() -> dict:
    store = _store()
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
            for p, i, n in store.provinces()
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


@app.post("/api/plan")
def plan(body: PlanBody) -> dict:
    result = _optimizer().solve(body.to_request())
    if not result.feasible:
        raise HTTPException(
            422, f"no menu could be built (solver status: {result.status})")
    return _serialise(result, norm_lang(body.lang))


@app.get("/api/dish/{dish_id}")
def dish(dish_id: int) -> dict:
    store = _store()
    found = store.dish(dish_id)
    if found is None:
        raise HTTPException(404, f"dish {dish_id} not found")
    payload = found.to_dict()
    payload["steps"] = found.steps
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


@app.post("/api/procurement")
def procurement(body: PlanBody, day: Optional[int] = None) -> dict:
    result = _optimizer().solve(body.to_request())
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
    """
    return _optimizer().explain_candidates(body.to_request())


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
    result = _optimizer().solve(body.to_request())
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
def _orchestrator() -> RacikOrchestrator:
    return RacikOrchestrator(_store(), _optimizer(), make_client())


class AskBody(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=20)
    lang: str = DEFAULT_LANG


@app.get("/api/orchestrator")
def orchestrator_status() -> dict:
    """Which model is driving, and whether it is reachable."""
    client = _orchestrator().client
    return {
        **client.describe(),
        "tools": [t["function"]["name"] for t in TOOL_SCHEMAS],
        "max_steps": _orchestrator().max_steps,
        "mode": "sealion" if client.configured else "fallback",
        "hint": ("Set SEALION_API_KEY to enable SEA-LION orchestration; "
                 "without it Racik answers with a rule-based planner."),
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


# ---------------------------------------------------------------- serialise


def _serialise(result: PlanResult, lang: str = DEFAULT_LANG) -> dict:
    store = _store()
    portions = result.request.portions
    targets = result.targets

    days = []
    for day in result.days:
        slots = {}
        for slot in SLOTS:
            dish_ = day.dishes[slot]
            slots[slot] = None if dish_ is None else {
                **dish_.to_dict(),
                "main_food": dish_.main_food_name,
                "cost_total_idr": round(dish_.cost_per_portion_idr * portions),
                "steps": [s.strip() for s in (dish_.steps or "").split(".")
                          if s.strip()][:8],
            }
        days.append({
            "index": day.day_index,
            "label_id": DAY_LABELS[day.day_index % 7],
            "label_en": DAY_LABELS_EN[day.day_index % 7],
            "cost_per_portion_idr": round(day.cost_per_portion_idr),
            "cost_total_idr": round(day.cost_per_portion_idr * portions),
            "adequacy": round(result.adequacy(day), 3),
            "nutrients": {k: round(v, 2) for k, v in day.nutrients.items()},
            "compliance": _compliance(day.nutrients, targets, lang),
            "slots": slots,
        })

    return {
        "summary": result.summary(),
        "band": {"key": result.band.key, "label_id": result.band.label_id,
                 "label_en": result.band.label_en},
        "targets": {k: round(v, 1) for k, v in targets.items()},
        "days": days,
        "relaxations": [
            {"day": r.day_index, "nutrient": r.nutrient,
             "label_id": NUTRIENT_META[r.nutrient][0],
             "label_en": NUTRIENT_META[r.nutrient][1],
             "unit": unit(lang, NUTRIENT_META[r.nutrient][2]),
             "shortfall": round(r.shortfall, 2), "target": round(r.target, 2),
             "share": round(r.share, 3)}
            for r in result.relaxations
        ],
        "notes": _notes(result, lang),
        "lang": lang,
    }


def _compliance(nutrients: dict, targets: dict,
                lang: str = DEFAULT_LANG) -> list[dict]:
    """Per-nutrient attainment, keeping verified and advisory values apart."""
    rows = []
    for key, (label_id, label_en, unit_symbol, status) in NUTRIENT_META.items():
        target = targets.get(key)
        if not target:
            continue
        value = nutrients.get(key, 0.0)
        rows.append({
            "key": key, "label_id": label_id, "label_en": label_en,
            "unit": unit(lang, unit_symbol), "value": round(value, 1),
            "target": round(target, 1),
            "pct": round(value / target * 100),
            "binding": key in BINDING_NUTRIENTS,
            "verified": status == "verified",
        })
    return rows


def _notes(result: PlanResult, lang: str = DEFAULT_LANG) -> list[str]:
    """Delegates to report.plan_notes so both surfaces say the same thing."""
    return plan_notes(result, lang)


# ---------------------------------------------------------------- static UI

if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(UI_DIR / "index.html")


_ARCHITECTURE_SVG = PROJECT_DIR / "docs" / "architecture.svg"

if _ARCHITECTURE_SVG.exists():
    @app.get("/architecture.svg", include_in_schema=False)
    def architecture() -> FileResponse:
        """The system diagram, served from docs/ so there is one copy of it."""
        return FileResponse(_ARCHITECTURE_SVG, media_type="image/svg+xml")
