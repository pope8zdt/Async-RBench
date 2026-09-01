from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import async_rbench.evaluation.runner as runner_module
from async_rbench.evaluation.runner import (
    EpisodeConfig, _cleanup_workspace_resources, run_episode,
)
from async_rbench.evaluation.workspace_runtime import DisabledWorkspaceRuntime
from async_rbench.private_eval import PrivateVerificationResult


ROOT = Path(__file__).resolve().parents[1]


class _FakeProcess:
    def __init__(self, events: list[dict]) -> None:
        self.stdin = self._Stdin()
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.stdout.feed_data(
            b"".join(json.dumps(event).encode("utf-8") + b"\n" for event in events)
        )
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        self.returncode = 0

    class _Stdin:
        def write(self, _payload: bytes) -> None:
            return None

        async def drain(self) -> None:
            return None

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


def test_workspace_sweep_requires_the_child_role_label(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_docker(*args: str, **_kwargs):
        calls.append(args)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(runner_module, "_docker", fake_docker)
    _cleanup_workspace_resources("abcdef123456")

    assert calls[0] == (
        "ps", "-aq", "--filter", "label=async_rbench.workspace_run_id=abcdef123456",
        "--filter", "label=async_rbench.managed=child",
    )


def test_private_verifier_runs_before_participant_or_workspace_teardown(
    tmp_path: Path, monkeypatch,
) -> None:
    """The submitted main container is still available at verifier commit time."""
    lifecycle: list[str] = []

    class TrackingWorkspace(DisabledWorkspaceRuntime):
        async def cleanup(self) -> None:
            lifecycle.append("workspace_cleanup")

    async def fake_subprocess(*_args, **_kwargs):
        return _FakeProcess([
            {
                "type": "participant_metadata",
                "backend": "scripted_test",
                "main_model": "scripted-main",
                "child_model": "scripted-child",
                "workspace_mode": "container_clone",
            },
            {"type": "ready"},
            {
                "type": "episode_ended", "final_answer": "done",
                "local_status": "completed", "declared_task_success": True,
            },
        ])

    def fake_docker(*args: str, **_kwargs):
        if args[:3] == ("rm", "-f", "main-under-test"):
            lifecycle.append("participant_teardown")
        return SimpleNamespace(stdout="", returncode=0)

    def fake_verifier(*, main_container: str, **_kwargs) -> PrivateVerificationResult:
        assert main_container == "main-under-test"
        # This models the verifier's initial contamination audit/commit.  The
        # cleanup callbacks must not have run when it needs the main container.
        assert lifecycle == []
        lifecycle.append("private_verifier")
        return PrivateVerificationResult(True, 0, "1 passed", "a" * 64)

    monkeypatch.setattr(
        runner_module, "_prepare_container",
        lambda *_args, **_kwargs: ("participant-image", "main-under-test", "sha256:image"),
    )
    monkeypatch.setattr(runner_module, "audit_participant_container", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner_module, "build_workspace_runtime", lambda *_args, **_kwargs: TrackingWorkspace())
    monkeypatch.setattr(runner_module, "run_isolated_verifier", fake_verifier)
    monkeypatch.setattr(runner_module, "_docker", fake_docker)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)

    config = EpisodeConfig(
        episode_id="verifier-lifecycle", case_id="data-recovery-service",
        execution_mode="linear", guidance="incentive", agent_seed=1,
        adapter_command=["fake-adapter"], output_dir=tmp_path,
        use_container=True, timeout_sec=10,
    )
    asyncio.run(run_episode(ROOT, config))

    assert lifecycle == [
        "private_verifier", "workspace_cleanup", "participant_teardown",
    ]
