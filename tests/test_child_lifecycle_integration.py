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
from async_rbench.profiles.reference_scaffold_api.runtime import ReferenceScaffold
from async_rbench.spec import load_case


ROOT = Path(__file__).resolve().parents[1]


class NoToolBackend:
    async def complete(self, **_: Any) -> ModelTurn:
        return ModelTurn(
            assistant_message={"role": "assistant", "content": "not submitted"},
            tool_calls=[],
            total_tokens=7,
        )

    def runtime_metadata(self) -> dict[str, Any]:
        return {"model_observations": []}


class NonSubmitToolBackend:
    def __init__(self) -> None:
        self.turn = 0

    async def complete(self, **_: Any) -> ModelTurn:
        self.turn += 1
        call_id = f"terminal-{self.turn}"
        arguments = {"command": "echo still-working"}
        return ModelTurn(
            assistant_message={
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": "terminal",
                        "arguments": json.dumps(arguments),
                    },
                }],
            },
            tool_calls=[ToolCall(call_id, "terminal", arguments)],
            total_tokens=11,
        )

    def runtime_metadata(self) -> dict[str, Any]:
        return {"model_observations": []}


def _start(mode: str = "linear") -> dict[str, Any]:
    case_path = ROOT / "cases" / "data-recovery-service" / "public_case.yaml"
    case = load_case(case_path).raw
    task = yaml.safe_load(
        (case_path.parent / "task" / "task.yaml").read_text(encoding="utf-8")
    )
    config = EpisodeConfig(
        episode_id="child-lifecycle",
        case_id="data-recovery-service",
        execution_mode=mode,
        guidance="incentive",
        agent_seed=1,
        adapter_command=[sys.executable],
        output_dir=ROOT / "artifacts" / "test-unused",
        use_container=False,
    )
    return _make_start(config, case, task, None, "0123456789ab")


def _scaffold(backend: Any, *, max_child_steps: int = 40, **overrides: Any) -> ReferenceScaffold:
    config = ScaffoldConfig.from_file(None, {
        "backend": "scripted_test",
        "workspace_mode": "disabled",
        "max_child_steps": max_child_steps,
        **overrides,
    })
    start = _start()
    only = start["initial_wave"][0]
    workstream_id = only["workstream_id"]
    start["initial_wave"] = [only]
    start["allowed_work_units"] = [workstream_id]
    start["workstream_contracts"] = {
        workstream_id: start["workstream_contracts"][workstream_id]
    }
    return ReferenceScaffold(
        start=start,
        config=config,
        backend=backend,
        workspace=DisabledWorkspaceRuntime(),
        emitter=ProtocolEmitter(stdout=io.StringIO()),
        delivery_reader=DeliveryReader(stdin=io.StringIO()),
    )


async def _run_one(scaffold: ReferenceScaffold):
    manager = scaffold.manager
    manager._launch_queued = lambda: None
    manager.spawn_initial_wave()
    record = next(iter(manager.children.values()))
    await manager._run_child(record)
    return manager, record, scaffold.emitter.events


def _assert_non_submission_terminal(manager, record, events, expected_event: str) -> None:
    assert manager.unresolved_count() == 0
    assert manager.linear_bundle_ready() is True
    waited = asyncio.run(manager.wait([record.child_id], 0, "all"))
    assert waited["ready"] is True
    types = [event["type"] for event in events]
    assert expected_event in types
    assert "child_completed" not in types
    assert "result_contract_validated" not in types
    assert "result_rejected" not in types


def test_emergency_safety_abort_is_terminal_without_submission() -> None:
    async def exercise():
        scaffold = _scaffold(NoToolBackend(), emergency_total_token_cap=1)
        return await _run_one(scaffold)

    manager, record, events = asyncio.run(exercise())
    assert record.status == "resource_safety_abort"
    assert record.decision == "resource_safety_abort"
    _assert_non_submission_terminal(
        manager, record, events, "child_resource_safety_abort"
    )


def test_one_unsealed_assistant_response_ends_as_no_submission() -> None:
    manager, record, events = asyncio.run(_run_one(_scaffold(NoToolBackend())))
    assert record.status == "no_submission"
    assert record.decision == "no_submission"
    assert record.payload is None
    _assert_non_submission_terminal(manager, record, events, "child_no_submission")


def test_non_submit_tools_reaching_step_limit_end_as_step_limit_reached() -> None:
    manager, record, events = asyncio.run(
        _run_one(_scaffold(NonSubmitToolBackend(), max_child_steps=2))
    )
    assert record.status == "step_limit_reached"
    assert record.decision == "step_limit_reached"
    assert record.payload is None
    _assert_non_submission_terminal(
        manager, record, events, "child_step_limit_reached"
    )
