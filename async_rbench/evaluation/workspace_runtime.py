from __future__ import annotations

import asyncio
import re
import tempfile
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class WorkspaceConfig(Protocol):
    """Minimal config surface the workspace runtime reads from a participant config."""

    workspace_mode: str
    child_terminal_timeout_sec: int
    keep_child_workspaces: bool


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    output: str


async def _command(*args: str, timeout: float | None = None) -> CommandResult:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        output, _ = await process.communicate()
        return CommandResult(124, output.decode(errors="replace") + "\ncommand timed out")
    return CommandResult(int(process.returncode or 0), output.decode(errors="replace"))


def _safe_name(value: str, limit: int = 48) -> str:
    # Docker repository components do not accept arbitrary mixtures of
    # separators (for example ``_-``).  Normalise every separator run to one
    # hyphen, then trim again *after* truncation so a length boundary cannot
    # leave a dangling separator before the next name component is appended.
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    truncated = cleaned[:limit].rstrip("-")
    return truncated or "item"


def event_assets_for_workstreams(event_assets: dict[str, list[str]], work_units: list[str]) -> set[str]:
    """The event assets a child may receive, scoped to its own workstreams."""
    return {
        str(path)
        for workstream in work_units
        for path in event_assets.get(workstream, [])
    }


class WorkspaceRuntime:
    async def create_child(self, child_id: str) -> str: ...
    async def prepare_event_assets(self, event_assets: dict[str, list[str]]) -> None: ...
    async def stage_child_assets(self, child_id: str, work_units: list[str], event_assets: dict[str, list[str]]) -> None: ...
    async def main_terminal(self, command: str, timeout: int) -> CommandResult: ...
    async def child_terminal(self, child_id: str, command: str, timeout: int) -> CommandResult: ...
    async def promote(self, child_id: str, source_path: str, destination_path: str) -> CommandResult: ...
    async def observe_artifact(self, artifact_id: str) -> dict[str, str]: ...
    async def verify_current_state(
        self, artifact_ids: list[str], lineage_completion_ids: list[str],
    ) -> dict[str, object]: ...
    async def cleanup_child(self, child_id: str) -> None: ...
    async def cleanup(self) -> None: ...


class DockerWorkspaceRuntime(WorkspaceRuntime):
    """Copy-on-write child isolation using a snapshot image per child."""

    def __init__(
        self,
        main_container: str,
        episode_id: str,
        workspace_run_id: str,
        config: WorkspaceConfig,
        event_asset_source_root: Path | None = None,
    ) -> None:
        self.main_container = main_container
        self.episode_id = _safe_name(episode_id, 26)
        self.workspace_run_id = _safe_name(workspace_run_id, 16)
        self.config = config
        self.child_containers: dict[str, str] = {}
        self.child_images: dict[str, str | None] = {}
        self._event_asset_root: Path | None = None
        self._event_asset_files: dict[str, Path] = {}
        self._event_asset_source_root = (
            event_asset_source_root.resolve() if event_asset_source_root else None
        )

    def _host_event_asset(self, container_path: str) -> Path | None:
        """Resolve an image-layout path to a private file in the task build context.

        New cases keep event assets out of the participant image entirely.  Their
        conventional ``/app/...`` destination maps to the same relative path in
        ``task/`` (for example ``/app/events/x.json`` -> ``task/events/x.json``).
        Some registered cases author the asset path directly as ``task/<rel>``
        (for example ``task/upstream_solutions/event_worker.py``); those resolve
        against the same task root with the ``task/`` prefix stripped.  Where the
        authored path does not match the on-disk layout, the asset is located by
        basename within the task build context (destination unchanged).  Older
        cases may still transform or create an asset in the image, so when no
        host candidate exists a deliberate ``docker cp`` fallback is used below.
        """
        root = self._event_asset_source_root
        if root is None:
            return None
        if container_path.startswith("/app/"):
            pure = Path(container_path.replace("/app/", "", 1))
        elif container_path.startswith("task/"):
            pure = Path(container_path[len("task/"):])
        else:
            return None
        if pure.is_absolute() or ".." in pure.parts:
            return None
        candidate = (root / pure).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        if candidate.exists():
            return candidate
        # Authored destinations sometimes exceed the real layout: the asset lives
        # elsewhere in the same task build context (e.g. the path says
        # /app/task_file/scripts/event_worker.py but the file is under
        # upstream_solutions/). Locate it by basename, deterministically: use it
        # only when there is exactly one match, otherwise fall through to the
        # docker-cp path used by legacy in-image assets.
        matches = [p for p in root.rglob(pure.name) if p.is_file()]
        return matches[0].resolve() if len(matches) == 1 else None

    def _container_asset_destination(self, container_path: str) -> str:
        """The in-container path an event asset is staged to.

        ``/app/...`` destinations are already absolute and are used verbatim.
        Some cases author the asset path as ``task/<rel>``
        (``task/upstream_solutions/event_worker.py``): that ``task/`` label is
        the build-context root, and the equivalent location inside a task
        container is the legacy evaluator helper mount ``/async_rbench/<rel>``.
        Normalise it so ``mkdir -p`` and ``docker cp`` always address a real
        absolute path; anything malformed is left as authored.
        """
        if container_path.startswith("task/"):
            rest = container_path[len("task/"):]
            pure = Path(rest)
            if pure.is_absolute() or ".." in pure.parts:
                return container_path
            return "/async_rbench/" + rest
        return container_path

    async def prepare_event_assets(self, event_assets: dict[str, list[str]]) -> None:
        paths = sorted({str(path) for values in event_assets.values() for path in values})
        if not paths:
            return
        self._event_asset_root = Path(tempfile.mkdtemp(prefix="async_rbench-event-assets-"))
        for index, path in enumerate(paths):
            local = self._event_asset_root / f"asset-{index}"
            host_source = self._host_event_asset(path)
            if host_source is not None:
                if host_source.is_dir():
                    shutil.copytree(host_source, local)
                else:
                    shutil.copy2(host_source, local)
            else:
                copied = await _command(
                    "docker", "cp", f"{self.main_container}:{path}", str(local),
                    timeout=self.config.child_terminal_timeout_sec,
                )
                if copied.exit_code != 0:
                    raise RuntimeError(f"failed to isolate event asset {path}: {copied.output[-4000:]}")
                removed = await _command(
                    "docker", "exec", self.main_container, "rm", "-rf", path,
                    timeout=self.config.child_terminal_timeout_sec,
                )
                if removed.exit_code != 0:
                    raise RuntimeError(f"failed to hide event asset {path}: {removed.output[-4000:]}")
            self._event_asset_files[path] = local

    async def stage_child_assets(self, child_id: str, work_units: list[str], event_assets: dict[str, list[str]]) -> None:
        container = self.child_containers.get(child_id)
        if not container:
            raise RuntimeError(f"unknown child workspace {child_id}")
        requested = event_assets_for_workstreams(event_assets, work_units)
        for path in sorted(requested):
            local = self._event_asset_files.get(path)
            if local is None:
                raise RuntimeError(f"event asset was not prepared: {path}")
            destination = self._container_asset_destination(path)
            parent = str(Path(destination).parent).replace("\\", "/")
            created = await _command("docker", "exec", container, "mkdir", "-p", parent, timeout=60)
            if created.exit_code != 0:
                raise RuntimeError(f"failed to prepare event asset parent {parent}")
            copied = await _command("docker", "cp", str(local), f"{container}:{destination}", timeout=120)
            if copied.exit_code != 0:
                raise RuntimeError(f"failed to stage event asset {path}: {copied.output[-4000:]}")

    async def create_child(self, child_id: str) -> str:
        safe_child = _safe_name(child_id, 12)
        image = f"async_rbench-child-{self.episode_id}-{self.workspace_run_id}-{safe_child}:snapshot"
        container = _safe_name(
            f"dtb2c-{self.episode_id}-{self.workspace_run_id}-{safe_child}", 63
        )
        committed = await _command(
            "docker", "commit",
            "--change", "LABEL async_rbench.managed=child",
            "--change", f"LABEL async_rbench.workspace_run_id={self.workspace_run_id}",
            self.main_container, image,
            timeout=self.config.child_terminal_timeout_sec,
        )
        if committed.exit_code != 0:
            raise RuntimeError(f"failed to snapshot main container: {committed.output[-4000:]}")
        started = await _command(
            "docker", "run", "-d", "--name", container,
            "--label", "async_rbench.managed=child",
            "--label", f"async_rbench.workspace_run_id={self.workspace_run_id}",
            image,
            timeout=self.config.child_terminal_timeout_sec,
        )
        if started.exit_code != 0:
            await _command("docker", "image", "rm", "-f", image, timeout=60)
            raise RuntimeError(f"failed to start child container: {started.output[-4000:]}")
        self.child_containers[child_id] = container
        self.child_images[child_id] = image
        return container

    async def main_terminal(self, command: str, timeout: int) -> CommandResult:
        return await _command("docker", "exec", self.main_container, "bash", "-lc", command, timeout=timeout)

    async def child_terminal(self, child_id: str, command: str, timeout: int) -> CommandResult:
        container = self.child_containers.get(child_id)
        if not container:
            return CommandResult(2, f"unknown child workspace {child_id}")
        return await _command("docker", "exec", container, "bash", "-lc", command, timeout=timeout)

    async def promote(self, child_id: str, source_path: str, destination_path: str) -> CommandResult:
        container = self.child_containers.get(child_id)
        if not container:
            return CommandResult(2, f"unknown child workspace {child_id}")
        with tempfile.TemporaryDirectory(prefix="async_rbench-promote-") as directory:
            local = Path(directory) / "payload"
            copied_out = await _command("docker", "cp", f"{container}:{source_path}", str(local), timeout=120)
            if copied_out.exit_code != 0:
                return copied_out
            return await _command("docker", "cp", str(local), f"{self.main_container}:{destination_path}", timeout=120)

    async def cleanup_child(self, child_id: str) -> None:
        if self.config.keep_child_workspaces:
            return
        container = self.child_containers.pop(child_id, None)
        image = self.child_images.pop(child_id, None)
        if container:
            await _command("docker", "rm", "-f", container, timeout=60)
        if image:
            await _command("docker", "image", "rm", "-f", image, timeout=60)

    async def cleanup(self) -> None:
        for child_id in list(self.child_containers):
            await self.cleanup_child(child_id)
        if self._event_asset_root:
            shutil.rmtree(self._event_asset_root, ignore_errors=True)
            self._event_asset_root = None
            self._event_asset_files.clear()

class DisabledWorkspaceRuntime(WorkspaceRuntime):
    """Only for scaffold conformance tests; never use for scored Docker episodes."""

    async def create_child(self, child_id: str) -> str:
        return f"disabled:{child_id}"

    async def prepare_event_assets(self, event_assets: dict[str, list[str]]) -> None:
        return None

    async def stage_child_assets(self, child_id: str, work_units: list[str], event_assets: dict[str, list[str]]) -> None:
        return None

    async def main_terminal(self, command: str, timeout: int) -> CommandResult:
        return CommandResult(0, f"disabled workspace accepted command: {command}")

    async def child_terminal(self, child_id: str, command: str, timeout: int) -> CommandResult:
        return CommandResult(0, f"disabled child workspace accepted command: {command}")

    async def promote(self, child_id: str, source_path: str, destination_path: str) -> CommandResult:
        return CommandResult(0, f"disabled promotion {child_id}:{source_path} -> {destination_path}")

    async def cleanup_child(self, child_id: str) -> None:
        return None

    async def cleanup(self) -> None:
        return None

def build_workspace_runtime(
    start: dict,
    config: WorkspaceConfig,
    event_asset_source_root: Path | None = None,
) -> WorkspaceRuntime:
    container = start.get("container_name")
    if config.workspace_mode == "disabled":
        return DisabledWorkspaceRuntime()
    if not container:
        raise RuntimeError("container_clone workspace requires episode_start.container_name")
    run_id = str(start.get("workspace_run_id") or "legacy")
    return DockerWorkspaceRuntime(
        str(container), str(start["episode_id"]), run_id, config,
        event_asset_source_root=event_asset_source_root,
    )
