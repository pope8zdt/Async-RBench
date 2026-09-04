from __future__ import annotations

from async_rbench.evaluation.model_backend import (
    provider_preflight,
    validate_credential,
)


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
