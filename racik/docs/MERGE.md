# The merge — two codebases, one engine

Two RACIK implementations were built in parallel against the same brief: this
one, and a Supabase-backed build on the `claude-supabase-build` branch. They
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
