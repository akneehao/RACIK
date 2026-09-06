"""Recipe steps: scraped Indonesian home-cook notes -> professional English.

The corpus's step-by-step text is scraped from a recipe-sharing site, written
for a home cook chatting with followers, not a school kitchen following an
SOP: stray ">>" paragraph markers, asides like "Tadaaa" or "Lumayan bisa buat
sarapan", inconsistent punctuation. This module rewrites it into clear,
numbered, professional English instructions for the "How to Prepare" panel —
the one place in the app a kitchen operator actually reads prose, as opposed
to a translated label.

Same shape as translate.py's DishTranslator: cached per dish (a second view
costs nothing), degrades to a same-language cleanup with no model configured,
and always reports which of the two produced the result so the UI can be
honest about it. A later pass can reuse this system prompt's structure for a
professional *Indonesian* rewrite once the English version is settled — see
the module docstring note in translate.py for the same design rationale.
"""
from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import DATA_DIR
from .sealion import SeaLionClient, SeaLionError

CACHE_PATH = DATA_DIR / "recipe_steps_en.json"
MAX_STEPS = 10

SYSTEM_PROMPT = """\
You rewrite Indonesian home-cook recipe notes into professional English \
cooking instructions for kitchen staff preparing school meals at scale.

Rules:
- Return a JSON object only: {"steps": ["...", "..."]}. No prose, no markdown fence.
- Each array entry is one clear, imperative instruction ("Beat the eggs until \
smooth", not "Then you beat the eggs").
- Preserve every real action, ingredient, quantity, and order from the source. \
Do not invent steps, ingredients, or quantities that are not in the source text.
- Remove social-media chatter that carries no cooking instruction: asides like \
"Tadaaa", "Lumayan buat sarapan", exclamation runs, emoji, ">>" paragraph \
markers, notes to followers. If a line is pure chatter with no instruction, \
drop it entirely rather than translating it.
- Merge fragments that describe one action into one step; split a run-on line \
that covers two actions into two steps.
- Use standard cooking terminology (saute, simmer, drain, marinate) instead of \
a literal word-for-word translation where an English cook would use a \
different verb for the same action.
- At most 10 steps. If the source has more, combine minor ones rather than \
truncating real instructions.
- The output is 100% English. Never leave an Indonesian word (including \
first-person asides like "saya"/"aku", or address terms like "bu"/"mba") \
untranslated in the final text — a professional kitchen SOP has no casual \
first-person voice at all.
"""

# Scraped posts use a run of underscores or dashes as a visual divider
# between photo steps. The `^\W*$` branch below cannot catch them:
# `_` is a word character, so a line of underscores is `\w+`. They also
# sit inline rather than on their own line, so one survives into the middle
# of the step that follows -- which is how "_____ Goreng ikan manyung asap"
# reaches the kitchen's How to Prepare panel.
_DIVIDER = re.compile(r"[_=~*\u00b7\u2014\u2013-]{3,}")

# Emoji and pictographs. Dropped rather than kept: a step is read off a
# screen in a working kitchen, and they also let a closing aside pass as an
# instruction just by carrying a word the noise filter does not know.
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF\uFE0F\u2764]")

# Structural: the part is punctuation or whitespace only. Safe to test with
# a full match, and safe to drop outright.
_EMPTY_LINE = re.compile(r"^\W*$")

# Chatter aimed at followers rather than a kitchen. Deliberately matched
# only inside a SHORT part: a great many scraped recipes carry no sentence
# punctuation at all, so the split below yields one part holding the whole
# method, and searching that for chatter deletes the entire recipe over one
# stray phrase. A sign-off is its own short sentence; an instruction that
# merely contains "siap disantap" is not.
_CHATTER = re.compile(
    r"tadaaa+|lumayan|selamat (mencoba|makan)|semoga (suka|berhasil)|"
    r"jangan lupa (like|subscribe|follow)|"
    r"sungguh (nikmat|enak)|pasti nambah|enak(nya)? banget|"
    r"jadi dec?h|siap (disantap|dinikmati)|met mencoba|happy cooking",
    re.IGNORECASE)
CHATTER_MAX_CHARS = 60


def rule_clean(raw: str) -> list[str]:
    """Same-language cleanup with no model available: strips scrape noise and
    splits into sentences. Still Indonesian — never claims to be a translation."""
    text = re.sub(r">>\s*", "", str(raw or ""))
    # Before the whitespace collapse, or a divider glues itself to the step
    # that follows instead of disappearing.
    text = _DIVIDER.sub(" ", text)
    text = _EMOJI.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    steps = []
    for part in parts:
        part = part.strip(" .!?")
        # A part that was only a divider or emoji is empty by now.
        if not part or _EMPTY_LINE.match(part):
            continue
        if len(part) <= CHATTER_MAX_CHARS and _CHATTER.search(part):
            continue
        steps.append(part[:1].upper() + part[1:])
    return steps[:MAX_STEPS]


@dataclass
class RecipeSteps:
    dish_id: int
    steps: list[str] = field(default_factory=list)
    source: str = "rule"          # "llm" | "rule" | "cache"

    def to_dict(self) -> dict:
        return {"steps": self.steps, "steps_source": self.source}


class StepsTranslator:
    """Batched-per-call (one dish at a time — steps are long enough that
    batching several dishes risks the model conflating them), cached to disk."""

    def __init__(self, client: Optional[SeaLionClient] = None,
                 cache_path: Optional[Path] = None):
        self.client = client or SeaLionClient()
        self.cache_path = Path(cache_path) if cache_path else CACHE_PATH
        self.cache: dict[str, list[str]] = self._load_cache()
        self.calls = 0
        self.last_error: Optional[str] = None

    def _load_cache(self) -> dict[str, list[str]]:
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return {k: v for k, v in data.get("steps", {}).items()
                    if isinstance(v, list)}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(
                {"note": "LLM-rewritten professional English recipe steps. "
                         "Delete an entry (or the file) to re-translate it.",
                 "steps": self.cache}, ensure_ascii=False, indent=1),
                encoding="utf-8")
        except OSError:
            pass

    def translate(self, dish_id: int, raw_steps: str,
                  use_model: bool = True) -> RecipeSteps:
        key = str(dish_id)
        if key in self.cache:
            return RecipeSteps(dish_id, self.cache[key], "cache")

        if use_model and self.client.configured and str(raw_steps or "").strip():
            fetched = self._ask_model(raw_steps)
            if fetched:
                self.cache[key] = fetched
                self._save()
                return RecipeSteps(dish_id, fetched, "llm")

        return RecipeSteps(dish_id, rule_clean(raw_steps), "rule")

    def _extra_kwargs(self) -> dict:
        """SEA-LION-only chat options, omitted for clients that reject them.

        `chat_template_kwargs` is a vLLM extension, not part of the OpenAI
        schema, so passing it to Bedrock/Anthropic raises TypeError before a
        request is ever made. Probing the signature keeps SEA-LION's
        thinking-disabled behaviour (reasoning tokens otherwise eat the whole
        max_tokens budget and the model returns empty content) without making
        every other provider an error path.
        """
        try:
            params = inspect.signature(self.client.chat).parameters
        except (TypeError, ValueError):          # a stub/mock with no signature
            return {}
        if "chat_template_kwargs" in params:
            return {"chat_template_kwargs": {"enable_thinking": False}}
        return {}

    def _ask_model(self, raw_steps: str) -> list[str]:
        try:
            reply = self.client.chat(
                [{"role": "system", "content": SYSTEM_PROMPT},
                 {"role": "user", "content":
                     f"Rewrite these recipe notes:\n{raw_steps}"}],
                # SEA-LION's hosted model (Qwen-SEA-LION-v4.5-27B-IT) is a
                # reasoning model: by default it spends tokens on a
                # "reasoning_content" scratchpad before the final answer, and
                # that scratchpad counts against max_tokens — a longer/messier
                # source recipe (several sub-recipes bundled in one) made it
                # think long enough to exhaust even a 3000-token budget and
                # return empty content. This task needs a direct rewrite, not
                # visible reasoning, so turn thinking off entirely rather than
                # chase an ever-larger token ceiling — confirmed on the exact
                # recipe that failed: 234 tokens, correct output, no
                # truncation risk left.
                temperature=0.0, max_tokens=1500, **self._extra_kwargs())
            self.calls += 1
        except SeaLionError as exc:
            self.last_error = str(exc)
            return []

        parsed = _parse_steps_object(reply.content)
        return [str(s).strip() for s in parsed if str(s).strip()][:MAX_STEPS]


def _parse_steps_object(text: str) -> list:
    if not text:
        return []
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(),
                     flags=re.MULTILINE).strip()
    try:
        value = json.loads(cleaned)
    except ValueError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        value = None
        if match:
            try:
                value = json.loads(match.group(0))
            except ValueError:
                pass
        if value is None:
            # The model has occasionally dropped just the wrapping object's
            # closing "}" (confirmed live: valid steps array, `{"steps": [...]`
            # with no final brace) — the array itself is still well-formed, so
            # extract and parse that directly rather than losing the whole
            # reply to one missing character.
            arr = re.search(r"\[.*\]", cleaned, re.S)
            if not arr:
                return []
            try:
                value = json.loads(arr.group(0))
            except ValueError:
                return []
    if isinstance(value, dict):
        return value.get("steps") or []
    return value if isinstance(value, list) else []
