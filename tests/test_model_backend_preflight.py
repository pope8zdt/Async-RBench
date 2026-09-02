from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from async_rbench.evaluation.model_backend import (
    OpenAICompatibleBackend,
    conservative_input_estimate,
    exact_input_estimate,
    provider_preflight,
    validate_credential,
)


@dataclass
class _FakeProviderConfig:
    """Minimal ProviderConfig surface needed by OpenAICompatibleBackend."""

    backend: str = "openai_compatible"
    api_url: str = "http://x/v1"
    max_api_concurrency: int = 1
    max_tokens_parameter: str = "max_tokens"
    max_output_tokens: int = 8192
    send_seed: bool = False
    temperature: float | None = None
    request_body_extra: dict[str, Any] = None  # type: ignore[assignment]
    extra_headers: dict[str, str] = None  # type: ignore[assignment]
    request_timeout_sec: int = 30
    codex_executable: str = "codex"
    codex_reasoning_effort: str = "high"
    tokenizer: str = ""

    def api_key(self) -> str:
        return ""


# --- Item 3: Unicode / orphan credential preflight ---


def test_valid_ascii_keys_pass():
    for key in ("", "sk-abc123", "a8b7_D-01=+/", "x" * 64):
        validate_credential(key)  # must not raise


def test_whitespace_credential_is_rejected():
    for key in (" abc", "abc ", "ab\tc", "ab\nc"):
        try:
            validate_credential(key)
        except RuntimeError:
            continue
        raise AssertionError(f"accepted whitespace credential {key!r}")


def test_non_ascii_credential_is_rejected():
    # Invisible BOM / non-breaking space / zero-width copied into the key would
    # corrupt the Authorization header and burn the episode as a 401.
    for key in ("ab\xa0c", "ab​c", "ab﻿c", "a中c", "ab\x00c"):
        try:
            validate_credential(key)
        except RuntimeError:
            continue
        raise AssertionError(f"accepted non-ASCII credential {key!r}")


def test_provider_preflight_reports_missing_required_credential(monkeypatch):
    import os
    monkeypatch.delenv("QWEN3_CODER_API_KEY", raising=False)
    config = {
        "api_key_env": "QWEN3_CODER_API_KEY", "api_key_required": True,
        "api_url": "http://x/v1", "main_model": "m",
    }
    assert provider_preflight(config) == (
        "missing credential 'QWEN3_CODER_API_KEY' (set it before running)"
    )


def test_provider_preflight_rejects_orphan_credential(monkeypatch):
    import os
    monkeypatch.setenv("QWEN3_CODER_API_KEY", "  ﻿sk-abc  ")
    config = {
        "api_key_env": "QWEN3_CODER_API_KEY", "api_key_required": True,
        "api_url": "http://x/v1", "main_model": "m",
    }
    assert provider_preflight(config).startswith("credential is not a flat bearer token")


def test_provider_preflight_requires_url_and_model(monkeypatch):
    import os
    monkeypatch.setenv("QWEN3_CODER_API_KEY", "sk-ok")
    assert provider_preflight(
        {"api_key_env": "QWEN3_CODER_API_KEY", "main_model": "m"}
    ) == "provider config has no api_url"
    assert provider_preflight(
        {"api_key_env": "QWEN3_CODER_API_KEY", "api_url": "http://x/v1"}
    ) == "provider config has no main_model"


def test_provider_preflight_ok_when_credential_clean(monkeypatch):
    import os
    monkeypatch.setenv("QWEN3_CODER_API_KEY", "sk-ok")
    config = {
        "api_key_env": "QWEN3_CODER_API_KEY", "api_key_required": True,
        "api_url": "http://x/v1", "main_model": "m",
    }
    assert provider_preflight(config) == ""


# --- Item 5: backend input-estimate contract (spec §7.3) --------------------


_MESSAGES = [
    {"role": "system", "content": "You are a resolver."},
    {"role": "user", "content": "Recover the rows with a short instruction."},
]
_TOOLS = [
    {
        "type": "function",
        "function": {"name": "terminal", "description": "run", "parameters": {}},
    }
]


def test_estimate_without_tokenizer_is_conservative_upper_bound() -> None:
    backend = OpenAICompatibleBackend(_FakeProviderConfig(tokenizer=""))
    estimate = backend.estimate_input_tokens(_MESSAGES, _TOOLS)
    assert estimate.accounting_mode == "conservative"
    # An upper bound must be at least as large as the compact exact proxy.
    assert estimate.input_tokens >= exact_input_estimate(_MESSAGES, _TOOLS)
    assert estimate.input_tokens >= 1


def test_estimate_with_tokenizer_is_heuristic_proxy_not_exact() -> None:
    backend = OpenAICompatibleBackend(_FakeProviderConfig(tokenizer="o200k"))
    estimate = backend.estimate_input_tokens(_MESSAGES, _TOOLS)
    # A configured tokenizer still reports a heuristic *proxy*, not an exact,
    # guaranteed count (spec §7.3).  Only a real provider tokenizer would label
    # "provider_exact"; the current proxy is charged "tokenizer_proxy" so Track A
    # does not treat it as a guarantee.
    assert estimate.accounting_mode == "tokenizer_proxy"
    assert estimate.input_tokens == exact_input_estimate(_MESSAGES, _TOOLS)


def test_exact_proxy_is_not_claimed_as_an_upper_bound() -> None:
    # The exact/compact proxy (``chars // 4``) is a heuristic, not a guaranteed
    # upper bound: a tokenizer can emit more tokens than the proxy for a packed
    # run of characters that maps to multiple tokens.  Strict admission therefore
    # must not rely on this branch to be safe at admission time -- the pool still
    # settles to true usage and halts on an overrun.  Here we assert only that the
    # conservative branch stays above (never below) the proxy, which is the one
    # direction the contract guarantees; we explicitly do NOT claim the proxy is
    # a ceiling.
    assert conservative_input_estimate(_MESSAGES, _TOOLS) >= exact_input_estimate(
        _MESSAGES, _TOOLS
    )
