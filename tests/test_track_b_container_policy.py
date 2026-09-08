from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from async_rbench.evaluation import runner, workspace_runtime
from async_rbench import private_eval


IMAGE_ID = "sha256:" + "a" * 64
ENV_KEYS = (
    "TRACK_B_CONTAINER_CPUS",
    "TRACK_B_CONTAINER_MEMORY",
    "TRACK_B_PARTICIPANT_IMAGE_IDS",
)


@pytest.fixture
def container_commands(tmp_path, monkeypatch):
    """Capture the external Docker boundary; never contact a Docker daemon."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    calls = []

    def fake_docker(*args, **kwargs):
        calls.append(args)
        output = IMAGE_ID if args[:2] == ("image", "inspect") else ""
        return SimpleNamespace(stdout=output, returncode=0)

    async def fake_command(*args, **kwargs):
        assert args[0] == "docker"
        calls.append(args[1:])
        return workspace_runtime.CommandResult(0, "")

    def fake_verifier_exec(args, **kwargs):
        assert args[:2] == ["docker", "exec"]
        calls.append(tuple(args[1:]))
        return SimpleNamespace(stdout=b"1 passed\n", returncode=0)

    monkeypatch.setattr(runner, "_docker", fake_docker)
    monkeypatch.setattr(private_eval, "_docker", fake_docker)
    monkeypatch.setattr(workspace_runtime, "_command", fake_command)
    monkeypatch.setattr(private_eval.subprocess, "run", fake_verifier_exec)
    task = tmp_path / "task"
    (task / "tests").mkdir(parents=True)
    (task / "run-tests.sh").write_text("true\n", encoding="utf-8")

    def invoke(role, **kwargs):
        if role == "participant":
            return runner._prepare_container(
                tmp_path, "case-a", "seed-1", "episode-a", True,
                "abcdef123456", tmp_path, **kwargs,
            )
        if role == "child":
            runtime = workspace_runtime.DockerWorkspaceRuntime(
                "main-a", "episode-a", "abcdef123456",
                SimpleNamespace(child_terminal_timeout_sec=10, keep_child_workspaces=False),
            )
            return asyncio.run(runtime.create_child("child-1"))
        return private_eval.run_isolated_verifier(
            main_container="main-a", task_dir=task, episode_id="episode-a",
        )

    return invoke, calls


@pytest.mark.parametrize("role", ["participant", "child", "verifier"])
def test_unset_limits_preserve_existing_container_commands(container_commands, role):
    invoke, calls = container_commands
    invoke(role)
    run = next(command for command in calls if command[0] == "run")
    assert "--cpus" not in run
    assert "--memory" not in run
    if role == "participant":
        assert calls[0][0:3] == ("build", "-t", "async_rbench-eval-case-a-seed-1:locked")
        assert run == (
            "run", "-d", "--name", "dtb2-episode-a-abcdef123456",
            "--label", "async_rbench.managed=participant",
            "async_rbench-eval-case-a-seed-1:locked",
        )


@pytest.mark.parametrize("role", ["participant", "child", "verifier"])
def test_process_limits_reach_each_container_role(container_commands, monkeypatch, role):
    invoke, calls = container_commands
    monkeypatch.setenv("TRACK_B_CONTAINER_CPUS", "0.25")
    monkeypatch.setenv("TRACK_B_CONTAINER_MEMORY", "512m")
    invoke(role)
    run = next(command for command in calls if command[0] == "run")
    assert "--cpus" in run
    assert run[run.index("--cpus") + 1] == "0.25"
    assert "--memory" in run
    assert run[run.index("--memory") + 1] == "512m"
    image_index = next(i for i, arg in enumerate(run) if arg.endswith((":locked", ":snapshot")))
    assert run.index("--cpus") < image_index
    assert run.index("--memory") < image_index


@pytest.mark.parametrize("role", ["participant", "child", "verifier"])
@pytest.mark.parametrize("key,value", [
    ("TRACK_B_CONTAINER_CPUS", "0"),
    ("TRACK_B_CONTAINER_CPUS", "-1"),
    ("TRACK_B_CONTAINER_CPUS", "nan"),
    ("TRACK_B_CONTAINER_CPUS", "inf"),
    ("TRACK_B_CONTAINER_CPUS", ""),
    ("TRACK_B_CONTAINER_CPUS", "0.25 --privileged"),
    ("TRACK_B_CONTAINER_MEMORY", "0m"),
    ("TRACK_B_CONTAINER_MEMORY", "-512m"),
    ("TRACK_B_CONTAINER_MEMORY", ""),
    ("TRACK_B_CONTAINER_MEMORY", "lots"),
    ("TRACK_B_CONTAINER_MEMORY", "512m --privileged"),
])
def test_invalid_limits_fail_before_any_docker_command(
    container_commands, monkeypatch, role, key, value,
):
    invoke, calls = container_commands
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match=key):
        invoke(role)
    assert calls == []


def test_track_b_immutable_image_skips_build_and_preserves_unique_name(
    container_commands, monkeypatch,
):
    invoke, calls = container_commands
    monkeypatch.setenv("TRACK_B_PARTICIPANT_IMAGE_IDS", json.dumps({"case-a::seed-1": IMAGE_ID}))
    image, container, image_id = invoke("participant", adapter_profile="track_b", official_track=False)
    assert (image, image_id) == (IMAGE_ID, IMAGE_ID)
    assert container == "dtb2-episode-a-abcdef123456"
    assert all(command[0] != "build" for command in calls)
    assert next(command for command in calls if command[0] == "run")[-1] == IMAGE_ID


@pytest.mark.parametrize("profile,official", [(None, False), ("reference_scaffold", False), ("track_b", True)])
def test_image_override_is_ignored_outside_nonofficial_track_b(
    container_commands, monkeypatch, profile, official,
):
    invoke, calls = container_commands
    monkeypatch.setenv("TRACK_B_PARTICIPANT_IMAGE_IDS", "deliberately invalid JSON")
    image, _, _ = invoke("participant", adapter_profile=profile, official_track=official)
    assert image == "async_rbench-eval-case-a-seed-1:locked"
    assert calls[0][:2] == ("build", "-t")


@pytest.mark.parametrize("mapping", [
    "bad JSON", "[]", "{}",
    json.dumps({"case-a::seed-1": "shared-tag:locked"}),
    json.dumps({"case-a::seed-1": "sha256:abc"}),
    json.dumps({"case-a::seed-1": 42}),
    json.dumps({"case-b::seed-1": IMAGE_ID}),
])
def test_bad_or_missing_image_mapping_never_falls_back_to_build(
    container_commands, monkeypatch, mapping,
):
    invoke, calls = container_commands
    monkeypatch.setenv("TRACK_B_PARTICIPANT_IMAGE_IDS", mapping)
    with pytest.raises(ValueError, match="TRACK_B_PARTICIPANT_IMAGE_IDS"):
        invoke("participant", adapter_profile="track_b", official_track=False)
    assert calls == []


def test_source_digest_changes_when_track_b_driver_changes(tmp_path: Path):
    for name in ("evaluation", "profiles", "conformance", "track_b"):
        (tmp_path / "async_rbench" / name).mkdir(parents=True)
    (tmp_path / "adapters").mkdir()
    for name in (
        "async_rbench/private_eval.py", "PROTOCOL.md", "ADAPTER_PROTOCOL.md",
        "evaluation_contract.json", "event_taxonomy.json",
    ):
        (tmp_path / name).write_text("fixture\n", encoding="utf-8")
    driver = tmp_path / "async_rbench" / "track_b" / "openai_driver.py"
    driver.write_text("version = 1\n", encoding="utf-8")
    initial = runner._source_digest(tmp_path)
    driver.write_text("version = 2\n", encoding="utf-8")
    assert runner._source_digest(tmp_path) != initial
