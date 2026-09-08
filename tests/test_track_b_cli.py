from __future__ import annotations

import json
from pathlib import Path

import pytest

from async_rbench.profiles import load_profile
from async_rbench.track_b import cli as track_b_cli


def _write_config(path: Path) -> Path:
    path.write_text(
        "track: B\nframework: deterministic\nmodel: fixture\n",
        encoding="utf-8",
    )
    return path


def test_track_b_profile_is_development_only() -> None:
    profile = load_profile("track_b")

    assert profile.runtime_mode == "agent_system"
    assert profile.adapter_command[-1].replace("\\", "/").endswith("adapters/track_b.py")


def test_run_command_never_requests_official_track(tmp_path: Path, monkeypatch) -> None:
    config = _write_config(tmp_path / "config.yaml")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"episodes": []}), encoding="utf-8")
    captured: list[str] = []
    monkeypatch.setattr(track_b_cli, "run_eval_cli", lambda argv: captured.extend(argv) or 0)

    result = track_b_cli.main([
        "run", "--config", str(config), "--manifest", str(manifest),
        "--output", str(tmp_path / "track-b-output"), "--no-container",
    ])

    assert result == 0
    assert "--official-track" not in captured
    assert captured[:3] == ["run-manifest", "--manifest", str(manifest.resolve())]
    assert "track_b" in captured


def test_run_rejects_formal_experiment_output(tmp_path: Path) -> None:
    config = _write_config(tmp_path / "config.yaml")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"episodes": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="formal experiment"):
        track_b_cli.main([
            "run", "--config", str(config), "--manifest", str(manifest),
            "--output", str(tmp_path / "artifacts" / "experiments" / "formal-47-run"),
        ])


def test_doctor_returns_zero_for_deterministic_runtime(tmp_path: Path, capsys) -> None:
    config = _write_config(tmp_path / "config.yaml")

    assert track_b_cli.main(["doctor", "--config", str(config)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ready"] is True
    assert payload["framework"] == "deterministic"
