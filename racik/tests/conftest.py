"""Shared test fixtures.

The one thing every test needs protection from: a real racik/.env file.
api.py loads it automatically at import time (python-dotenv), which is
correct in production — but it means the *first* test in a run that
imports racik.api quietly pulls whatever provider config is sitting in a
developer's real .env into the process-wide environment, where it stays
for every test that runs after it. A test asserting "no provider
configured -> falls back to the default" then depends on nobody having a
real .env — true in CI, false the moment someone sets one up locally to
actually run the app, which is exactly when these tests started failing.

autouse=True: every test gets a clean slate for these variables unless it
explicitly sets one itself (via monkeypatch, which still works normally
inside a test — this fixture only clears what's already there beforehand).
"""
from __future__ import annotations

import pytest

_LLM_PROVIDER_ENV_VARS = (
    "RACIK_LLM_PROVIDER",
    "SEALION_API_KEY",
    "SEALION_BASE_URL",
    "SEALION_MODEL",
    "BEDROCK_MODEL_ARN",
    "BEDROCK_NATIVE_MODEL_ID",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
)


@pytest.fixture(autouse=True)
def _isolated_llm_provider_env(monkeypatch):
    for key in _LLM_PROVIDER_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
