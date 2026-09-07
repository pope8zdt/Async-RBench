from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from async_rbench.evaluation.case_contract import ContractError
from async_rbench.track_b.adapter import FrameworkModelBackend, build_public_context
from async_rbench.track_b.config import TrackBConfig
from async_rbench.track_b.contracts import FrameworkResult, HarnessAction


ROOT = Path(__file__).resolve().parents[1]


class _Runtime:
    async def run(self, request):
        assert request.metadata["role"] == "main"
        assert request.messages[0]["content"] == "solve"
        return FrameworkResult(
            output_text="done",
            actions=(HarnessAction("finish", {"status": "completed", "summary": "done"}),),
            usage={"input_tokens": 7, "output_tokens": 3},
        )


def test_framework_backend_converts_actions_to_model_tool_calls() -> None:
    backend = FrameworkModelBackend(
        TrackBConfig(track="B", framework="deterministic", model="fixture"),
        _Runtime(),
    )

    turn = asyncio.run(backend.complete(
        role="main",
        model="fixture",
        messages=[{"role": "user", "content": "solve"}],
        tools=[{"type": "function", "function": {"name": "finish"}}],
        seed=7,
    ))

    assert turn.assistant_message["content"] == "done"
    assert turn.tool_calls[0].name == "finish"
    assert turn.tool_calls[0].arguments == {"status": "completed", "summary": "done"}
    assert turn.total_tokens == 10


def test_adapter_rejects_private_context_field() -> None:
    with pytest.raises(ContractError, match="private"):
        build_public_context({"instruction": "x", "authoritative_result_kind": "authority"})


def test_adapter_builds_context_from_public_episode_start() -> None:
    context = build_public_context({
        "episode_id": "episode-1",
        "execution_mode": "async",
        "instruction": "solve",
        "workstreams": [{"id": "ws-1", "task": "inspect"}],
    })

    assert context.episode_id == "episode-1"
    assert context.execution_mode == "async"
    assert context.workstreams[0]["id"] == "ws-1"


def test_adapter_script_imports_package_outside_repository_cwd(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "adapters" / "track_b.py"), "--help"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Track B adapter" in completed.stdout
