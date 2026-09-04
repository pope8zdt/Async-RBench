from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from async_rbench.evaluation.model_backend import ModelTurn, ToolCall
from async_rbench.evaluation.runner import EpisodeConfig, _make_start
from async_rbench.evaluation.workspace_runtime import DisabledWorkspaceRuntime
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.profiles.reference_scaffold_api.gateway import DeliveryReader, ProtocolEmitter
from async_rbench.profiles.reference_scaffold_api.runtime import ChildRecord, ReferenceScaffold
from async_rbench.spec import load_case


ROOT = Path(__file__).resolve().parents[1]


def _start() -> dict[str, Any]:
    case_path = ROOT / "cases" / "data-recovery-service" / "public_case.yaml"
    case = load_case(case_path).raw
    task = yaml.safe_load(
        (case_path.parent / "task" / "task.yaml").read_text(encoding="utf-8")
    )
    config = EpisodeConfig(
        episode_id="v101-runtime",
        case_id="data-recovery-service",
        execution_mode="async",
        guidance="incentive",
        agent_seed=1,
        adapter_command=[sys.executable],
        output_dir=ROOT / "artifacts" / "test-unused",
        use_container=False,
    )
    return _make_start(config, case, task, None, "0123456789ab")


def _scaffold(backend: Any, **overrides: Any) -> ReferenceScaffold:
    config = ScaffoldConfig.from_file(None, {
        "backend": "scripted_test",
        "workspace_mode": "disabled",
        **overrides,
    })
    scaffold = ReferenceScaffold(
        start=_start(),
        config=config,
        backend=backend,
        workspace=DisabledWorkspaceRuntime(),
        emitter=ProtocolEmitter(stdout=io.StringIO()),
        delivery_reader=DeliveryReader(stdin=io.StringIO()),
    )
    # Runtime-loop unit tests bypass the benchmark-owned initial-wave barrier.
    scaffold.messages = [
        {"role": "system", "content": scaffold._system_prompt()},
        {"role": "user", "content": str(scaffold.start["instruction"])},
    ]
    return scaffold


class NoToolBackend:
    def __init__(self, *, tokens: int = 7) -> None:
        self.calls = 0
        self.tokens = tokens

    async def complete(self, **_: Any) -> ModelTurn:
        self.calls += 1
        return ModelTurn(
            assistant_message={"role": "assistant", "content": "stop"},
            tool_calls=[],
            total_tokens=self.tokens,
        )

    def estimate_input_tokens(self, **_: Any) -> object:
        raise AssertionError("normal runtime must not perform token admission estimation")

    def runtime_metadata(self) -> dict[str, Any]:
        return {"model_observations": []}


class TerminalBackend(NoToolBackend):
    async def complete(self, **_: Any) -> ModelTurn:
        self.calls += 1
        call_id = f"terminal-{self.calls}"
        args = {"command": "echo step"}
        return ModelTurn(
            assistant_message={
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {"name": "terminal", "arguments": json.dumps(args)},
                }],
            },
            tool_calls=[ToolCall(call_id, "terminal", args)],
            total_tokens=self.tokens,
        )


class FinishThenTerminalBackend(NoToolBackend):
    async def complete(self, **_: Any) -> ModelTurn:
        self.calls += 1
        if self.calls > 1:
            return await super().complete()
        finish = ToolCall("finish-1", "finish", {"status": "completed", "summary": "done"})
        terminal = ToolCall("terminal-1", "terminal", {"command": "echo must-not-run"})
        return ModelTurn(
            assistant_message={"role": "assistant", "content": None},
            tool_calls=[finish, terminal],
            total_tokens=self.tokens,
        )


def test_v101_config_uses_step_horizons_and_one_emergency_fuse() -> None:
    config = ScaffoldConfig.from_file(None, {
        "backend": "scripted_test",
        "workspace_mode": "disabled",
        "max_main_steps": 3,
        "max_child_steps": 2,
        "emergency_total_token_cap": 99,
    })
    metadata = config.public_metadata()
    assert metadata["max_main_steps"] == 3
    assert metadata["max_child_steps"] == 2
    assert metadata["emergency_total_token_cap"] == 99
    for removed in (
        "max_main_turns", "max_child_turns", "max_total_tokens",
        "budget_child_shared", "budget_main_pre", "budget_main_post",
        "budget_main_total", "child_context_budget_chars",
    ):
        assert removed not in metadata


def test_finish_is_terminal_even_with_unclosed_benchmark_state() -> None:
    async def exercise() -> tuple[dict[str, Any], ReferenceScaffold]:
        scaffold = _scaffold(NoToolBackend())
        record = ChildRecord(
            child_id="child-queued",
            task="work",
            work_units=["wal_recovery"],
            targets=[],
            expected_output="out",
            priority="high",
            status="completed_hidden",
            completion_id="completion-queued",
        )
        scaffold.manager.children[record.child_id] = record
        scaffold.manager.completion_to_child[record.completion_id] = record.child_id
        await scaffold.manager.handle_delivery({
            "completion_id": record.completion_id,
            "payload": {"id": 1},
        })
        result = await scaffold._execute_main_tool(ToolCall(
            "finish-early", "finish", {"status": "completed", "summary": "stop now"},
        ))
        return result, scaffold

    result, scaffold = asyncio.run(exercise())
    assert result == {"ending": True, "status": "completed"}
    assert scaffold.finished is True
    finish_events = [
        event for event in scaffold.emitter.events if event.get("type") == "finish_invoked"
    ]
    assert len(finish_events) == 1
    assert finish_events[0]["pending_occurrence_count"] == 1
    assert finish_events[0]["closure_complete"] is False


def test_finish_stops_later_tools_in_the_same_response() -> None:
    async def exercise() -> tuple[ReferenceScaffold, FinishThenTerminalBackend]:
        backend = FinishThenTerminalBackend()
        scaffold = _scaffold(backend)
        scaffold.start["initial_wave"] = []
        scaffold.start["allowed_work_units"] = []
        await scaffold.run()
        await scaffold.shutdown()
        return scaffold, backend

    scaffold, backend = asyncio.run(exercise())
    action_kinds = [
        event.get("kind") for event in scaffold.emitter.events
        if event.get("type") == "main_action"
    ]
    assert backend.calls == 1
    assert action_kinds == ["finish"]
    assert scaffold.finish_status == "completed"


def test_no_tool_response_is_one_step_implicit_stop_without_coaching_retry() -> None:
    async def exercise() -> tuple[ReferenceScaffold, NoToolBackend]:
        backend = NoToolBackend()
        scaffold = _scaffold(backend)
        scaffold.start["initial_wave"] = []
        scaffold.start["allowed_work_units"] = []
        await scaffold.run()
        await scaffold.shutdown()
        return scaffold, backend

    scaffold, backend = asyncio.run(exercise())
    assert backend.calls == 1
    assert scaffold.finish_status == "incomplete"
    assert any(
        event.get("type") == "main_implicit_stop"
        for event in scaffold.emitter.events
    )


def test_main_step_horizon_is_the_normal_runtime_limit() -> None:
    async def exercise() -> tuple[ReferenceScaffold, TerminalBackend]:
        backend = TerminalBackend(tokens=3)
        scaffold = _scaffold(backend, max_main_steps=2)
        scaffold.start["initial_wave"] = []
        scaffold.start["allowed_work_units"] = []
        await scaffold.run()
        await scaffold.shutdown()
        return scaffold, backend

    scaffold, backend = asyncio.run(exercise())
    assert backend.calls == 2
    assert scaffold.finish_status == "step_limit_reached"
    assert scaffold.token_usage.snapshot["total"] == 6


def test_emergency_fuse_counts_actual_usage_and_aborts_after_crossing() -> None:
    async def exercise() -> tuple[ReferenceScaffold, TerminalBackend]:
        backend = TerminalBackend(tokens=5)
        scaffold = _scaffold(
            backend,
            max_main_steps=10,
            emergency_total_token_cap=10,
        )
        scaffold.start["initial_wave"] = []
        scaffold.start["allowed_work_units"] = []
        await scaffold.run()
        await scaffold.shutdown()
        return scaffold, backend

    scaffold, backend = asyncio.run(exercise())
    assert backend.calls == 2
    assert scaffold.finish_status == "resource_safety_abort"
    aborts = [
        event for event in scaffold.emitter.events
        if event.get("type") == "resource_safety_abort"
    ]
    assert len(aborts) == 1
    assert aborts[0]["observed_total"] == 10
    snapshots = [
        event for event in scaffold.emitter.events
        if event.get("type") == "token_usage_snapshot"
    ]
    assert snapshots[-1]["total"] == 10


def test_default_emergency_fuse_aborts_at_five_million_actual_tokens() -> None:
    async def exercise() -> tuple[ReferenceScaffold, TerminalBackend]:
        backend = TerminalBackend(tokens=2_500_000)
        scaffold = _scaffold(backend, max_main_steps=10)
        scaffold.start["initial_wave"] = []
        scaffold.start["allowed_work_units"] = []
        await scaffold.run()
        await scaffold.shutdown()
        return scaffold, backend

    scaffold, backend = asyncio.run(exercise())
    assert backend.calls == 2
    assert scaffold.finish_status == "resource_safety_abort"
    assert scaffold.token_usage.snapshot["total"] == 5_000_000
