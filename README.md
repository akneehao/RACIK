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
school-meal program. An SPPG kitchen operator enters a location, a budget,
a headcount and free-text notes; Racik plans a multi-day menu that meets AKG
2019 nutrient floors under the MBG per-portion budget, explains why each dish
was chosen, and hands back scaled recipes and a shopping list.

This repo has two parts:

- **`racik/`** — the planning engine: an 18k-recipe corpus turned into a
  costed, AKG-scored dish index; a CP-SAT menu optimiser; two LLM-backed
  planning agents (**Agen Gizi** for nutrition, **Agen Biaya** for budget)
  plus a deterministic **Validator**; and persistence for operator review,
  menu-history rotation, and stock/cost audit. Full detail in
  [`racik/README.md`](racik/README.md), and a guided reading order through
  the code in [`racik/docs/CODE_MAP.md`](racik/docs/CODE_MAP.md).
- **`index.html` / `css/` / `js/`** — the operator-facing frontend (the
  styled UI shown in the product mockups), served by the same FastAPI app
  as the primary interface. The agent-first single-file UI — where "build
  menu" goes through the orchestrator rather than straight to the solver —
  is mounted alongside it at `/agent`.

## What makes this agentic, not a solver with a chatbot bolted on

Building a menu never goes straight to the solver. **Agen Gizi** reads the
operator's free-text notes and the age band and authors the nutrition
constraint set; **Agen Biaya** authors the budget and regional cost
constraints; CP-SAT then selects against what they wrote, and a
deterministic **Validator** recomputes the result independently and fails
loudly if the two disagree. Every run returns that trace — `preprocessing →
agen_gizi → agen_biaya → cp_sat → validator` — and the UI shows it. The
`/agent` UI additionally routes the whole thing through a natural-language
orchestrator (`/api/ask`), and adds a separately-prompted **Reviewer** that
checks ingredient availability against a finished plan: a reflection
pattern, where the planner generates and a reviewer checks against a
constraint the planner never saw.

Neither agent ever computes a number. Every gram, rupiah and adequacy
percentage comes from a deterministic tool call, and every agent-authored
figure is clamped into a band derived from AKG before the solver sees it —
an agent is an author within bounds, never an authority. That split is what
makes a hard nutrition floor safe to put an LLM in front of.

## Quickstart

```bash
cd racik
python -m venv .venv && .venv/Scripts/activate      # or source .venv/bin/activate on Linux/Mac
pip install -r requirements.txt
python scripts/build_db.py                          # one-time ETL, ~20-30s
python -m uvicorn racik.api:app --port 8000         # from inside racik/
```

Open `http://localhost:8000`. No API key or AWS credentials are required —
without them, Agen Gizi/Agen Biaya and the orchestrator fall back to a
deterministic, non-LLM path that uses the same tools and returns the same
numbers, so the app is fully demoable with zero configuration.

To enable a live LLM, the fastest path needs no AWS account at all:

```bash
export RACIK_LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=<a key from console.anthropic.com>
```

or, with AWS Bedrock access:

```bash
export RACIK_LLM_PROVIDER=bedrock
export BEDROCK_MODEL_ID=<a model id enabled in your AWS account/region>
export AWS_REGION=<region>
# plus standard AWS credentials: env vars, ~/.aws/credentials, or an IAM role
```

`racik/.env.example` documents every provider — including hosted SEA-LION,
SEA-LION imported into Bedrock, and the Bedrock Access Gateway — along with
the two credential traps that bite during a live demo. Architecture, the
CP-SAT rubric and the honest limitations list are in
[`racik/README.md`](racik/README.md).

## Deploying

- [`deploy/huggingface-spaces.md`](deploy/huggingface-spaces.md) — free, no
  credit card, deploys the existing `Dockerfile` as-is.
- [`deploy/README.md`](deploy/README.md) — AWS App Runner, if you'd rather
  stay on AWS end to end.

## Tests

```bash
cd racik && python -m pytest tests -q
```

No network or API key required.
