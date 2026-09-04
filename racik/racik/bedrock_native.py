"""Calling a stock AWS Bedrock model (Claude Haiku, Nova Micro/Lite, etc.)
through the Converse API — distinct from bedrock.py, which is specifically
about importing SEA-LION's own weights via Custom Model Import.

Converse is the native way to call anything already in Bedrock's model
catalog: no import job, no S3 upload, just a modelId and an IAM-permitted
principal. That's the right fit for a time-boxed hackathon sandbox account
(ISB — Innovation Sandbox on AWS) with a hard budget cap and short-lived
SSO credentials: no standing infrastructure to leave running, nothing to
import ahead of time.

The catch this module exists to handle: Converse's request/response shape
is genuinely different from the OpenAI chat.completions format the rest of
Racik is built around (orchestrator.py's messages list, TOOL_SCHEMAS,
sealion.py's ChatResult) —

  - no "system" role in `messages`; it's a separate top-level `system` param
  - no "tool" role for tool results; they go back as a `user` message with
    a `toolResult` content block, addressed by toolUseId
  - assistant tool calls are `toolUse` content blocks, not a `tool_calls`
    field with JSON-string arguments
  - tools are `{"toolSpec": {"name", "description", "inputSchema": {"json": ...}}}`,
    not `{"type": "function", "function": {...}}`

So chat() here translates in both directions and returns the same
ChatResult/ToolCall shape sealion.py and bedrock.py already return — the
orchestrator doesn't know or care which provider answered it.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from .sealion import ChatResult, SeaLionClient, SeaLionError, SeaLionNotConfigured, ToolCall

logger = logging.getLogger(__name__)

# Cheap, fast, tool-calling-capable defaults worth trying first in a
# budget-capped sandbox — see racik/docs or the hackathon's own guidance.
# claude-3-haiku-20240307 is Bedrock-LEGACY and access-denied on fresh
# accounts; nova-lite is ACTIVE and supports plain ON_DEMAND invocation
# (the current Claude models on this account require an inference-profile
# ARN, not a bare modelId, so they're not a drop-in default here).
DEFAULT_MODEL_ID = "amazon.nova-lite-v1:0"


class BedrockNativeClient(SeaLionClient):
    """Any stock Bedrock model, called via Converse. Not SEA-LION — this is
    the path for "we don't need SEA-LION specifically, just a working
    tool-calling model on the AWS credits we already have"."""

    def __init__(self, model_id: Optional[str] = None,
                 region: Optional[str] = None,
                 timeout: float = 90.0,
                 max_attempts: int = 6):
        super().__init__(api_key="", base_url="bedrock-converse://",
                         timeout=timeout, min_interval=0.0)
        self.model_id = model_id or os.environ.get(
            "BEDROCK_NATIVE_MODEL_ID", DEFAULT_MODEL_ID)
        self.region = (region or os.environ.get("AWS_REGION")
                       or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1")
        self.max_attempts = max_attempts
        self.model = self.model_id
        self._client = None

    # ------------------------------------------------------------ wiring
    @property
    def configured(self) -> bool:
        return bool(self.model_id) and _boto3_available()

    def describe(self) -> dict:
        return {
            "provider": "AWS Bedrock (native catalog model, Converse API)",
            "model": self.model_id,
            "base_url": f"bedrock-runtime.{self.region}.amazonaws.com",
            "region": self.region,
            "configured": self.configured,
            "boto3_available": _boto3_available(),
            "calls_made": self.calls,
            "note": ("Not SEA-LION — a stock Bedrock catalog model. Tool "
                     "calling via Converse's toolConfig, which AWS documents "
                     "as supported for this class of model (unlike Custom "
                     "Model Import, see bedrock.py)."),
        }

    def _runtime(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:                    # pragma: no cover
            raise SeaLionNotConfigured(
                "boto3 is required: pip install boto3") from exc
        self._client = boto3.client(
            "bedrock-runtime", region_name=self.region,
            config=Config(retries={"total_max_attempts": self.max_attempts,
                                   "mode": "standard"},
                          read_timeout=self.timeout))
        return self._client

    # ------------------------------------------------------------ inference
    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None,
             temperature: float = 0.0, max_tokens: int = 1400,
             tool_choice: str = "auto") -> ChatResult:
        if not self.model_id:
            raise SeaLionNotConfigured(
                "Set BEDROCK_NATIVE_MODEL_ID to a Bedrock model id, e.g. "
                "amazon.nova-lite-v1:0 or amazon.nova-micro-v1:0")

        system, converse_messages = _to_converse_messages(messages)
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": converse_messages,
            "inferenceConfig": {"temperature": temperature,
                                "maxTokens": max_tokens},
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["toolConfig"] = {"tools": [_to_converse_tool(t) for t in tools]}

        try:
            response = self._runtime().converse(**kwargs)
            self.calls += 1
        except Exception as exc:
            # boto3 raises AWS auth-layer errors (ExpiredToken, AccessDenied)
            # as a generic ClientError with the real code inside
            # exc.response['Error']['Code'] — only service-modelled errors
            # (like Bedrock's own ResourceNotFoundException) get a
            # distinctly-named exception class. Checking type(exc).__name__
            # alone misses the auth-layer cases entirely, which is exactly
            # what happens on every call once an ISB sandbox token expires
            # — the most common failure this client sees in practice.
            name = type(exc).__name__
            code = ""
            response_obj = getattr(exc, "response", None)
            if isinstance(response_obj, dict):
                code = response_obj.get("Error", {}).get("Code", "")
            marker = code or name
            logger.warning("Bedrock Converse call failed (%s): %s", marker, exc)

            if "ExpiredToken" in marker:
                raise SeaLionError(
                    "AWS session credentials expired — ISB sandbox "
                    "credentials last 12 hours. Re-export them from the "
                    "access portal and retry."
                ) from exc
            if "AccessDenied" in marker or "UnrecognizedClient" in marker:
                raise SeaLionError(
                    f"Bedrock rejected the credentials ({marker}). Check the "
                    "region (us-east-1 for the ISB sandbox) and that this "
                    "model is enabled for the account.") from exc
            if "Throttling" in marker or "TooManyRequests" in marker:
                raise SeaLionError(
                    "Bedrock is temporarily rate-limiting requests — try "
                    "again in a moment.") from exc
            if "ResourceNotFoundException" in marker and "Legacy" in str(exc):
                raise SeaLionError(
                    f"Bedrock model '{self.model_id}' is retired/legacy and "
                    "access-denied on this account. Set BEDROCK_NATIVE_MODEL_ID "
                    "to an ACTIVE on-demand model, e.g. amazon.nova-lite-v1:0."
                ) from exc
            # Unrecognised failure: still keep the operator-facing message
            # short — the full exception is already in the log line above,
            # never in what a kitchen coordinator reads.
            raise SeaLionError(
                f"Bedrock is temporarily unreachable ({marker}) — the "
                "deterministic planner is answering instead.") from exc

        return _from_converse_response(response)


# ---------------------------------------------------------------- translation


def _to_converse_messages(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    """OpenAI-shaped messages -> (Converse `system`, Converse `messages`).

    Converse has no "system" or "tool" role: system prompts are a separate
    top-level field, and tool results travel back as a `user` message with
    a `toolResult` content block."""
    system: list[dict] = []
    out: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            if msg.get("content"):
                system.append({"text": msg["content"]})
            continue

        if role == "tool":
            out.append({"role": "user", "content": [{
                "toolResult": {
                    "toolUseId": msg.get("tool_call_id", ""),
                    "content": [{"text": str(msg.get("content", ""))}],
                },
            }]})
            continue

        if role == "assistant":
            content: list[dict] = []
            if msg.get("content"):
                content.append({"text": msg["content"]})
            for call in msg.get("tool_calls") or []:
                fn = call.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except (TypeError, ValueError):
                    args = {}
                content.append({"toolUse": {
                    "toolUseId": call.get("id", ""),
                    "name": fn.get("name", ""),
                    "input": args,
                }})
            if content:
                out.append({"role": "assistant", "content": content})
            continue

        # user (or anything else) -> plain text turn
        if msg.get("content"):
            out.append({"role": "user", "content": [{"text": str(msg["content"])}]})
    return system, out


def _to_converse_tool(schema: dict) -> dict:
    """{"type":"function","function":{...}} -> {"toolSpec": {...}}"""
    fn = schema.get("function", schema)
    return {"toolSpec": {
        "name": fn.get("name", ""),
        "description": fn.get("description", ""),
        "inputSchema": {"json": fn.get("parameters", {"type": "object",
                                                        "properties": {}})},
    }}


def _from_converse_response(response: dict) -> ChatResult:
    message = (response.get("output") or {}).get("message") or {}
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in message.get("content") or []:
        if "text" in block:
            text_parts.append(block["text"])
        elif "toolUse" in block:
            use = block["toolUse"]
            tool_calls.append(ToolCall(
                id=use.get("toolUseId", ""), name=use.get("name", ""),
                arguments=use.get("input", {}) or {}))

    usage_raw = response.get("usage") or {}
    usage = {
        "prompt_tokens": usage_raw.get("inputTokens", 0),
        "completion_tokens": usage_raw.get("outputTokens", 0),
    }
    return ChatResult(content="".join(text_parts).strip(),
                      tool_calls=tool_calls, raw=message, usage=usage)


def _boto3_available() -> bool:
    try:
        import boto3  # noqa: F401
        return True
    except ImportError:
        return False
