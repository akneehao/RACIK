"""Tests for bedrock_native.py — the OpenAI<->Converse translation.

This is the highest-risk hand-written part of the native-Bedrock path (no
real AWS call needed to verify it's correct): if the shape is wrong, tool
calling silently breaks, and the orchestrator's whole trust story depends
on tool calling actually working.

Run:  python -m pytest tests -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from racik.bedrock_native import (BedrockNativeClient, _from_converse_response,
                                  _to_converse_messages, _to_converse_tool)


# ---------------------------------------------------------------- request shape

def test_system_message_becomes_the_separate_system_param():
    system, messages = _to_converse_messages([
        {"role": "system", "content": "You are Racik."},
        {"role": "user", "content": "Plan a 5-day menu"},
    ])
    assert system == [{"text": "You are Racik."}]
    assert messages == [{"role": "user", "content": [{"text": "Plan a 5-day menu"}]}]


def test_assistant_tool_call_becomes_a_touluse_block():
    _, messages = _to_converse_messages([
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "plan_menu", "arguments": json.dumps({"days": 5})}},
        ]},
    ])
    assert len(messages) == 1
    block = messages[0]["content"][0]["toolUse"]
    assert block == {"toolUseId": "call_1", "name": "plan_menu", "input": {"days": 5}}


def test_tool_result_becomes_a_user_message_with_toolresult():
    """Converse has no "tool" role — results go back as user content."""
    _, messages = _to_converse_messages([
        {"role": "tool", "tool_call_id": "call_1", "name": "plan_menu",
         "content": '{"ok": true}'},
    ])
    assert messages == [{"role": "user", "content": [{
        "toolResult": {"toolUseId": "call_1", "content": [{"text": '{"ok": true}'}]},
    }]}]


def test_assistant_text_and_tool_call_together():
    _, messages = _to_converse_messages([
        {"role": "assistant", "content": "Let me check that.", "tool_calls": [
            {"id": "call_2", "type": "function",
             "function": {"name": "get_dish", "arguments": "{}"}},
        ]},
    ])
    content = messages[0]["content"]
    assert {"text": "Let me check that."} in content
    assert any("toolUse" in c for c in content)


def test_malformed_tool_arguments_dont_crash_translation():
    _, messages = _to_converse_messages([
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_3", "type": "function",
             "function": {"name": "plan_menu", "arguments": "not valid json"}},
        ]},
    ])
    assert messages[0]["content"][0]["toolUse"]["input"] == {}


def test_tool_schema_translates_to_toolspec():
    oai_tool = {"type": "function", "function": {
        "name": "plan_menu", "description": "plans a menu",
        "parameters": {"type": "object",
                       "properties": {"days": {"type": "integer"}}}}}
    converse_tool = _to_converse_tool(oai_tool)
    assert converse_tool == {"toolSpec": {
        "name": "plan_menu", "description": "plans a menu",
        "inputSchema": {"json": {"type": "object",
                                 "properties": {"days": {"type": "integer"}}}},
    }}


# ---------------------------------------------------------------- response shape

def test_response_parses_text_and_tool_use_and_usage():
    fake_response = {
        "output": {"message": {"role": "assistant", "content": [
            {"text": "Sure, planning now."},
            {"toolUse": {"toolUseId": "call_9", "name": "plan_menu",
                        "input": {"days": 3}}},
        ]}},
        "usage": {"inputTokens": 120, "outputTokens": 45},
    }
    result = _from_converse_response(fake_response)
    assert result.content == "Sure, planning now."
    assert result.wants_tools
    assert result.tool_calls[0].name == "plan_menu"
    assert result.tool_calls[0].arguments == {"days": 3}
    # orchestrator.py reads exactly these two keys off ChatResult.usage —
    # Bedrock's own inputTokens/outputTokens naming must map onto them.
    assert result.usage == {"prompt_tokens": 120, "completion_tokens": 45}


def test_response_with_no_tool_use_has_no_tool_calls():
    fake_response = {"output": {"message": {"content": [{"text": "Just an answer."}]}}}
    result = _from_converse_response(fake_response)
    assert not result.wants_tools
    assert result.content == "Just an answer."


def test_response_joins_multiple_text_blocks():
    fake_response = {"output": {"message": {"content": [
        {"text": "Part one. "}, {"text": "Part two."},
    ]}}}
    result = _from_converse_response(fake_response)
    assert result.content == "Part one. Part two."


# ---------------------------------------------------------------- client wiring

def test_client_falls_back_to_a_real_default_model_when_unset(monkeypatch):
    """No model_id given (constructor arg or env var) still means a real,
    working model — never silently inert. That's deliberate: a hackathon
    demo shouldn't fail closed just because nobody set an env var."""
    monkeypatch.delenv("BEDROCK_NATIVE_MODEL_ID", raising=False)
    client = BedrockNativeClient(model_id="")
    assert client.model_id  # DEFAULT_MODEL_ID
    assert client.configured  # given boto3 is installed in this env


def test_client_describe_never_claims_to_be_sealion():
    client = BedrockNativeClient(model_id="anthropic.claude-3-haiku-20240307-v1:0")
    desc = client.describe()
    assert "SEA-LION" not in desc["provider"]
    assert desc["model"] == "anthropic.claude-3-haiku-20240307-v1:0"


def test_factory_routes_to_native_client_when_model_id_set(monkeypatch):
    monkeypatch.setenv("BEDROCK_NATIVE_MODEL_ID",
                       "anthropic.claude-3-haiku-20240307-v1:0")
    monkeypatch.delenv("RACIK_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("BEDROCK_MODEL_ARN", raising=False)
    monkeypatch.delenv("SEALION_BASE_URL", raising=False)
    from racik.bedrock import make_client
    client = make_client()
    assert isinstance(client, BedrockNativeClient)


def test_factory_routes_to_native_client_via_explicit_provider(monkeypatch):
    monkeypatch.setenv("RACIK_LLM_PROVIDER", "bedrock_native")
    monkeypatch.setenv("BEDROCK_NATIVE_MODEL_ID", "amazon.nova-micro-v1:0")
    from racik.bedrock import make_client
    client = make_client()
    assert isinstance(client, BedrockNativeClient)
    assert client.model_id == "amazon.nova-micro-v1:0"


# ---------------------------------------------------------------- error classification

class _StubRuntime:
    """Stands in for the boto3 bedrock-runtime client so these tests never
    need real AWS credentials or a network call."""

    def __init__(self, exc):
        self._exc = exc

    def converse(self, **kwargs):
        raise self._exc


def _client_error(code, message="boom"):
    from botocore.exceptions import ClientError
    return ClientError({"Error": {"Code": code, "Message": message}}, "Converse")


def test_expired_token_surfaces_as_a_short_friendly_message():
    """Regression test for a real bug: boto3 raises AWS auth-layer errors
    (ExpiredToken, AccessDenied) as a generic ClientError with the real
    code inside exc.response['Error']['Code'] — only service-modelled
    errors get a distinctly-named exception class. Checking
    type(exc).__name__ alone misses the auth-layer cases entirely, which
    is exactly what happened on every single call once an ISB sandbox
    token expired: the operator saw the raw AWS SDK exception text
    ("ClientError", "ExpiredTokenException", "security token") embedded
    in the answer instead of a short, friendly message."""
    from racik.sealion import SeaLionError
    client = BedrockNativeClient(model_id="amazon.nova-lite-v1:0")
    client._client = _StubRuntime(_client_error(
        "ExpiredTokenException",
        "The security token included in the request is expired"))
    try:
        client.chat([{"role": "user", "content": "hi"}])
        assert False, "expected a SeaLionError"
    except SeaLionError as exc:
        assert "expired" in str(exc).lower()
        assert "ExpiredTokenException" not in str(exc)
        assert "security token" not in str(exc)


def test_access_denied_names_the_likely_cause():
    from racik.sealion import SeaLionError
    client = BedrockNativeClient(model_id="amazon.nova-lite-v1:0")
    client._client = _StubRuntime(_client_error("AccessDeniedException",
                                                "not authorized"))
    try:
        client.chat([{"role": "user", "content": "hi"}])
        assert False, "expected a SeaLionError"
    except SeaLionError as exc:
        assert "credentials" in str(exc).lower() or "region" in str(exc).lower()


def test_unrecognised_failure_still_gets_a_short_message_not_the_raw_exception():
    from racik.sealion import SeaLionError
    client = BedrockNativeClient(model_id="amazon.nova-lite-v1:0")
    client._client = _StubRuntime(
        RuntimeError("some totally unexpected internal boto3 detail"))
    try:
        client.chat([{"role": "user", "content": "hi"}])
        assert False, "expected a SeaLionError"
    except SeaLionError as exc:
        assert "some totally unexpected internal boto3 detail" not in str(exc)
