from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from async_rbench.evaluation import workspace_runtime as workspace_module
from async_rbench.evaluation.workspace_runtime import (
    CommandResult,
    DockerWorkspaceRuntime,
)


@dataclass(frozen=True)
class Config:
    workspace_mode: str = "container_clone"
    child_terminal_timeout_sec: int = 120
    keep_child_workspaces: bool = False


def test_one_validation_image_seeds_three_distinct_branch_containers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    image_id = "sha256:" + "a" * 64

    async def fake_command(*args: str, timeout: float | None = None) -> CommandResult:
        calls.append(tuple(args))
        if args[:2] == ("docker", "commit"):
            return CommandResult(0, image_id + "\n")
        if args[:2] == ("docker", "run"):
            return CommandResult(0, "container-id\n")
        return CommandResult(0, "")

    monkeypatch.setattr(workspace_module, "_command", fake_command)
    runtime = DockerWorkspaceRuntime(
        "source-main",
        "episode-validation",
        "run-validation",
        Config(),
    )

    async def exercise():
        snapshot = await runtime.capture_validation_snapshot(
            "checkpoint-1",
            tree_sha256="b" * 64,
        )
        branches = [
            await runtime.create_validation_branch(snapshot, condition)
            for condition in ("oracle_replan", "native_agent", "frozen_plan")
        ]
        return snapshot, branches

    snapshot, branches = asyncio.run(exercise())

    assert snapshot.image_id == image_id
    assert snapshot.tree_sha256 == "b" * 64
    assert {branch.image_id for branch in branches} == {image_id}
    assert {branch.tree_sha256 for branch in branches} == {"b" * 64}
    assert len({branch.container_name for branch in branches}) == 3
    assert len([call for call in calls if call[:2] == ("docker", "commit")]) == 1
    run_calls = [call for call in calls if call[:2] == ("docker", "run")]
    assert len(run_calls) == 3
    assert all(snapshot.image_name in call for call in run_calls)


def test_validation_snapshot_rejects_invalid_tree_digest() -> None:
    runtime = DockerWorkspaceRuntime(
        "source-main",
        "episode-validation",
        "run-validation",
        Config(),
    )

    with pytest.raises(ValueError, match="tree_sha256"):
        asyncio.run(
            runtime.capture_validation_snapshot("checkpoint-1", tree_sha256="bad")
        )


def test_validation_branch_rejects_unowned_snapshot() -> None:
    runtime = DockerWorkspaceRuntime(
        "source-main",
        "episode-validation",
        "run-validation",
        Config(),
    )
    foreign = workspace_module.ValidationWorkspaceSnapshot(
        snapshot_id="foreign",
        image_name="foreign:snapshot",
        image_id="sha256:" + "c" * 64,
        tree_sha256="d" * 64,
    )

    with pytest.raises(ValueError, match="not owned by this runtime"):
        asyncio.run(runtime.create_validation_branch(foreign, "native_agent"))


def test_inflight_child_workspace_can_be_captured_for_bundle_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    image_id = "sha256:" + "e" * 64

    async def fake_command(*args: str, timeout: float | None = None) -> CommandResult:
        calls.append(tuple(args))
        return CommandResult(0, image_id + "\n")

    monkeypatch.setattr(workspace_module, "_command", fake_command)
    runtime = DockerWorkspaceRuntime(
        "source-main",
        "episode-validation",
        "run-validation",
        Config(),
    )
    runtime.child_containers["child-1"] = "source-child-container"

    snapshot = asyncio.run(
        runtime.capture_validation_child_snapshot(
            "checkpoint-1",
            "child-1",
            tree_sha256="f" * 64,
        )
    )

    assert snapshot.image_id == image_id
    commit = next(call for call in calls if call[:2] == ("docker", "commit"))
    assert "source-child-container" in commit
    assert runtime.validation_snapshots[snapshot.snapshot_id] == snapshot


def test_normal_episode_cleanup_keeps_validation_images_until_explicit_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    image_id = "sha256:" + "1" * 64

    async def fake_command(*args: str, timeout: float | None = None) -> CommandResult:
        calls.append(tuple(args))
        if args[:2] == ("docker", "commit"):
            return CommandResult(0, image_id + "\n")
        return CommandResult(0, "ok\n")

    monkeypatch.setattr(workspace_module, "_command", fake_command)
    runtime = DockerWorkspaceRuntime(
        "source-main",
        "episode-validation",
        "run-validation",
        Config(),
    )

    async def exercise() -> None:
        await runtime.capture_validation_snapshot(
            "checkpoint-1", tree_sha256="2" * 64
        )
        await runtime.cleanup()
        assert runtime.validation_snapshots
        assert not any(call[:3] == ("docker", "image", "rm") for call in calls)
        await runtime.cleanup_validation_resources()

    asyncio.run(exercise())

    assert runtime.validation_snapshots == {}
    assert any(call[:3] == ("docker", "image", "rm") for call in calls)


def test_new_runtime_adopts_snapshot_only_when_docker_image_id_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_id = "sha256:" + "3" * 64

    async def fake_command(*args: str, timeout: float | None = None) -> CommandResult:
        return CommandResult(0, image_id + "\n")

    monkeypatch.setattr(workspace_module, "_command", fake_command)
    runtime = DockerWorkspaceRuntime(
        "new-main",
        "episode-validation",
        "run-validation",
        Config(),
    )
    snapshot = workspace_module.ValidationWorkspaceSnapshot(
        snapshot_id="checkpoint-1",
        image_name="main:snapshot",
        image_id=image_id,
        tree_sha256="4" * 64,
    )

    adopted = asyncio.run(runtime.adopt_validation_snapshot(snapshot))

    assert adopted == snapshot
    assert runtime.validation_snapshots == {"checkpoint-1": snapshot}

    mismatch = workspace_module.ValidationWorkspaceSnapshot(
        snapshot_id="checkpoint-2",
        image_name="other:snapshot",
        image_id="sha256:" + "5" * 64,
        tree_sha256="6" * 64,
    )
    with pytest.raises(RuntimeError, match="image id mismatch"):
        asyncio.run(runtime.adopt_validation_snapshot(mismatch))
