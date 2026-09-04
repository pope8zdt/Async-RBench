from __future__ import annotations

import asyncio
from argparse import Namespace
import hashlib
import json
from pathlib import Path

import pytest

from async_rbench import eval_cli


CASE_ID = "tbn-partial-failure-recovery-0e92790bd0"


def _run_args(
    manifest_path: Path,
    output: Path,
    *,
    config: Path | None = None,
    resume: bool = False,
) -> Namespace:
    return Namespace(
        manifest=str(manifest_path),
        output=str(output),
        official_track=False,
        adapter_command=None,
        skip_conformance=False,
        no_container=False,
        profile="conformance_mock",
        runtime_mode=None,
        config=str(config) if config is not None else None,
        timeout=30,
        gateway_grace=5,
        no_progress=True,
        resume=resume,
        keep_containers=False,
        progress_heartbeat=5,
    )


async def _passing_conformance(*args: object, **kwargs: object) -> dict[str, bool]:
    return {"conformance_passed": True}


def test_run_manifest_stops_before_episodes_when_conformance_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    eval_cli.write_manifest(
        manifest_path,
        eval_cli.create_manifest(
            [CASE_ID],
            1,
            "incentive",
            7,
            ["async"],
            None,
        ),
    )

    async def failed_conformance(*args: object, **kwargs: object) -> dict[str, bool]:
        return {"conformance_passed": False}

    monkeypatch.setattr(eval_cli, "run_conformance", failed_conformance)
    args = _run_args(manifest_path, tmp_path / "run")

    with pytest.raises(ValueError, match="adapter conformance failed"):
        asyncio.run(eval_cli._run_manifest(args))


def test_resume_rejects_run_binding_drift_before_episodes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    eval_cli.write_manifest(
        manifest_path,
        eval_cli.create_manifest(
            [CASE_ID], 1, "incentive", 7, ["async"], None, model="model-a",
        ),
    )
    old_config = tmp_path / "old.yaml"
    old_config.write_text("main_model: model-a\nchild_model: child-a\n", encoding="utf-8")
    new_config = tmp_path / "new.yaml"
    new_config.write_text("main_model: model-a\nchild_model: child-b\n", encoding="utf-8")
    profile = eval_cli.load_profile("conformance_mock")
    old_command = eval_cli._append_config(list(profile.adapter_command), old_config.resolve())
    old_binding = eval_cli._conformance_binding_digest(
        old_command, "conformance_mock", old_config.resolve(),
    )
    output = tmp_path / "run"
    output.mkdir()
    (output / "run-binding.json").write_text(
        json.dumps({
            "binding_version": "1.0",
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "adapter_profile": "conformance_mock",
            "runtime_mode": None,
            "conformance_binding_sha256": old_binding,
            "resource_policy_sha256": None,
            "model": "model-a",
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(eval_cli, "run_conformance", _passing_conformance)

    async def must_not_run_episode(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("binding drift must fail before starting an episode")

    monkeypatch.setattr(eval_cli, "run_episode", must_not_run_episode)
    args = _run_args(manifest_path, output, config=new_config, resume=True)

    with pytest.raises(ValueError, match="run binding drift.*conformance_binding_sha256"):
        asyncio.run(eval_cli._run_manifest(args))


def test_new_run_pins_binding_before_starting_an_episode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest = eval_cli.create_manifest(
        [CASE_ID], 1, "incentive", 7, ["async"], None, model="model-a",
    )
    eval_cli.write_manifest(manifest_path, manifest)
    config = tmp_path / "profile.yaml"
    config.write_text("main_model: model-a\nchild_model: child-a\n", encoding="utf-8")
    output = tmp_path / "run"
    monkeypatch.setattr(eval_cli, "run_conformance", _passing_conformance)

    async def observe_binding(*args: object, **kwargs: object) -> dict[str, object]:
        binding_path = output / "run-binding.json"
        assert binding_path.is_file()
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        assert binding["binding_version"] == "1.0"
        assert binding["manifest_sha256"] == hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest()
        assert binding["adapter_profile"] == "conformance_mock"
        assert binding["model"] == "model-a"
        return {"score_status": "scored"}

    monkeypatch.setattr(eval_cli, "run_episode", observe_binding)
    args = _run_args(manifest_path, output, config=config)

    assert asyncio.run(eval_cli._run_manifest(args)) == 0


def test_resume_rejects_retained_score_from_different_adapter_binding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest = eval_cli.create_manifest(
        [CASE_ID], 1, "incentive", 7, ["async"], None, model="model-a",
    )
    eval_cli.write_manifest(manifest_path, manifest)
    config = tmp_path / "profile.yaml"
    config.write_text("main_model: model-a\nchild_model: child-a\n", encoding="utf-8")
    profile = eval_cli.load_profile("conformance_mock")
    command = eval_cli._append_config(list(profile.adapter_command), config.resolve())
    current_binding = eval_cli._conformance_binding_digest(
        command, "conformance_mock", config.resolve(),
    )
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    output = tmp_path / "run"
    output.mkdir()
    (output / "run-binding.json").write_text(
        json.dumps({
            "binding_version": "1.0",
            "manifest_sha256": manifest_sha256,
            "adapter_profile": "conformance_mock",
            "runtime_mode": None,
            "conformance_binding_sha256": current_binding,
            "resource_policy_sha256": None,
            "model": "model-a",
        }),
        encoding="utf-8",
    )
    episode = manifest["episodes"][0]
    instance = eval_cli.resolve_case_instance(
        eval_cli.ROOT, episode["case_id"], episode["instance_id"],
    )
    contract_version, contract_sha256 = eval_cli._evaluation_contract_identity(
        eval_cli.ROOT,
    )
    episode_output = output / episode["episode_id"]
    episode_output.mkdir()
    (episode_output / "score.json").write_text(
        json.dumps({
            "manifest_sha256": manifest_sha256,
            "scaffold_and_protocol_sha256": eval_cli._source_digest(eval_cli.ROOT),
            "evaluation_contract_version": contract_version,
            "evaluation_contract_sha256": contract_sha256,
            "verifier_bundle_sha256": eval_cli.verifier_bundle_sha256(
                instance.case_dir / "task"
            ),
            "case_sha256": eval_cli._case_digest(instance.case_dir),
            "conformance_binding_sha256": "different-binding",
            "adapter_profile": "conformance_mock",
            "runtime_mode": None,
            "resource_policy_sha256": None,
            "model": "model-a",
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(eval_cli, "run_conformance", _passing_conformance)
    args = _run_args(manifest_path, output, config=config, resume=True)

    with pytest.raises(ValueError, match="resume rejected adapter binding drift"):
        asyncio.run(eval_cli._run_manifest(args))
