"""Test-session hygiene: strip every LLM-provider env var before each test.

Both branches wrote this fixture independently, for the same reason and with
the same fix. This is the union of the two variable lists, so a provider only
one branch knew about still gets cleared.

racik/config.py loads racik/.env automatically (see its top-of-file
load_dotenv() call) so the running app picks up local credentials without a
manual `export`. Good for the app, bad for tests: this suite's own claim —
"no network, no API key" (racik/README.md's Tests section) — silently stops
being true the moment a developer has a populated .env, since real
credentials would make orchestrator/agents tests hit a live provider instead
of the scripted/rule-based paths they're designed to exercise. This fixture
keeps that claim true regardless of what's in .env.

Individual tests that need a specific provider still set it via their own
`monkeypatch.setenv(...)` — monkeypatch layers stack and unwind per-test, so
this session-start cleanup doesn't interfere with that.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import racik.config  # noqa: E402,F401  import first so its load_dotenv() runs
                     # before we strip — otherwise a later `import racik...`
                     # inside a test module would reload .env after us.

_PROVIDER_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "AWS_ACCESS_KEY_ID",
    "AWS_DEFAULT_REGION",
    "AWS_REGION",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "BEDROCK_MODEL_ARN",
    "BEDROCK_MODEL_ID",
    "BEDROCK_NATIVE_MODEL_ID",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "RACIK_LLM_PROVIDER",
    "SEALION_API_KEY",
    "SEALION_BASE_URL",
    "SEALION_MODEL",
)

for _var in _PROVIDER_ENV_VARS:
    os.environ.pop(_var, None)
