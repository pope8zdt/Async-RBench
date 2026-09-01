from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from pathlib import Path

import pytest

from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.evaluation.workspace_runtime import DockerWorkspaceRuntime
from async_rbench.evaluation.runner import _cleanup_workspace_resources


pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.getenv("ASYNC_RBENCH_RUN_DOCKER_TESTS") != "1", reason="opt-in Docker mutation test")
def test_dynamic_fourth_and_fifth_child_snapshots_use_valid_docker_names():
    suffix = uuid.uuid4().hex[:10]
    main_container = f"dtb2-dynamic-child-test-{suffix}"
    subprocess.run(
        ["docker", "run", "-d", "--name", main_container, "ubuntu:24.04", "sleep", "300"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    async def exercise() -> None:
        config = ScaffoldConfig(
            backend="scripted_test", main_model="scripted-test", child_model="scripted-test",
            workspace_mode="container_clone", max_total_child_spawns=5,
        )
        manager = DockerWorkspaceRuntime(
            main_container,
            "secure-release-0-async-6ce9da66",
            f"run-{suffix}",
            config,
        )
        try:
            fourth = await manager.create_child("child-4")
            fifth = await manager.create_child("child-5")
            assert fourth != fifth
            for child_id, container in (("child-4", fourth), ("child-5", fifth)):
                assert subprocess.run(
                    ["docker", "inspect", container],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                ).returncode == 0
                result = await manager.child_terminal(
                    child_id, f"printf {child_id}", 30
                )
                assert result.exit_code == 0 and result.output == child_id
        finally:
            await manager.cleanup()

    try:
        asyncio.run(exercise())
    finally:
        subprocess.run(
            ["docker", "rm", "-f", main_container], check=False,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )


@pytest.mark.skipif(os.getenv("ASYNC_RBENCH_RUN_DOCKER_TESTS") != "1", reason="opt-in Docker mutation test")
def test_child_container_is_hidden_until_promoted():
    suffix = uuid.uuid4().hex[:10]
    main_container = f"dtb2-workspace-test-{suffix}"
    subprocess.run(
        ["docker", "run", "-d", "--name", main_container, "ubuntu:24.04", "sleep", "300"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    async def exercise() -> None:
        config = ScaffoldConfig(
            backend="scripted_test",
            main_model="scripted-test",
            child_model="scripted-test",
            workspace_mode="container_clone",
        )
        manager = DockerWorkspaceRuntime(
            main_container, f"workspace-test-{suffix}", f"run-{suffix}", config
        )
        second = DockerWorkspaceRuntime(
            main_container, f"workspace-test-{suffix}", f"other-{suffix}", config
        )
        try:
            first_name = await manager.create_child("child-1")
            second_name = await second.create_child("child-1")
            assert first_name != second_name
            written = await manager.child_terminal("child-1", "printf child-only > /child-result.txt", 30)
            assert written.exit_code == 0
            hidden = await manager.main_terminal("test ! -e /child-result.txt", 30)
            assert hidden.exit_code == 0
            promoted = await manager.promote("child-1", "/child-result.txt", "/promoted-result.txt")
            assert promoted.exit_code == 0
            visible = await manager.main_terminal("cat /promoted-result.txt", 30)
            assert visible.exit_code == 0 and visible.output == "child-only"
        finally:
            await manager.cleanup()
            await second.cleanup()

        preserved_config = ScaffoldConfig(
            backend="scripted_test", main_model="scripted-test", child_model="scripted-test",
            workspace_mode="container_clone", keep_child_workspaces=True,
        )
        preserved = DockerWorkspaceRuntime(
            main_container, f"workspace-test-{suffix}", suffix, preserved_config
        )
        preserved_name = await preserved.create_child("child-1")
        await preserved.cleanup()
        assert subprocess.run(
            ["docker", "inspect", preserved_name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        ).returncode == 0
        _cleanup_workspace_resources(suffix)
        assert subprocess.run(
            ["docker", "inspect", preserved_name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        ).returncode != 0

    try:
        asyncio.run(exercise())
    finally:
        subprocess.run(
            ["docker", "rm", "-f", main_container],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )


@pytest.mark.skipif(os.getenv("ASYNC_RBENCH_RUN_DOCKER_TESTS") != "1", reason="opt-in Docker mutation test")
def test_event_asset_is_hidden_from_main_and_unassigned_children():
    suffix = uuid.uuid4().hex[:10]
    main_container = f"dtb2-event-asset-test-{suffix}"
    subprocess.run(
        ["docker", "run", "-d", "--name", main_container, "ubuntu:24.04", "sleep", "300"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    async def exercise() -> None:
        config = ScaffoldConfig(
            backend="scripted_test", main_model="scripted-test", child_model="scripted-test",
            workspace_mode="container_clone",
        )
        manager = DockerWorkspaceRuntime(
            main_container, f"event-asset-{suffix}", f"event-{suffix}", config
        )
        try:
            seeded = await manager.main_terminal(
                "printf authoritative-only > /event-secret.txt", 30
            )
            assert seeded.exit_code == 0
            assets = {"authoritative": ["/event-secret.txt"]}
            await manager.prepare_event_assets(assets)
            assert (await manager.main_terminal("test ! -e /event-secret.txt", 30)).exit_code == 0

            await manager.create_child("child-authority")
            await manager.create_child("child-support")
            await manager.stage_child_assets(
                "child-authority", ["authoritative"], assets
            )
            await manager.stage_child_assets("child-support", ["support"], assets)
            visible = await manager.child_terminal(
                "child-authority", "cat /event-secret.txt", 30
            )
            hidden = await manager.child_terminal(
                "child-support", "test ! -e /event-secret.txt", 30
            )
            assert visible.exit_code == 0 and visible.output == "authoritative-only"
            assert hidden.exit_code == 0
        finally:
            await manager.cleanup()

    try:
        asyncio.run(exercise())
    finally:
        subprocess.run(
            ["docker", "rm", "-f", main_container], check=False,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )


def test_host_event_asset_mapping_is_scoped_to_task_root(tmp_path):
    task = tmp_path / "task"
    event = task / "events" / "authority.json"
    event.parent.mkdir(parents=True)
    event.write_text('{"authority": true}', encoding="utf-8")
    config = ScaffoldConfig(
        backend="scripted_test", main_model="scripted-test", child_model="scripted-test",
        workspace_mode="container_clone",
    )
    manager = DockerWorkspaceRuntime(
        "unused", "host-event", "host-event", config,
        event_asset_source_root=task,
    )

    assert manager._host_event_asset("/app/events/authority.json") == event.resolve()
    assert manager._host_event_asset("/app/../private.txt") is None
    assert manager._host_event_asset("/other/events/authority.json") is None


def test_host_event_asset_mapping_accepts_task_file_runtime_script(tmp_path):
    """A participant event asset must use its in-container /app task_file path."""
    task = tmp_path / "task"
    worker = task / "task_file" / "scripts" / "event_worker.py"
    worker.parent.mkdir(parents=True)
    worker.write_text("# event asset\n", encoding="utf-8")
    config = ScaffoldConfig(
        backend="scripted_test", main_model="scripted-test", child_model="scripted-test",
        workspace_mode="container_clone",
    )
    manager = DockerWorkspaceRuntime(
        "unused", "host-event", "host-event", config,
        event_asset_source_root=task,
    )

    assert manager._host_event_asset("/app/task_file/scripts/event_worker.py") == worker.resolve()


def test_host_event_asset_mapping_accepts_legacy_task_prefix(tmp_path):
    """Legacy cases author event assets as task/<rel> (no /app/ prefix). These
    resolve against the task build context root, so they never need to exist in
    the participant image."""
    task = tmp_path / "task"
    worker = task / "upstream_solutions" / "event_worker.py"
    worker.parent.mkdir(parents=True)
    worker.write_text("# event worker\n", encoding="utf-8")
    config = ScaffoldConfig(
        backend="scripted_test", main_model="scripted-test", child_model="scripted-test",
        workspace_mode="container_clone",
    )
    manager = DockerWorkspaceRuntime(
        "unused", "host-event", "host-event", config,
        event_asset_source_root=task,
    )

    assert manager._host_event_asset("task/upstream_solutions/event_worker.py") == worker.resolve()
    assert manager._host_event_asset("../private.txt") is None
    assert manager._host_event_asset("other/upstream_solutions/event_worker.py") is None


def test_host_event_asset_locates_by_basename_when_destination_mismatches(tmp_path):
    """Some cases author a destination path that does not match the on-disk layout
    (e.g. /app/task_file/scripts/event_worker.py while the file sits under
    upstream_solutions/). The destination stays as authored; the host source is
    located uniquely by basename, and an ambiguous multi-match falls back to None."""
    task = tmp_path / "task"
    (task / "task_file" / "scripts").mkdir(parents=True)
    (task / "task_file" / "scripts" / "write_manifest.py").write_text("# m\n", encoding="utf-8")
    worker = task / "upstream_solutions" / "event_worker.py"
    worker.parent.mkdir(parents=True)
    worker.write_text("# event worker\n", encoding="utf-8")
    config = ScaffoldConfig(
        backend="scripted_test", main_model="scripted-test", child_model="scripted-test",
        workspace_mode="container_clone",
    )
    manager = DockerWorkspaceRuntime(
        "unused", "host-event", "host-event", config,
        event_asset_source_root=task,
    )

    # Destination path is wrong, but the file exists uniquely under upstream_solutions/.
    assert manager._host_event_asset("/app/task_file/scripts/event_worker.py") == worker.resolve()


def test_host_event_asset_basename_fallback_is_ambiguous_only(tmp_path):
    """When the authored destination misses and two files share the basename, the
    resolver must NOT guess: it returns None so the docker-cp path is used."""
    task = tmp_path / "task"
    for sub in ("a", "b"):
        (task / sub).mkdir(parents=True)
        (task / sub / "asset.json").write_text(sub, encoding="utf-8")
    config = ScaffoldConfig(
        backend="scripted_test", main_model="scripted-test", child_model="scripted-test",
        workspace_mode="container_clone",
    )
    manager = DockerWorkspaceRuntime(
        "unused", "host-event", "host-event", config,
        event_asset_source_root=task,
    )

    assert manager._host_event_asset("/app/nowhere/asset.json") is None


@pytest.mark.skipif(os.getenv("ASYNC_RBENCH_RUN_DOCKER_TESTS") != "1", reason="opt-in Docker mutation test")
def test_secure_authority_bundle_changes_revision_and_is_workstream_scoped():
    subprocess.run(
        ["docker", "build", "-t", "async_rbench-secure-release:locked",
         str(ROOT / "cases/secure-release/task")],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    suffix = uuid.uuid4().hex[:10]
    main_container = f"dtb2-secure-event-test-{suffix}"
    subprocess.run(
        ["docker", "run", "-d", "--name", main_container,
         "async_rbench-secure-release:locked", "sleep", "300"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    async def exercise() -> None:
        config = ScaffoldConfig(
            backend="scripted_test", main_model="scripted-test", child_model="scripted-test",
            workspace_mode="container_clone",
        )
        manager = DockerWorkspaceRuntime(
            main_container, f"secure-event-{suffix}", f"secure-{suffix}", config
        )
        assets = {"sanitize_history": ["/app/events/authoritative-release.bundle"]}
        try:
            initial = await manager.main_terminal(
                "git -C /app/repo rev-parse main; git -C /app/repo rev-parse dev", 30
            )
            assert initial.exit_code == 0
            initial_heads = set(initial.output.splitlines())
            await manager.prepare_event_assets(assets)
            assert (await manager.main_terminal(
                "test ! -e /app/events/authoritative-release.bundle", 30
            )).exit_code == 0
            await manager.create_child("authority")
            await manager.create_child("patch")
            await manager.stage_child_assets("authority", ["sanitize_history"], assets)
            await manager.stage_child_assets("patch", ["patch_pre_rewrite"], assets)
            authority = await manager.child_terminal(
                "authority",
                "test -s /app/events/authoritative-release.bundle && "
                "git bundle list-heads /app/events/authoritative-release.bundle",
                30,
            )
            hidden = await manager.child_terminal(
                "patch", "test ! -e /app/events/authoritative-release.bundle", 30
            )
            assert authority.exit_code == 0 and hidden.exit_code == 0
            authority_heads = {line.split()[0] for line in authority.output.splitlines() if line.strip()}
            assert authority_heads and authority_heads.isdisjoint(initial_heads)
        finally:
            await manager.cleanup()

    try:
        asyncio.run(exercise())
    finally:
        subprocess.run(
            ["docker", "rm", "-f", main_container], check=False,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
