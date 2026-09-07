from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from async_rbench.track_b.config import TrackBConfig
from async_rbench.track_b.frameworks import doctor_framework


def _config(credential_env: str = "") -> TrackBConfig:
    return TrackBConfig(
        track="B", framework="codex-cli", model="gpt-5.6-luna",
        credential_env=credential_env,
    )


def _login_check(monkeypatch: pytest.MonkeyPatch, result: tuple[bool, str]) -> None:
    monkeypatch.setitem(
        sys.modules,
        "async_rbench.track_b.frameworks.codex_cli",
        SimpleNamespace(check_cli_login=lambda: result),
    )


def test_codex_config_accepts_saved_login_without_credential_variable(tmp_path: Path) -> None:
    path = tmp_path / "codex.yaml"
    path.write_text(
        "track: B\nframework: codex-cli\nmodel: gpt-5.6-luna\n",
        encoding="utf-8",
    )

    config = TrackBConfig.from_file(path)

    assert config.credential_env == ""
    assert config.public_metadata()["framework"] == "codex-cli"


def test_codex_config_rejects_api_credential_variable() -> None:
    with pytest.raises(ValueError, match="credential_env must be empty"):
        _config("OPENAI_API_KEY").validate()


@pytest.mark.parametrize(
    ("login_result", "ready"),
    [
        ((True, "Logged in using ChatGPT"), True),
        ((False, "Not logged in; run codex login"), False),
        ((False, "Saved ChatGPT login required; API key login is unsupported"), False),
    ],
)
def test_codex_doctor_requires_saved_chatgpt_login(
    monkeypatch: pytest.MonkeyPatch, login_result: tuple[bool, str], ready: bool,
) -> None:
    monkeypatch.setattr("shutil.which", lambda _: "codex")
    _login_check(monkeypatch, login_result)

    report = doctor_framework("codex-cli", _config())

    assert report.ready is ready
    assert report.executable_present is True
    assert report.credential_present is ready
    assert login_result[1] in report.detail
    assert report.install_hint == ""


def test_codex_doctor_does_not_probe_login_without_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _: None)

    def unexpected_login_probe() -> tuple[bool, str]:
        pytest.fail("login must not run when the Codex CLI is missing")

    monkeypatch.setitem(
        sys.modules,
        "async_rbench.track_b.frameworks.codex_cli",
        SimpleNamespace(check_cli_login=unexpected_login_probe),
    )

    report = doctor_framework("codex-cli", _config())

    assert report.ready is False
    assert report.executable_present is False
    assert report.credential_present is False
    assert "codex" in report.install_hint.lower()
    assert "runtime dependency" in report.detail


def test_codex_doctor_rejects_api_credential_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _: "codex")
    monkeypatch.setenv("OPENAI_API_KEY", "local-test-secret")
    _login_check(monkeypatch, (True, "Logged in using ChatGPT"))

    report = doctor_framework("codex-cli", _config("OPENAI_API_KEY"))

    assert report.ready is False
    assert report.credential_present is False
    assert "credential_env must be empty" in report.detail
    assert "local-test-secret" not in report.detail
