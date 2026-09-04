"""Tests for the SEA-LION orchestration layer.

The agent loop is exercised with a scripted stand-in for SEA-LION rather than
the live API: the loop's job is to route, bound itself, and survive bad model
output, and all of that must be verifiable without a network call or an API key.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from racik.optimizer import MenuOptimizer
from racik.orchestrator import (MAX_REPEATED_CALLS, TOOL_SCHEMAS,
                                RacikOrchestrator, parse_intent)
from racik.sealion import (DEFAULT_BASE_URL, ORCHESTRATOR_MODEL, ChatResult,
                           SeaLionClient, ToolCall, _parse_tool_calls)
from racik.store import RacikStore


# ---------------------------------------------------------------- fixtures

@pytest.fixture(scope="module")
def store():
    return RacikStore()


@pytest.fixture(scope="module")
def optimizer(store):
    return MenuOptimizer(store.load_dishes())


class ScriptedSeaLion(SeaLionClient):
    """A SEA-LION stand-in that replays a fixed list of replies."""

    def __init__(self, script: list[ChatResult]):
        super().__init__(api_key="test-key", min_interval=0.0)
        self.script = list(script)
        self.seen_messages: list[list[dict]] = []

    @property
    def configured(self) -> bool:
        return True

    def chat(self, messages, tools=None, **kwargs) -> ChatResult:
        self.seen_messages.append(list(messages))
        if not self.script:
            return ChatResult(content="done")
        return self.script.pop(0)


def _call(name: str, **arguments) -> ChatResult:
    return ChatResult(content="", tool_calls=[
        ToolCall(id=f"call_{name}", name=name, arguments=arguments)])


# ---------------------------------------------------------------- client

def test_hosted_api_requires_a_key():
    assert SeaLionClient(api_key="").configured is False
    assert SeaLionClient(api_key="k").configured is True


def test_local_server_needs_no_key():
    """A self-hosted OpenAI-compatible SEA-LION has no bearer token."""
    client = SeaLionClient(api_key="", base_url="http://localhost:8000/v1")
    assert client.configured is True


def test_default_model_is_the_documented_api_id():
    assert ORCHESTRATOR_MODEL == "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"
    assert DEFAULT_BASE_URL == "https://api.sea-lion.ai/v1"


def test_unconfigured_client_refuses_to_call():
    from racik.sealion import SeaLionNotConfigured
    with pytest.raises(SeaLionNotConfigured):
        SeaLionClient(api_key="").chat([{"role": "user", "content": "hi"}])


def test_tool_call_arguments_parse_from_json_string():
    """OpenAI-compatible servers send arguments as a JSON string."""
    calls = _parse_tool_calls([{
        "id": "c1", "type": "function",
        "function": {"name": "plan_menu", "arguments": '{"stage": "sd", "days": 3}'},
    }])
    assert calls[0].arguments == {"stage": "sd", "days": 3}


def test_malformed_tool_arguments_do_not_raise():
    calls = _parse_tool_calls([{
        "id": "c1", "function": {"name": "x", "arguments": "{not json"}}])
    assert "_unparsed" in calls[0].arguments


# ---------------------------------------------------------------- schemas

def test_every_declared_tool_has_an_implementation(store, optimizer):
    orch = RacikOrchestrator(store, optimizer, ScriptedSeaLion([]))
    declared = {t["function"]["name"] for t in TOOL_SCHEMAS}
    assert declared == set(orch.tools)


def test_tool_schemas_are_well_formed():
    for schema in TOOL_SCHEMAS:
        fn = schema["function"]
        assert schema["type"] == "function"
        assert fn["name"] and fn["description"]
        assert fn["parameters"]["type"] == "object"
        for name, spec in fn["parameters"]["properties"].items():
            assert "type" in spec, f"{fn['name']}.{name} has no type"


# ---------------------------------------------------------------- agent loop

def test_loop_runs_a_tool_then_answers(store, optimizer):
    client = ScriptedSeaLion([
        _call("nutrition_reference", stage="sd"),
        ChatResult(content="Target energi 617 kkal per sekali makan."),
    ])
    result = RacikOrchestrator(store, optimizer, client).ask("Berapa targetnya?")
    assert result.mode == "sealion"
    assert [t.name for t in result.trace] == ["nutrition_reference"]
    assert "617" in result.answer
    assert result.stopped_because == "completed"


def test_tool_results_are_fed_back_to_the_model(store, optimizer):
    client = ScriptedSeaLion([
        _call("nutrition_reference", stage="sd"),
        ChatResult(content="ok"),
    ])
    RacikOrchestrator(store, optimizer, client).ask("targets?")
    final_turn = client.seen_messages[-1]
    tool_messages = [m for m in final_turn if m["role"] == "tool"]
    assert tool_messages, "tool output was never returned to the model"
    assert "energy_kcal" in tool_messages[0]["content"]


def test_step_cap_is_enforced_in_code(store, optimizer):
    """A model that only ever calls tools must still terminate."""
    client = ScriptedSeaLion([_call("nutrition_reference", stage="sd")] * 50)
    orch = RacikOrchestrator(store, optimizer, client, max_steps=3)
    result = orch.ask("loop forever")
    assert result.steps == 3
    assert "step cap" in result.stopped_because
    assert result.answer


def test_repeated_identical_calls_are_short_circuited(store, optimizer):
    client = ScriptedSeaLion([_call("nutrition_reference", stage="sd")] * 10)
    orch = RacikOrchestrator(store, optimizer, client, max_steps=6)
    result = orch.ask("repeat")
    blocked = [t for t in result.trace if "error" in t.result]
    executed = [t for t in result.trace if "error" not in t.result]
    assert len(executed) <= MAX_REPEATED_CALLS
    assert blocked, "runaway repetition was never detected"


def test_unknown_tool_is_reported_not_raised(store, optimizer):
    client = ScriptedSeaLion([
        _call("definitely_not_a_tool", x=1),
        ChatResult(content="recovered"),
    ])
    result = RacikOrchestrator(store, optimizer, client).ask("q")
    assert result.answer == "recovered"
    assert "unknown tool" in result.trace[0].result["error"]


def test_bad_arguments_are_reported_not_raised(store, optimizer):
    client = ScriptedSeaLion([
        _call("get_dish", wrong_argument=1),
        ChatResult(content="recovered"),
    ])
    result = RacikOrchestrator(store, optimizer, client).ask("q")
    assert "error" in result.trace[0].result
    assert result.answer == "recovered"


def test_plan_tool_returns_engine_numbers(store, optimizer):
    client = ScriptedSeaLion([
        _call("plan_menu", stage="sd", days=2, portions=100),
        ChatResult(content="menu siap"),
    ])
    result = RacikOrchestrator(store, optimizer, client).ask("buatkan menu")
    payload = result.trace[0].result
    assert len(payload["days"]) == 2
    assert payload["summary"]["mean_cost_per_portion_idr"] > 0
    # the plan is surfaced for the UI, not only described in prose
    assert result.plan is not None and result.plan["days"]


def test_budget_sensitivity_reports_adequacy_per_budget(store, optimizer):
    client = ScriptedSeaLion([
        _call("budget_sensitivity", stage="sma", days=1,
              budgets_idr=[7000, 10000]),
        ChatResult(content="ok"),
    ])
    result = RacikOrchestrator(store, optimizer, client).ask("cukup tidak?")
    rows = result.trace[0].result["rows"]
    assert [r["ingredient_budget_idr"] for r in rows] == [7000, 10000]
    # more money must never buy less adequacy
    assert rows[1]["mean_adequacy"] >= rows[0]["mean_adequacy"]


def test_search_respects_its_filters(store, optimizer):
    orch = RacikOrchestrator(store, optimizer, ScriptedSeaLion([]))
    out = orch.tools["search_dishes"](slot="sayur", max_cost_idr=1500, limit=8)
    assert out["dishes"]
    for dish in out["dishes"]:
        assert dish["slot"] == "sayur"
        assert dish["cost_per_portion_idr"] <= 1500


def test_get_dish_exposes_gram_provenance(store, optimizer):
    orch = RacikOrchestrator(store, optimizer, ScriptedSeaLion([]))
    some_id = store.search_dishes(slot="hewani", limit=1)[0]["dish_id"]
    detail = orch.tools["get_dish"](dish_id=some_id)
    assert detail["ingredients"]
    assert all("basis" in line for line in detail["ingredients"])


def test_propose_recipe_computes_real_numbers_from_model_authored_lines(store, optimizer):
    """The model chooses the ingredient lines (this is the one tool where
    that's allowed — see orchestrator.py's SYSTEM_PROMPT bullet on it), but
    the resulting nutrition/cost is still computed by the same deterministic
    pipeline every corpus recipe goes through, never stated by the model."""
    orch = RacikOrchestrator(store, optimizer, ScriptedSeaLion([]))
    out = orch.tools["propose_recipe"](
        name="Gulai Ayam Hijau",
        ingredient_lines=["1 kg ayam, daging, segar", "400 ml santan",
                          "3 buah cabai hijau"],
        province="Jawa Tengah")
    assert "error" not in out
    assert out["draft"]["cost_per_portion_idr"] > 0
    assert out["draft"]["per_portion"]["protein_g"] > 0
    # echoed back verbatim, not re-derived — /api/recipe/save persists
    # exactly this text, not the computed numbers
    assert out["ingredient_lines"] == ["1 kg ayam, daging, segar",
                                       "400 ml santan", "3 buah cabai hijau"]


def test_propose_recipe_reports_the_scope_it_would_save_under(store, optimizer):
    """Regression test for a real bug: the draft card must show (and let a
    kitchen operator confirm/correct) exactly which province/stage a save
    would use — silently defaulting to the setup form's current selection
    is how a recipe drafted for one region/stage in free text ends up
    saved under a completely different one and is never considered for
    the menu it was actually meant for."""
    orch = RacikOrchestrator(store, optimizer, ScriptedSeaLion([]))
    out = orch.tools["propose_recipe"](
        name="Gulai Ayam Hijau",
        ingredient_lines=["1 kg ayam, daging, segar", "400 ml santan"],
        province="Jawa Tengah", stage="smp")
    assert out["suggested_scope"] == {"province": "Jawa Tengah", "stage": "smp"}


def test_propose_recipe_leaves_scope_blank_when_unsaid(store, optimizer):
    orch = RacikOrchestrator(store, optimizer, ScriptedSeaLion([]))
    out = orch.tools["propose_recipe"](
        name="Gulai Ayam Hijau",
        ingredient_lines=["1 kg ayam, daging, segar", "400 ml santan"])
    assert out["suggested_scope"] == {"province": "", "stage": ""}


def test_propose_recipe_reports_an_error_not_a_crash_on_unusable_input(store, optimizer):
    orch = RacikOrchestrator(store, optimizer, ScriptedSeaLion([]))
    out = orch.tools["propose_recipe"](name="Gibberish",
                                       ingredient_lines=["zzz not real zzz"])
    assert "error" in out
    assert "draft" not in out


def test_propose_recipe_reaches_a_full_agent_loop(store, optimizer):
    # _call()'s own first parameter is named "name", which collides with
    # propose_recipe's "name" argument (the dish name) — build the
    # ToolCall directly instead of going through that helper.
    tool_call = ToolCall(id="call_propose_recipe", name="propose_recipe",
                         arguments={"name": "Gulai Ayam Hijau",
                                    "ingredient_lines": ["1 kg ayam, daging, segar",
                                                         "400 ml santan"]})
    client = ScriptedSeaLion([
        ChatResult(content="", tool_calls=[tool_call]),
        ChatResult(content="draf resep siap ditinjau"),
    ])
    result = RacikOrchestrator(store, optimizer, client).ask("tambah resep baru")
    payload = result.trace[0].result
    assert payload["draft"]["name"] == "Gulai Ayam Hijau"
    assert payload["draft"]["cost_per_portion_idr"] > 0


# ---------------------------------------------------------------- narration verification

def test_unverified_numbers_flags_a_figure_not_backed_by_any_tool_result():
    """The core case this exists for: a number the model typed that never
    came from a tool at all — this is exactly what the trust story
    promises never silently happens."""
    from racik.orchestrator import ToolInvocation, _unverified_numbers
    trace = [ToolInvocation("plan_menu", {}, {"summary": {
        "mean_cost_per_portion_idr": 6990}}, 0.1)]
    flagged = _unverified_numbers(
        "Biaya per porsi Rp6.990, tapi total belanja Rp999.999.", trace)
    assert "Rp999.999" in flagged
    assert "Rp6.990" not in flagged


def test_unverified_numbers_tolerates_percentage_narrated_from_a_fraction():
    """The critical anti-false-positive case: adequacy is stored as a 0-1
    fraction in every tool payload (e.g. mean_adequacy: 0.968), and every
    normal, correct answer narrates it as a percentage ("97%"). Without
    the x100 tolerance this is built with, this single, extremely common
    pattern would flag nearly every correct answer Racik produces."""
    from racik.orchestrator import ToolInvocation, _unverified_numbers
    trace = [ToolInvocation("plan_menu", {}, {
        "summary": {"mean_adequacy": 0.968}}, 0.1)]
    assert _unverified_numbers("Pemenuhan AKG rata-rata 97%.", trace) == []


def test_unverified_numbers_matches_rupiah_regardless_of_thousands_style():
    from racik.orchestrator import ToolInvocation, _unverified_numbers
    trace = [ToolInvocation("plan_menu", {}, {"cost_per_portion_idr": 6990}, 0.1)]
    assert _unverified_numbers("Biaya per porsi adalah Rp6.990.", trace) == []
    assert _unverified_numbers("Cost per portion is Rp6,990.", trace) == []


def test_unverified_numbers_returns_empty_when_trace_is_empty():
    """No tool ran — nothing to verify against, and nothing should be
    flagged as a false accusation of a number with no ground truth to
    check it against."""
    from racik.orchestrator import _unverified_numbers
    assert _unverified_numbers("Biaya sekitar Rp5.000.", []) == []


def test_full_agent_loop_surfaces_unverified_numbers(store, optimizer):
    client = ScriptedSeaLion([
        _call("plan_menu", stage="sd", days=1, portions=50),
        ChatResult(content="Biaya per porsi sekitar Rp1.234.567 — sangat terjangkau."),
    ])
    result = RacikOrchestrator(store, optimizer, client).ask("buatkan menu")
    assert result.unverified_numbers  # the solver never produces this figure
    assert any("1.234.567" in n for n in result.unverified_numbers)


def test_fallback_path_never_flags_a_number(store, optimizer):
    """The rule-based fallback's text is built directly from the same
    payload it's checked against (see _render_plan_text), so it can never
    disagree with itself — confirms the check doesn't misfire there."""
    orch = RacikOrchestrator(store, optimizer, SeaLionClient(api_key=""))
    result = orch.ask("Menu 2 hari untuk SD, 100 porsi")
    assert result.mode == "fallback"
    assert result.unverified_numbers == []


# ---------------------------------------------------------------- fallback

def test_fallback_used_when_no_api_key(store, optimizer):
    """Asserted language-neutrally: the same code ships defaulting to id or en."""
    orch = RacikOrchestrator(store, optimizer, SeaLionClient(api_key=""))
    result = orch.ask("Menu 2 hari untuk SD, 100 porsi")
    assert result.mode == "fallback"
    assert result.plan is not None
    assert "menu" in result.answer.lower()
    assert len(result.plan["days"]) == 2


@pytest.mark.parametrize("lang,opening", [("id", "Menu"), ("en", "A ")])
def test_fallback_answers_in_the_requested_language(store, optimizer, lang, opening):
    orch = RacikOrchestrator(store, optimizer, SeaLionClient(api_key=""))
    result = orch.ask("Menu 2 hari untuk SD, 100 porsi", lang=lang)
    assert result.answer.startswith(opening)


def test_network_failure_degrades_to_fallback(store, optimizer):
    from racik.sealion import SeaLionError

    class Broken(ScriptedSeaLion):
        def chat(self, messages, tools=None, **kwargs):
            raise SeaLionError("connection reset")

    orch = RacikOrchestrator(store, optimizer, Broken([]))
    result = orch.ask("Menu 2 hari SD")
    assert result.mode == "fallback"
    assert "SEA-LION" in result.answer and result.plan is not None


# ---------------------------------------------------------------- intent

@pytest.mark.parametrize("text,expected", [
    ("Buatkan menu 5 hari untuk SMP di Jawa Tengah, 150 porsi",
     {"stage": "smp", "days": 5, "portions": 150, "province": "Jawa Tengah"}),
    ("menu 3 hari SD 200 siswa", {"stage": "sd", "days": 3, "portions": 200}),
    ("menu PAUD seminggu", {"stage": "paud", "days": 5}),
    ("menu SMA", {"stage": "sma"}),
])
def test_intent_parsing(text, expected):
    parsed = parse_intent(text, ["Jawa Tengah", "Sumatera Barat", "Bali"])
    for key, value in expected.items():
        assert parsed[key] == value


def test_intent_parses_budget_and_allergens():
    parsed = parse_intent(
        "menu SD anggaran Rp8.500 per porsi tanpa udang", ["Bali"])
    assert parsed["budget_per_portion_idr"] == 8500
    assert any("udang" in t for t in parsed["exclude_terms"])


def test_intent_defaults_are_conservative():
    """Nothing readable in the text means defaults, never a guess."""
    parsed = parse_intent("halo apa kabar", ["Bali"])
    assert parsed == {"stage": "sd"}


def test_exclusions_reach_the_planner(store, optimizer):
    orch = RacikOrchestrator(store, optimizer, SeaLionClient(api_key=""))
    result = orch.ask("Menu 2 hari SD tanpa telur")
    for day in result.plan["days"]:
        for name in day["dishes"].values():
            assert name is None or "telur" not in name.lower()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
