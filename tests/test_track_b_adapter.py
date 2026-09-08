from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from async_rbench.evaluation.case_contract import ContractError
from async_rbench.track_b.adapter import FrameworkModelBackend, build_public_context
from async_rbench.track_b.components import HarnessComponents
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


class _CustomContext:
    def __init__(self):
        self.contexts = []

    def build(self, context):
        from async_rbench.track_b.contracts import FrameworkRequest

        self.contexts.append(context)
        return FrameworkRequest(
            messages=({"role": "user", "content": "custom context"},),
            tools=context.tools,
        )


class _CustomPolicy:
    def select_actions(self, context, result):
        return (HarnessAction("finish", {"status": "incomplete", "summary": "policy"}),)


class _Delegation:
    def initial_actions(self, context):
        return (HarnessAction("list_subagents", {}),)


class _Hooks:
    def __init__(self):
        self.events = []

    def on_event(self, event):
        self.events.append(dict(event))


class _CapturingRuntime:
    def __init__(self):
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        return FrameworkResult(output_text="runtime")


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


def test_framework_backend_applies_custom_harness_components() -> None:
    runtime = _CapturingRuntime()
    hooks = _Hooks()
    context_builder = _CustomContext()
    backend = FrameworkModelBackend(
        TrackBConfig(track="B", framework="deterministic", model="fixture"),
        runtime,
        episode_context=build_public_context({
            "episode_id": "episode-1",
            "execution_mode": "async",
            "instruction": "solve",
            "initial_wave": [{"id": "ws-1", "task": "inspect"}],
        }),
        components=HarnessComponents(
            context_builder=context_builder,
            delegation_policy=_Delegation(),
            agent_policy=_CustomPolicy(),
            lifecycle_hooks=hooks,
        ),
    )

    turn = asyncio.run(backend.complete(
        role="main",
        model="fixture",
        messages=[{"role": "user", "content": "original"}],
        tools=[{"type": "function", "function": {"name": "finish"}}],
        seed=2,
    ))

    assert runtime.requests[0].messages[0]["content"] == "custom context"
    assert context_builder.contexts[0].episode_id == "episode-1"
    assert context_builder.contexts[0].execution_mode == "async"
    assert context_builder.contexts[0].workstreams[0]["id"] == "ws-1"
    assert [call.name for call in turn.tool_calls] == ["list_subagents", "finish"]
    assert [event["type"] for event in hooks.events] == [
        "framework_turn_started",
        "framework_turn_finished",
    ]


def test_adapter_rejects_private_context_field() -> None:
    with pytest.raises(ContractError, match="private"):
        build_public_context({"instruction": "x", "authoritative_result_kind": "authority"})


def test_adapter_builds_context_from_public_episode_start() -> None:
    context = build_public_context({
        "episode_id": "episode-1",
        "execution_mode": "async",
        "instruction": "solve",
        "initial_wave": [{"id": "ws-1", "task": "inspect"}],
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
