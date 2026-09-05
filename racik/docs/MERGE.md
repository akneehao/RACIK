# The merge — three codebases, one engine

Three RACIK implementations were built in parallel against the same brief.
This document records both merges so neither is re-litigated.

- **Merge 1** folded in a Supabase-backed build (`claude-supabase-build`).
- **Merge 2** folded in the `aditi` branch, which had diverged from the same
  ancestor as this one and built genuinely different things on top.

## Merge 1 — the Supabase build

That build and this one
reached the same core conclusion independently — **the deterministic engine owns
every number and the language model owns none of them** — and split the nutrients
into enforced and advisory tiers for the same reason.

This engine is the base. It was further along on nearly every axis, and the
comparison is worth recording so nobody re-litigates it:

| | this engine | the other build |
|---|---|---|
| Ingredient lines resolved | **99.98%** of 260,734 | 98.5% accepted |
| Usable dishes | **17,936 / 18,133** | ~81% of ingredient mass linked |
| Vegetable candidates | **826** | ~240 |
| Tests | **202** | 93 |
| Cooking losses | retention factors, frying-oil absorption cap | not modelled |
| Yield | estimated, declared through `DishQuality` | sidestepped via per-100g templates |
| No solution | **soft floors** — always a menu, plus what it relaxed | relaxation ladder that could still fail |
| Deployment | Render, Docker, HF Spaces | none |
| Language | bilingual ID/EN | English only |

Most of the other build was therefore redundant and was deleted rather than
merged. Three things survived, and only because they answer questions this
codebase could not answer from its own data.

## 1. Measurement provenance — `data/nutrient_quality.json`

The shipped `TKPI_2020_Table_4_All_Data.csv` carries values but not their
provenance: a number measured in a lab and a number inferred from a similar food
are indistinguishable in it. A separately maintained copy of the same table
carries a per-value `is_imputed` flag.

That flag moved one nutrient across the binding line. **Fibre is a macro, so it
used to bind, and only 68% of its values were measured.** Sodium is 53%, zinc
47%. A hard floor on a mostly-inferred column is optimised against noise, and
nothing downstream disagrees because every layer reads the same column.

It also exonerates two: calcium and iron are 99.6% and 99.3% measured, so the
food data there is sound and only the AKG reference figure is in doubt.

`akg.py` now requires both tests — a trusted target *and* a measured column.
`scripts/build_nutrient_quality.py` regenerates the file; the engine only ever
reads it.

## 2. `scripts/province_sweep.py`

Soft floors are the right behaviour and they hide something. A solve always
returns a menu, so a province with a thin dish pool produces a plan that looks
like everyone else's — the concessions are in `PlanResult.relaxations` and
nowhere a person would look. The sweep plans every province and prints what each
one relaxed.

## 3. Nothing else

An infeasibility-core diagnostic was ported and then dropped: it extracts the
conflicting constraint subset from CP-SAT via assumption literals, which is
genuinely useful against **hard** floors and pointless against soft ones. The
design decision upstream had already removed the problem.

The other build's parser, linker, optimiser, agents, API and frontend were all
superseded by their counterparts here.

## What was learned from the other build's failures

Two findings are worth keeping even though the code was discarded, because they
are the kind of thing that recurs:

- **A rule invented for tidiness made 26 of 33 provinces infeasible.** Requiring
  five *distinct* vegetables across a five-day plan is not how a kitchen works,
  and outside Java it was unsatisfiable. This engine avoids it structurally by
  making variety a penalty rather than a constraint.
- **Adding constraints one at a time finds the wrong culprit.** When two
  constraints conflict, the one added second gets blamed. CP-SAT's
  `SufficientAssumptionsForInfeasibility` names the real pair.

---

# Merge 2 — the `aditi` branch

`aditi` and `valeskha` both descend from `6e69935` ("Add Racik planning engine
+ bilingual UI under racik/"). Neither is a superset of the other: `valeskha`
added deployment, a tray cache, the styled operator frontend and brand assets;
`aditi` added a redesigned UI and four features the engine did not have.

Everything from `aditi` was kept. Nothing was dropped as redundant, because
none of it overlapped.

## What came across

| From `aditi` | What it does |
|---|---|
| `history.py` | Per-scope served log + **1–5 star ratings**, combined into a soft repetition weight |
| `substitution.py` | Reviewer agent: classifies an ingredient core vs flexible, proposes swaps from real lookups only |
| `recipes.py` | Recipe Workshop — a school-authored dish becomes a real solver candidate |
| `bedrock_native.py` | Bedrock Converse against a stock catalog model |
| `optimizer.py` | `recency_weights`, `extra_dishes`, `target_overrides` |
| `ui/index.html` | The agent-first single-file UI, now mounted at `/agent` |

## The ratings feature, and the half of it that was missing

The headline feature is that **an operator's star rating changes what gets
served next**. `history.py` implements it as

    weight = time_decay(days since last served) x RATING_MULTIPLIER[stars]

with multipliers `{1: 1.5, 2: 1.2, 3: 1.0, 4: 0.5, 5: 0.15}` — a 5-star dish
comes back roughly seven times sooner than a 1-star one. The optimizer applies
that weight as a soft penalty, never a ban.

Two gaps had to be closed before it worked outside `aditi`'s own UI:

1. **Nothing recorded what was served on the `/api/generate` path.**
   `recency_weights()` walks the served log and looks the rating up per row,
   so an empty log returns `{}` no matter how many ratings exist. Only
   `/api/plan` recorded, and the primary frontend calls `/api/generate`. Every
   star an operator clicked there was silently discarded.
   `RacikOrchestrator._record_rating_history()` now records on both paths,
   filtering synthetic component ids the same way the served log does.

2. **The primary frontend had no rating control.** `utils.js` shipped a
   `setupStarRating()` that toggled a CSS class, posted nothing, and had zero
   callers. It was replaced with `renderDishRating()` in `plan.js`, which posts
   to `/api/rate` scoped by province and stage — the same key `history.py`
   uses, so one region's verdict cannot push a dish out of another's rotation.

`tests/test_pipeline.py` now asserts all three properties: that generate
records, that a 1-star rating raises the avoidance weight while an unrated
dish stays put, and that ratings do not leak across provinces.

## Conflicts and how they were resolved

Eight files conflicted. The rule throughout was to keep both behaviours where
they were additive and to disambiguate where they collided.

| File | Resolution |
|---|---|
| `api.py` | Union. Kept `serialize.py` over the inline serialiser, plus `aditi`'s history recording, all four singletons, and both `mode` and `llm_configured` |
| `bedrock.py` | **Name collision.** `bedrock` meant Converse in one branch and Custom Model Import in the other. Now dispatches on which variable is set: `BEDROCK_MODEL_ARN` -> imported SEA-LION, `BEDROCK_MODEL_ID` -> Converse, `BEDROCK_NATIVE_MODEL_ID` -> `bedrock_native`. Both existing configurations keep working untouched |
| `orchestrator.py` | Both constructor params kept (`price_table`, `history`) |
| `i18n.py` | `valeskha`'s colon separator (a deliberate change) + `aditi`'s `plan.relax_summary` keys |
| `conftest.py` | HEAD's structure, unioned env-var list (16 entries) |
| `requirements.txt` | `boto3` promoted to required; `httpx` kept over `httpx2` |
| `README.md`, `.env.example` | Rewritten to document the union, including the provider disambiguation above |

## Two bugs the merge itself introduced, and what they cost

Both were caught by the suite, and both are the same shape — a resolution that
was locally right and globally wrong.

- **`_compliance` was deleted with the inline serialiser, but `/api/swap`
  still called it.** A `NameError` on every swap. The fix was to point it at
  `serialize.compliance_rows`.
- **`/api/swap` also had its own copy of the slot-payload construction**,
  which had already drifted from `serialize.py`'s during the merge. Extracted
  as `serialize.slot_payload()` so the two cannot diverge again.

A third, in the test fixture rather than the code: `_orchestrator()` is
`lru_cache`d and takes its `PlanHistory` at construction, so a fixture that
swapped `_history` per test still handed back an orchestrator bound to the
previous test's — already closed — database. The fixture now clears that cache
on both sides of the yield.

## What the two frontends are for

Both are served and both are real, because they answer different questions.

- **`/`** — the operator workflow: a tab per stage (onboarding, plan, day
  detail, procurement, stock audit), ES modules, export to PNG/PDF. This is
  the one a kitchen would actually use for a week of service.
- **`/agent`** — the agent-first UI: the primary action goes through
  `/api/ask`, so the reasoning trace is the interface rather than a panel
  inside it. Also home to the Recipe Workshop and the substitution Reviewer.

Two things were ported from `/agent` into `/` rather than replacing it: the
star rating described above, and the quick-pick restriction chips (which write
Indonesian terms into the existing notes field, because `exclude_terms` is a
text filter against Indonesian dish names — an English chip would match
nothing).
