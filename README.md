# Racik

An AKG-grounded, cost-constrained menu planner for Indonesia's **Makan
Bergizi Gratis** (MBG) program — built for SPPG kitchen coordinators, not
engineers.

**This branch (`hackathon-mvp`) is the one to look at.** It has the real
planning engine (CP-SAT solver, 18,000+ recipe corpus, official AKG 2019 /
TKPI 2020 data) plus a friendly, agent-first UI on top of it. Everything here
actually runs — see `racik/README.md` for the full technical write-up
(architecture, data pipeline, API, tests) and `racik/docs/CODE_MAP.md` for a
guided reading order through the codebase.

## Quick start

```bash
cd racik
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/build_db.py          # builds data/racik.db from the raw corpus, ~20s
python -m uvicorn racik.api:app --port 8000
# open http://127.0.0.1:8000
```

Optional: `export SEALION_API_KEY=...` to enable live SEA-LION orchestration.
Without it, the app runs on a deterministic rule-based fallback that uses the
exact same tools and returns the exact same numbers — narrower, still
trustworthy, never a blank page.

## What makes this an agentic solution, not a solver with a chatbot bolted on

The primary "Build menu" action in the UI does **not** call the solver
directly — it goes through the same natural-language orchestrator as the
"Ask Racik" chat box (`/api/ask`), which reads the request, decides which
tool to call, and hands back a reasoning trace shown right in the result
panel ("How Racik built this menu"). A second, separately-prompted agent
reviews ingredient availability after a plan exists (a Reflection Pattern —
Planner generates, Reviewer checks against a constraint the Planner never
saw). Neither agent computes a number itself — every gram, rupiah, and
adequacy percentage comes from a deterministic tool call, never a model
guess.

## Repo history / other branches

- `main` — the original static frontend prototype (illustrative data, no
  real backend). Kept for reference; superseded by this branch.
- `racik-engine` — the real engine as first built (CP-SAT solver, TKPI/AKG
  data, SEA-LION orchestrator), with a functional but dense, engineer-facing
  UI. This branch (`hackathon-mvp`) builds on it directly — same engine, same
  data, with the primary flow routed through the agent, a friendlier result
  view, editable nutrition targets, cross-session menu variety, and the
  ingredient-substitution Reviewer agent added on top.
