"""SEA-LION client — AI Singapore's Southeast Asian LLM family.

SEA-LION v4.5 (released May 2026) is trained for Southeast Asian languages —
Indonesian among them — and is documented as being tuned for "precise
function-calling, structured JSON outputs, and autonomous agentic tool-use".
That combination is what makes it the right orchestrator for Racik: the
operator writes Indonesian, and the model's job is to route that intent onto
the deterministic planner, never to do the arithmetic itself.

Transport
---------
The hosted API at ``https://api.sea-lion.ai/v1`` is OpenAI-compatible, so this
client speaks the standard ``/chat/completions`` shape with ``tools`` and
``tool_calls``. It is implemented on ``urllib`` rather than the ``openai`` SDK
so that the planner keeps a dependency-free core; anything OpenAI-compatible
(vLLM, llama.cpp, Ollama) can be pointed at with ``base_url``.

Rate limiting
-------------
The hosted API documents 10 requests per minute per user, so the client
self-throttles to a minimum interval between calls and backs off on HTTP 429.
Self-hosted deployments can set ``min_interval=0``.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

DEFAULT_BASE_URL = "https://api.sea-lion.ai/v1"

# Model ids accepted by the hosted SEA-LION API.
ORCHESTRATOR_MODEL = "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"
REASONING_MODEL = "aisingapore/Llama-SEA-LION-v3.5-70B-R"
GUARD_MODEL = "aisingapore/SEA-Guard"
EMBEDDING_MODEL = "aisingapore/SEA-LION-ModernBERT-Embedding-600M"

# Published on HuggingFace for self-hosting rather than on the hosted API. Use
# it by serving the GGUF/vLLM build locally and pointing `base_url` at it.
LOCAL_SMALL_MODEL = "aisingapore/Gemma-SEA-LION-v4.5-E2B-IT"

MODEL_NOTES = {
    ORCHESTRATOR_MODEL: "27B instruct, 262K context, function-calling — default orchestrator",
    REASONING_MODEL: "70B reasoning variant, for harder multi-step questions",
    LOCAL_SMALL_MODEL: "4B instruct for self-hosting; not served by the hosted API",
}


class SeaLionError(RuntimeError):
    """Any failure talking to SEA-LION, with the cause preserved."""


class SeaLionNotConfigured(SeaLionError):
    """No API key available — the caller should fall back to rule-based mode."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class SeaLionClient:
    """Minimal OpenAI-compatible chat client for SEA-LION."""

    def __init__(self, api_key: Optional[str] = None,
                 base_url: str = DEFAULT_BASE_URL,
                 model: str = ORCHESTRATOR_MODEL,
                 timeout: float = 90.0,
                 min_interval: float = 6.0,
                 max_retries: int = 3):
        self.api_key = api_key or os.environ.get("SEALION_API_KEY", "")
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.model = model
        self.timeout = timeout
        # 10 requests/minute on the hosted API -> one call every 6 s.
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._last_call = 0.0
        self.calls = 0

    @property
    def configured(self) -> bool:
        """A local OpenAI-compatible server needs no key; the hosted API does."""
        return bool(self.api_key) or not self.base_url.startswith(
            "https://api.sea-lion.ai")

    def describe(self) -> dict:
        return {
            "provider": "SEA-LION (AI Singapore)",
            "model": self.model,
            "base_url": self.base_url,
            "configured": self.configured,
            "note": MODEL_NOTES.get(self.model, ""),
            "calls_made": self.calls,
        }

    # ------------------------------------------------------------ transport
    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None,
             temperature: float = 0.0, max_tokens: int = 1400,
             tool_choice: str = "auto") -> ChatResult:
        """One chat-completions round trip.

        temperature defaults to 0: the orchestrator's job is to extract
        parameters and relay tool output, and that must be reproducible.
        """
        if not self.configured:
            raise SeaLionNotConfigured(
                "No SEALION_API_KEY set. Get a key at https://sea-lion.ai, "
                "export SEALION_API_KEY, or point base_url at a local "
                "OpenAI-compatible SEA-LION server.")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        body = self._post("/chat/completions", payload)
        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise SeaLionError(f"unexpected response shape: {body}") from exc

        return ChatResult(
            content=(message.get("content") or "").strip(),
            tool_calls=_parse_tool_calls(message.get("tool_calls") or []),
            raw=message,
            usage=body.get("usage", {}) or {},
        )

    def _post(self, path: str, payload: dict) -> dict:
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            self._throttle()
            request = urllib.request.Request(
                self.base_url + path,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    **({"Authorization": f"Bearer {self.api_key}"}
                       if self.api_key else {}),
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as res:
                    self.calls += 1
                    return json.loads(res.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = _read_error(exc)
                if exc.code == 429:          # documented 10 req/min ceiling
                    last_error = SeaLionError(f"rate limited: {detail}")
                    time.sleep(min(2 ** attempt * 6.0, 30.0))
                    continue
                if exc.code in (401, 403):
                    raise SeaLionError(
                        f"SEA-LION rejected the credentials ({exc.code}): {detail}"
                    ) from exc
                if 500 <= exc.code < 600:
                    last_error = SeaLionError(f"server error {exc.code}: {detail}")
                    time.sleep(2 ** attempt)
                    continue
                raise SeaLionError(f"HTTP {exc.code}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = SeaLionError(f"network error: {exc}")
                time.sleep(2 ** attempt)
        raise last_error or SeaLionError("request failed with no diagnosis")

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()


def _parse_tool_calls(raw_calls: Iterable[dict]) -> list[ToolCall]:
    """Read tool calls, tolerating the arguments arriving as a JSON string."""
    calls: list[ToolCall] = []
    for call in raw_calls:
        function = call.get("function", {}) or {}
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except json.JSONDecodeError:
                arguments = {"_unparsed": arguments}
        if not isinstance(arguments, dict):
            arguments = {"value": arguments}
        calls.append(ToolCall(id=call.get("id", ""),
                              name=function.get("name", ""),
                              arguments=arguments))
    return calls


def _read_error(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8")[:400]
    except Exception:
        return exc.reason or "unknown"
