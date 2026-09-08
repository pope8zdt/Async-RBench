from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from async_rbench.track_b.submission import package_run, validate_package
from async_rbench.track_b import cli as track_b_cli


COMMIT = "a" * 40
CONFIG_SHA = "b" * 64
AGENT_IMAGE = "sha256:" + "c" * 64
TASK_IMAGE = "sha256:" + "d" * 64


def _episode(mode: str) -> dict:
    return {
        "episode_id": f"case-a-0-{mode}-episode",
        "case_id": "case-a",
        "instance_id": "seed-1",
        "repeat": 0,
        "execution_mode": mode,
        "counterfactual_pair_id": "case-a-seed-1-0",
    }


def _score(mode: str, *, child_infrastructure_failure: int = 0) -> dict:
    return {
        **_episode(mode),
        "score_status": "scored",
        "protocol_valid": True,
        "scenario_constructed": True,
        "conformance_passed": True,
        "infrastructure_failures": [],
        "child_terminal_counts": {
            "infrastructure_failure": child_infrastructure_failure,
        },
        "base_task_score": 0.25 if mode == "linear" else 0.5,
        "async_drs": 0.75 if mode == "async" else None,
        "requested_model": "model-a",
        "evaluation_contract_version": "11.0.0",
        "score_policy_version": "policy-a",
        "case_sha256": "e" * 64,
        "verifier_bundle_sha256": "f" * 64,
        "agent_seed": 2026,
        "participant_image_id": TASK_IMAGE,
        "participant_metadata": {
            "track": "B",
            "framework": "codex-cli",
            "model": "model-a",
            "config_sha256": CONFIG_SHA,
            "components": {"agent_policy": "example.policy:build"},
            "agent_runtime": {"image_id": AGENT_IMAGE, "os": "linux"},
            "runtime": {
                "type": "docker",
                "image": AGENT_IMAGE,
                "cpus": 0.5,
                "memory": "768m",
                "timeout_sec": 2400,
            },
            "secret": "DO NOT EXPORT",
        },
    }


def _run(tmp_path: Path, *, child_infrastructure_failure: int = 0) -> tuple[Path, Path]:
    episodes = [_episode("linear"), _episode("async")]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({
            "track": "B",
            "seed": 2026,
            "repetitions": 1,
            "episodes": episodes,
        }),
        encoding="utf-8",
    )
    manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    runs = tmp_path / "runs"
    for episode in episodes:
        directory = runs / episode["episode_id"]
        directory.mkdir(parents=True)
        score = _score(
            episode["execution_mode"],
            child_infrastructure_failure=(
                child_infrastructure_failure
                if episode["execution_mode"] == "async"
                else 0
            ),
        )
        score["manifest_sha256"] = manifest_sha
        score["manifest_episode_count"] = len(episodes)
        (directory / "score.json").write_text(json.dumps(score), encoding="utf-8")
    return manifest, runs


def test_package_exports_only_valid_aggregate_metrics(tmp_path: Path) -> None:
    manifest, runs = _run(tmp_path)

    package = package_run(runs, manifest, benchmark_commit=COMMIT)

    validate_package(package)
    assert package["track"] == "B"
    assert package["record"]["framework"] == "codex-cli"
    assert package["record"]["model"] == "model-a"
    assert package["record"]["caseCount"] == 1
    assert package["record"]["plannedEpisodes"] == 2
    assert package["record"]["completedEpisodes"] == 2
    assert package["record"]["validEpisodes"] == 2
    assert package["record"]["validPairs"] == 1
    assert package["record"]["pairedComplete"] is True
    assert package["record"]["metrics"] == {
        "linearBts": 0.25,
        "asyncBts": 0.5,
        "btsAsyncMinusLinear": 0.25,
        "asyncDrs": 0.75,
    }
    assert package["record"]["runtime"] == {
        "type": "docker",
        "imageId": AGENT_IMAGE,
        "os": "linux",
        "cpus": 0.5,
        "memory": "768m",
        "timeoutSec": 2400,
    }
    assert package["record"]["components"] == ["agent_policy"]
    assert "case-a" not in json.dumps(package)
    assert "DO NOT EXPORT" not in json.dumps(package)


def test_package_excludes_pair_with_child_infrastructure_failure(tmp_path: Path) -> None:
    manifest, runs = _run(tmp_path, child_infrastructure_failure=1)

    package = package_run(runs, manifest, benchmark_commit=COMMIT)

    assert package["record"]["completedEpisodes"] == 2
    assert package["record"]["validEpisodes"] == 1
    assert package["record"]["validPairs"] == 0
    assert package["record"]["pairedComplete"] is False
    assert package["record"]["metrics"] == {
        "linearBts": None,
        "asyncBts": None,
        "btsAsyncMinusLinear": None,
        "asyncDrs": None,
    }


def test_package_rejects_runtime_drift_within_pair(tmp_path: Path) -> None:
    manifest, runs = _run(tmp_path)
    async_score = runs / "case-a-0-async-episode" / "score.json"
    payload = json.loads(async_score.read_text(encoding="utf-8"))
    payload["participant_metadata"]["agent_runtime"]["image_id"] = "sha256:" + "1" * 64
    async_score.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="agent runtime image"):
        package_run(runs, manifest, benchmark_commit=COMMIT)


def test_package_rejects_score_from_another_manifest(tmp_path: Path) -> None:
    manifest, runs = _run(tmp_path)
    async_score = runs / "case-a-0-async-episode" / "score.json"
    payload = json.loads(async_score.read_text(encoding="utf-8"))
    payload["manifest_sha256"] = "1" * 64
    async_score.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest digest"):
        package_run(runs, manifest, benchmark_commit=COMMIT)


def test_validate_package_rejects_metric_tampering(tmp_path: Path) -> None:
    manifest, runs = _run(tmp_path)
    package = package_run(runs, manifest, benchmark_commit=COMMIT)
    package["record"]["metrics"]["asyncDrs"] = 0.1

    with pytest.raises(ValueError, match="content digest"):
        validate_package(package)


def test_cli_packages_and_validates_public_result(tmp_path: Path, capsys) -> None:
    manifest, runs = _run(tmp_path)
    output = tmp_path / "public" / "track-b-result.json"

    assert track_b_cli.main([
        "package",
        "--runs", str(runs),
        "--manifest", str(manifest),
        "--benchmark-commit", COMMIT,
        "--output", str(output),
    ]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["submissionId"] == json.loads(
        output.read_text(encoding="utf-8")
    )["submissionId"]
    assert created["validPairs"] == 1

    assert track_b_cli.main([
        "validate-package", "--input", str(output),
    ]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked == {
        "submissionId": created["submissionId"],
        "valid": True,
    }


def test_cli_never_overwrites_an_existing_package(tmp_path: Path) -> None:
    manifest, runs = _run(tmp_path)
    output = tmp_path / "result.json"
    output.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        track_b_cli.main([
            "package",
            "--runs", str(runs),
            "--manifest", str(manifest),
            "--benchmark-commit", COMMIT,
            "--output", str(output),
        ])
    assert output.read_text(encoding="utf-8") == "keep"
