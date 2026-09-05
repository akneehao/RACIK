"""The Substitution Reviewer — a second, separately-prompted agent.

Racik's Planner (orchestrator.py) chooses a menu against AKG floors, budget,
and variety. This module answers a different, later question a kitchen asks
*after* that plan exists: "we don't have this ingredient today — now what?"
That's not a re-optimisation, it's a judgment call over one ingredient, and
it gets its own agent with its own prompt — the same reasoning that already
separates translate.py's prompt from orchestrator.py's. Planner generates,
Reviewer checks the plan against a constraint the Planner never saw (today's
actual stock) and patches it. This is a Reflection Pattern, not a relabel of
an existing tool: the two agents ask genuinely different questions.

The judgment is the only part handed to the model. Whether an ingredient is
structurally load-bearing for the dish (a protein that defines the slot) or
a minor/aromatic component, and what real substitutes exist, are computed
first, in plain Python, from TKPI's food-group table — the same
"the model never calculates" contract as everywhere else in Racik. A model
that is not configured, or that fails, falls back to a deterministic answer
built from the same lookup, same as orchestrator.py's rule-based path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .i18n import norm_lang
from .sealion import SeaLionClient, SeaLionError
from .store import RacikStore
from .translate import _parse_json_object  # shared strict-JSON parser

# A line at or above this share of a dish's gross mass is structural to it —
# the same order of magnitude as the slot-classification thresholds in
# nutrition.py's _classify() (sayur >=0.50, staple >=0.55, protein >=0.18-0.22).
CORE_SHARE_THRESHOLD = 0.15

SYSTEM_PROMPT = """\
You are Racik's availability reviewer. A kitchen has told the planner an \
ingredient is missing today, after a menu was already planned. Your only \
job is to say what happens to *this one ingredient*, not to replan the \
menu — that already happened.

You are given:
- whether the ingredient is structural to the dish ("core") or a minor \
seasoning/aromatic component ("flexible") — already decided in code from \
its share of the dish's mass, you do not re-decide this.
- if core, a short list of real substitute ingredients from the same TKPI \
food group, with their macros, already looked up in the database.

Rules:
- If flexible: the action is always "drop". Say it is safe to omit, and \
name any minor effect on flavour or texture if relevant. Never propose a \
substitute for a flexible ingredient.
- If core: choose exactly one substitute by its "code" field from the list \
you were given. Never propose a food that is not in that list — if none \
of them fit, set substitute_code to null and say so instead of inventing \
one.
- Reply in the requested language.
- Return a JSON object only, no prose outside it, no markdown fence: \
{"action": "drop" | "substitute", "substitute_code": "<code or null>", \
"reason": "<one sentence>"}
"""


@dataclass
class SubstitutionResult:
    dish_id: int
    dish_name: str
    ingredient: str
    is_core: bool
    mass_share: float
    action: str                    # "drop" | "substitute" | "not_found"
    substitute: Optional[dict]     # {"code","name","energy_kcal","protein_g"} or None
    candidates: list[dict]         # every option the model/fallback could pick from
    reason: str
    source: str                    # "sealion" | "fallback"

    def to_dict(self) -> dict:
        return {
            "dish_id": self.dish_id, "dish_name": self.dish_name,
            "ingredient": self.ingredient, "is_core": self.is_core,
            "mass_share": round(self.mass_share, 3), "action": self.action,
            "substitute": self.substitute, "candidates": self.candidates,
            "reason": self.reason, "source": self.source,
        }


@dataclass
class _CustomLineView:
    """Adapts a freshly computed IngredientLine (recipes.py, not persisted
    into the corpus store's dish_lines table) to the flat name/raw/gross_g/
    tkpi_code shape _review_core expects from a StoredLine."""

    _line: object

    @property
    def name(self) -> str:
        return self._line.name

    @property
    def food_name(self) -> str:
        return self._line.food_name

    @property
    def raw(self) -> str:
        return self._line.parsed.raw

    @property
    def gross_g(self) -> float:
        return self._line.gross_g

    @property
    def tkpi_code(self) -> Optional[str]:
        return self._line.match.food.code if self._line.matched else None


class SubstitutionAgent:
    """The Reviewer half of the Planner -> Reviewer pair."""

    def __init__(self, store: RacikStore, client: Optional[SeaLionClient] = None):
        self.store = store
        self.client = client or SeaLionClient()

    def review(self, dish_id: int, ingredient: str,
              lang: str = "id") -> SubstitutionResult:
        dish = self.store.dish(dish_id)
        if dish is None:
            raise ValueError(f"dish {dish_id} not found")
        lines = self.store.lines(dish_id)
        return self._review_core(dish, lines, ingredient, lang)

    def review_custom(self, dish, ingredient: str,
                      lang: str = "id") -> SubstitutionResult:
        """Same review, for a Recipe Workshop dish (recipes.py) that was
        never persisted into the corpus store — it can still end up
        selected into an actual plan (extra_dishes' guaranteed inclusion),
        so it needs the same "ingredient missing today" path any corpus
        dish gets. Its lines are freshly computed IngredientLine objects
        rather than the store's flattened StoredLine rows, hence the
        adapter below instead of a second SQL fetch."""
        lines = [_CustomLineView(ln) for ln in dish.lines]
        return self._review_core(dish, lines, ingredient, lang)

    def _review_core(self, dish, lines, ingredient: str,
                     lang: str) -> SubstitutionResult:
        lang = norm_lang(lang)
        dish_id = dish.dish_id
        total_mass = sum(l.gross_g for l in lines) or 1.0

        needle = ingredient.strip().lower()
        matches = [l for l in lines if needle and
                  (needle in l.name.lower() or needle in (l.raw or "").lower())]
        # Several lines can share a substring ("ayam" also hits "air kaldu
        # ayam", chicken broth) — the largest match by mass is what a kitchen
        # means when it says an ingredient is missing, not an incidental
        # mention inside a compound ingredient's name.
        line = max(matches, key=lambda l: l.gross_g) if matches else None
        if line is None:
            return SubstitutionResult(
                dish_id, dish.name, ingredient, False, 0.0, "not_found", None,
                [], f"'{ingredient}' does not appear in {dish.name}.",
                "fallback")

        share = line.gross_g / total_mass
        is_core = bool(share >= CORE_SHARE_THRESHOLD
                       or (line.tkpi_code and line.tkpi_code == dish.main_food_code))
        candidates = self._candidates(line.tkpi_code) if is_core else []

        if self.client.configured:
            try:
                return self._ask_model(dish, line, is_core, share, candidates, lang)
            except SeaLionError:
                pass  # degrade to the deterministic path below

        return self._fallback(dish, line, is_core, share, candidates, lang)

    # ------------------------------------------------------------ candidates
    def _candidates(self, tkpi_code: Optional[str], limit: int = 5) -> list[dict]:
        if not tkpi_code:
            return []
        # Same food group is not enough: TKPI's group_code mixes raw
        # ingredients with composite/prepared products (e.g. corn and
        # "Martabak Mesir" are both group A, Serealia). A kitchen shopping
        # for a substitute needs the same *kind* of thing — raw-for-raw,
        # never a finished dish standing in for one of its own ingredients —
        # so `jenis` (TUNGGAL/SINGLE vs OLAHAN/PRODUK/KOMPOSIT) has to match
        # too. See tests/test_history_and_substitution.py for the case this
        # was found from.
        rows = self.store.conn.execute(
            "SELECT code, name, group_label, energy_kcal, protein_g, fat_g "
            "FROM foods WHERE code != ? AND group_code = "
            "(SELECT group_code FROM foods WHERE code = ?) "
            "AND jenis = (SELECT jenis FROM foods WHERE code = ?) "
            "ORDER BY ABS(protein_g - (SELECT protein_g FROM foods WHERE code = ?)) "
            "LIMIT ?",
            (tkpi_code, tkpi_code, tkpi_code, tkpi_code, limit)).fetchall()
        return [
            {"code": r["code"], "name": r["name"], "group": r["group_label"],
             "energy_kcal": round(r["energy_kcal"] or 0, 1),
             "protein_g": round(r["protein_g"] or 0, 1),
             "fat_g": round(r["fat_g"] or 0, 1)}
            for r in rows
        ]

    # ------------------------------------------------------------ model path
    def _ask_model(self, dish, line, is_core, share, candidates,
                   lang: str) -> SubstitutionResult:
        payload = {
            "dish": dish.name, "ingredient": line.food_name,
            "share_of_dish_mass": round(share, 3),
            "classification": "core" if is_core else "flexible",
            "candidates": candidates, "language": lang,
        }
        import json
        reply = self.client.chat(
            [{"role": "system", "content": SYSTEM_PROMPT},
             {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            temperature=0.0, max_tokens=400)
        parsed = _parse_json_object(reply.content) or {}

        action = parsed.get("action")
        code = parsed.get("substitute_code")
        reason = str(parsed.get("reason") or "").strip()
        valid_codes = {c["code"] for c in candidates}

        if not is_core:
            # The classification is decided in code, not by the model — a
            # flexible ingredient is always dropped regardless of what the
            # model returned, so a hallucinated "substitute" here is inert.
            return SubstitutionResult(
                dish.dish_id, dish.name, line.food_name, is_core, share,
                "drop", None, candidates,
                reason or self._fallback_reason(dish, line, is_core, share, lang),
                "sealion")

        if action == "substitute" and code in valid_codes:
            sub = next(c for c in candidates if c["code"] == code)
            return SubstitutionResult(
                dish.dish_id, dish.name, line.food_name, is_core, share,
                "substitute", sub, candidates,
                reason or self._fallback_reason(dish, line, is_core, share, lang),
                "sealion")

        # Model said "substitute" but named something not on the offered
        # list (or said nothing usable) — fall back to the deterministic
        # top candidate rather than trust an unvalidated pick.
        return self._fallback(dish, line, is_core, share, candidates, lang,
                              reason_prefix=reason)

    # ------------------------------------------------------------ fallback
    def _fallback(self, dish, line, is_core, share, candidates, lang: str,
                  reason_prefix: str = "") -> SubstitutionResult:
        if not is_core:
            return SubstitutionResult(
                dish.dish_id, dish.name, line.food_name, is_core, share,
                "drop", None, candidates,
                self._fallback_reason(dish, line, is_core, share, lang),
                "fallback")
        sub = candidates[0] if candidates else None
        action = "substitute" if sub else "not_found"
        reason = reason_prefix or self._fallback_reason(dish, line, is_core, share, lang)
        return SubstitutionResult(
            dish.dish_id, dish.name, line.food_name, is_core, share,
            action, sub, candidates, reason, "fallback")

    @staticmethod
    def _fallback_reason(dish, line, is_core: bool, share: float, lang: str) -> str:
        if lang == "id":
            if not is_core:
                return (f"{line.food_name} hanya {share:.0%} dari berat hidangan "
                        f"— boleh dihilangkan tanpa mengubah jenis hidangan.")
            return (f"{line.food_name} adalah {share:.0%} dari berat "
                    f"{dish.name} — perlu pengganti dari kelompok pangan yang sama.")
        if not is_core:
            return (f"{line.food_name} is only {share:.0%} of the dish's mass "
                    f"— safe to omit without changing what the dish is.")
        return (f"{line.food_name} is {share:.0%} of {dish.name}'s mass — "
                f"needs a substitute from the same food group.")
