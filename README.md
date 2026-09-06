---
title: Racik
emoji: 🍚
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 8000
pinned: false
---

# Racik

AI-powered meal planning for Indonesia's **Makan Bergizi Gratis** (MBG) free
school-meal programme. An SPPG kitchen operator enters a location, a school
level, a budget and a headcount; Racik plans a multi-day menu that meets AKG
2019 nutrient floors under the MBG per-portion budget, explains why each dish
was chosen, and hands back scaled recipes, a shopping list and a printable
compliance report.

Python + FastAPI throughout. The solver is Google OR-Tools CP-SAT; the agents
run on **AWS Bedrock**, and the whole app also runs with no model configured
at all.

---

## 1. Running it

**Requirements:** Python 3.12 or 3.13 (the Docker image pins 3.12; the test
suite runs on 3.13). No database server, no network access needed.

```bash
git clone <this repo> && cd RACIK

python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cd racik
python scripts/build_db.py           # one-time ETL: builds data/racik.db, ~30 s
python -m uvicorn racik.api:app --port 8000
```

Open **http://localhost:8000**.

Nothing else is required. With no API key and no AWS credentials the two
planning agents and the orchestrator fall back to a deterministic, non-LLM
path that calls the same tools and returns the same numbers — every figure in
the app is computed by the engine either way, so it is fully demoable
unconfigured. What a model adds is the *prose*: English recipe steps, dish-name
glosses, and free-text understanding.

### Docker

```bash
docker build -t racik .
docker run -p 8000:8000 --env-file .env racik
```

The image runs `build_db.py` at build time, so the container starts ready.

---

## 2. Environment setup

### Virtual environment

`requirements.txt` at the repo root includes `racik/requirements.txt`, so
`pip install -r requirements.txt` works from either directory. Direct
dependencies: `ortools`, `fastapi`, `uvicorn`, `rapidfuzz`, `pandas`,
`openpyxl`, `boto3`, `python-dotenv`, `httpx`, `pytest`.

### Paths

No `PYTHONPATH` or environment path variable is needed. Every path is derived
from the package location in [`racik/racik/config.py`](racik/racik/config.py):

```python
PKG_DIR     = Path(__file__).resolve().parent   # racik/racik/
PROJECT_DIR = PKG_DIR.parent                    # racik/
DATA_DIR    = PROJECT_DIR / "data"
```

The server must be started from inside `racik/` (`python -m uvicorn
racik.api:app`) so that `racik` resolves as a package. Every script in
`racik/scripts/` derives its own paths from `__file__` — and bootstraps
`sys.path` where it imports the package — so those run from any directory.

### Secrets and keys

Two `.env` files are read at startup, both gitignored:

| File | Holds |
|---|---|
| `racik/.env` | Provider routing — model id and region. No secrets. Template: [`racik/.env.example`](racik/.env.example) |
| `.env` (root) | The AWS credentials themselves, plus Supabase for one data script |

`racik/.env` is loaded first and wins on any shared key. The loader in
`config.py` accepts `NAME=value`, `export NAME=value` and Windows'
`SET NAME=value` — the AWS access portal hands out the last form, which
`python-dotenv` silently skips.

To enable a live model, use Bedrock Model:

```bash
# racik/.env — routing
RACIK_LLM_PROVIDER=bedrock
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
AWS_REGION=us-east-1

# .env — credentials
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...        # SSO tokens expire 8-12 h after issue
```

---

## 3. What it does

**Planning**

- Multi-day menus solved by **CP-SAT** against AKG 2019 floors, the MBG
  per-portion budget, and the five-slot *Isi Piringku* tray (staple, animal
  protein, plant protein, vegetable, fruit).
- **Soft floors.** A tight budget returns a menu plus a list of what it had to
  relax, never a blank page.
- **Regional preference** across all 33 provinces, with island-group fallback
  for thin corpora, and per-province cost indices.
- **Editable AKG targets** and a school-level selector (PAUD / SD / SMP / SMA)
  — an operator's typed number replaces the AKG figure for that nutrient.
- **Repair a short day** (`/api/improve-day`): re-solves one day with the
  nutrient floors put *above* the budget ceiling, and reports what that costs.

**Agents**

- **Agen Gizi** authors the nutrition constraint set from free-text notes and
  the age band; **Agen Biaya** authors the budget and regional cost
  constraints; a deterministic **Validator** recomputes the solved plan by a
  different code path and fails loudly if the two disagree.
- **Orchestrator** (`/api/ask`) — natural-language planning with a bounded
  tool loop and a visible trace.
- **Substitution Reviewer** — a separately-prompted second agent that judges
  whether an ingredient is core to a dish and proposes replacements from real
  corpus lookups. A reflection pattern: the planner generates, a reviewer
  checks against a constraint the planner never saw.

**Kitchen loop**

- **Operator review** — accept/reject a day, with a one-day re-solve that
  excludes what was rejected.
- **5-star ratings** that change repetition: a well-rated dish returns sooner,
  a poorly-rated one is pushed further out.
- **Menu-history rotation** — a 14-day decaying window, not a permanent ban.
- **Pantry** — confirmed leftover stock is nudged into the next plan.
- **Recipe Workshop** — a school-authored dish is costed, AKG-scored and
  becomes a genuine solver candidate.
- **Procurement** and **Stock & audit** — shopping lists, then received/used/
  actual-cost records per ingredient.

**Output**

- Scaled recipes with **professional English preparation steps**, rewritten
  from scraped Indonesian home-cook prose by an LLM and cached per dish.
- Printable bilingual **compliance report**, PNG/PDF tray export.
- Full **ID/EN** interface.

### What makes it agentic, not a solver with a chatbot on top

Building a menu never goes straight to the solver: the agents author the
constraints, CP-SAT selects against what they wrote, and the Validator checks
the result independently. Every run returns that trace — `preprocessing →
agen_gizi → agen_biaya → cp_sat → validator` — and the UI shows it.

Neither agent ever computes a number. Every gram, rupiah and adequacy
percentage comes from a deterministic tool call, and every agent-authored
figure is clamped into a band derived from AKG before the solver sees it. An
agent is an author within bounds, never an authority. That split is what makes
a hard nutrition floor safe to put a language model in front of.

---

## 4. Repository layout

### Engine — `racik/racik/`

| File | Purpose |
|---|---|
| `config.py` | Programme constants, paths, and the `.env` loader |
| `akg.py` | AKG 2019 targets per school stage; the binding/advisory nutrient tiers |
| `tkpi.py` | TKPI 2020 food composition — grams to nutrients |
| `urt.py` | Indonesian household measures (*ukuran rumah tangga*) to grams |
| `prices.py` | Ingredient prices, rupiah per kg, and per-province cost indices |
| `nutrition.py` | Recipe → a costed, nutrition-bearing dish |
| `store.py` | Read layer over `racik.db` |
| `optimizer.py` | **CP-SAT menu optimiser** — candidate rubric, soft floors, objective |
| `agents.py` | **Agen Gizi, Agen Biaya, Validator** |
| `orchestrator.py` | Tool-calling agent loop behind `/api/ask` and `/api/generate` |
| `substitution.py` | The Substitution Reviewer agent |
| `recipes.py` | Recipe Workshop — raw ingredient text to a real costed dish |
| `history.py` | Served-dish memory, 5-star ratings, pantry |
| `statedb.py` | Operator review, menu history, stock/audit persistence |
| `procurement.py` | Menu → shopping list |
| `report.py` | Compliance and procurement report |
| `serialize.py` | `PlanResult` → the JSON shape the API returns |
| `i18n.py` | Bilingual strings for server-generated prose |
| `translate.py` | Dish names → English glosses |
| `recipe_text.py` | Scraped Indonesian steps → professional English |
| `api.py` | **FastAPI app**: 28 endpoints plus static hosting for both UIs |
| `bedrock.py`, `bedrock_converse.py` | **The provider in use.** `bedrock.make_client()` routes from `RACIK_LLM_PROVIDER` |
| `bedrock_native.py`, `sealion.py`, `anthropic_client.py` | Alternate provider clients the factory can also return |

### Frontend — `index.html`, `css/`, `js/`

The primary operator UI, served by the same FastAPI app at `/`. Plain ES
modules, no build step.

| File | Purpose |
|---|---|
| `js/main.js` | Entry point |
| `js/state.js` | Single shared source of truth |
| `js/api.js` | Fetch wrapper for every endpoint the frontend calls |
| `js/onboarding.js` | Location, duration, budget, headcount, school level, targets |
| `js/plan.js` | Weekly tray and day detail — the largest module |
| `js/procurement.js` | Shopping-list recaps |
| `js/inventory.js` | Stock & audit records |
| `js/settings.js` | Programme parameters and the feedback log |
| `js/shell.js`, `js/utils.js`, `js/icons.js` | Sidebar shell, helpers, slot icons |

A second, agent-first single-file UI — where "build menu" goes through the
orchestrator rather than straight to the solver — is mounted at **`/agent`**
from `racik/ui/index.html`.

### Data pipeline — `racik/scripts/`

| Script | Purpose | Network |
|---|---|---|
| `build_db.py` | **Required once.** Builds `data/racik.db` from the raw TKPI table and the 18k-recipe corpus | no |
| `build_prices.py` | Derives ingredient prices and per-province cost indices | no |
| `precompute_trays.py` | Bank of verified single-day trays for the low-CPU demo host | no |
| `province_sweep.py` | Plans every province and reports what each relaxed | no |
| `build_nutrient_quality.py` | Regenerates `data/nutrient_quality.json` from an annotated TKPI copy | **yes** (Supabase) |
| `package.py` | Builds the shippable per-language bundles into `dist/` | no |

### Everything else

| Path | Purpose |
|---|---|
| `racik/data/` | Raw sources + generated `racik.db`; runtime state is gitignored |
| `racik/tests/` | 301 tests |
| `racik/docs/CODE_MAP.md` | Guided reading order through the engine |
| `racik/docs/WORKFLOW.md` | The pipeline, stage by stage |
| `Dockerfile`, `.dockerignore`, `render.yaml` | Container and Render blueprints |
| `deploy/` | Hugging Face Spaces and AWS App Runner guides, IAM policy |

---

## 5. Tests

```bash
cd racik && python -m pytest tests -q          # 301 tests
```

No network, no API key, no fixtures to download. Coverage is deliberately
weighted toward the places where a silent error is dangerous — unit
conversion, nutrient composition, the solver's constraints, and the agent
guardrails — rather than spread evenly.

| File | Covers |
|---|---|
| `test_racik.py` | Units, composition, pricing, the solver's constraints |
| `test_pipeline.py` | `/api/generate` end to end, review, ratings, improve-day |
| `test_orchestrator.py` | Tool loop, bounded steps, fallback path |
| `test_agents.py` | Agen Gizi / Agen Biaya clamping, the Validator |
| `test_history_and_substitution.py` | Ratings, recency, pantry, the Reviewer |
| `test_nutrient_quality.py` | The binding/advisory nutrient tiers |
| `test_recipe_text.py` | The no-model step-cleanup fallback, provider portability |
| `test_transparency.py` | Candidate-filter explanations, translation |
| `test_statedb.py`, `test_i18n.py` | Persistence, bilingual strings |
| `test_bedrock_*.py` | The Bedrock provider clients |

**Known flakiness:** a handful of tests give CP-SAT an 8–10 second wall-clock
budget and assert a solution comes back. On a loaded machine the solver
occasionally returns `UNKNOWN` inside that budget and one or two tests fail —
a different one or two each run. They pass on re-run; the assertion is about
the solver's speed, not its correctness.

---

## 6. Deploying

- [`deploy/huggingface-spaces.md`](deploy/huggingface-spaces.md) — free, no
  credit card, deploys the existing `Dockerfile` as-is.
- [`deploy/README.md`](deploy/README.md) — AWS App Runner, to stay on AWS end
  to end. IAM policy in `deploy/iam-bedrock-policy.json`.
- `render.yaml` — Render blueprint.

---

## Sources

AKG 2019 (Permenkes 28/2019, transcribed in `racik/akg.py`) · TKPI 2020
(Tabel Komposisi Pangan Indonesia) · an 18,133-recipe regional corpus ·
WFP Indonesia food-price series.

**Honest limitations.** Micronutrient targets (calcium, iron, zinc, vitamins A
and C) are *advisory*, not enforced: secondary sources disagree on the AKG
figures, and fibre and sodium are additionally under-measured in TKPI — see
`data/nutrient_quality.json` and the binding/advisory split in `akg.py`.
Prices are a reference table with a fallback ladder, not live market data.
Recipe yields are estimated from ingredient mass, since the corpus records no
serving counts.
