from __future__ import annotations

import asyncio
import copy
import io
import json
from typing import Any

from async_rbench.evaluation.model_backend import ModelTurn, ToolCall
from async_rbench.evaluation.token_usage import TokenUsageLedger
from async_rbench.evaluation.workspace_runtime import DisabledWorkspaceRuntime
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.profiles.reference_scaffold_api.gateway import ProtocolEmitter
from async_rbench.profiles.reference_scaffold_api.runtime import (
    ChildAgent,
    ChildRecord,
    SubagentManager,
    compress_child_messages,
)
from async_rbench.evaluation.model_backend import serialized_conversation_bytes


def _assistant_tool_block(
    call_id: str, *, reasoning_chars: int, argument_chars: int, result_chars: int,
) -> list[dict[str, Any]]:
    arguments = json.dumps({"command": "x" * argument_chars})
    return [
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "r" * reasoning_chars,
            "tool_calls": [{
                "id": call_id,
                "type": "function",
                "function": {"name": "terminal", "arguments": arguments},
            }],
        },
        {"role": "tool", "tool_call_id": call_id, "content": "o" * result_chars},
    ]


def test_compression_bounds_full_wire_and_preserves_tool_call_pairs() -> None:
    tools = ChildAgent.tools()
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "delegated contract"},
        *_assistant_tool_block(
            "old-call", reasoning_chars=20_000, argument_chars=1_000,
            result_chars=20_000,
        ),
        *_assistant_tool_block(
            "recent-call", reasoning_chars=4_000, argument_chars=100,
            result_chars=4_000,
        ),
    ]
    original_calls = [
        copy.deepcopy(message["tool_calls"])
        for message in messages if message.get("tool_calls")
    ]

    compressed = compress_child_messages(
        messages,
        tools,
        budget_bytes=8_000,
        keep_recent_blocks=1,
        excerpt_chars=200,
    )

    assert serialized_conversation_bytes(compressed, tools) <= 8_000
    assert [
        message["tool_calls"] for message in compressed if message.get("tool_calls")
    ] == original_calls
    call_ids = {
        call["id"]
        for message in compressed
        for call in (message.get("tool_calls") or [])
    }
    result_ids = {
        message["tool_call_id"]
        for message in compressed if message.get("role") == "tool"
    }
    assert result_ids == call_ids
    assert compressed[0] is messages[0]
    assert compressed[1] is messages[1]


class OrderingSpyBackend:
    def __init__(self) -> None:
        self.completed: list[list[dict[str, Any]]] = []
        self.calls = 0

    async def complete(self, *, messages, **_: Any) -> ModelTurn:
        self.completed.append(copy.deepcopy(messages))
        self.calls += 1
        if self.calls == 1:
            call_id = "terminal-1"
            args = {"command": "x" * 1_000}
            return ModelTurn(
                assistant_message={
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": "r" * 20_000,
                    "tool_calls": [{
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": "terminal", "arguments": json.dumps(args),
                        },
                    }],
                },
                tool_calls=[ToolCall(call_id, "terminal", args)],
                total_tokens=10,
            )
        call_id = "submit-2"
        args = {"summary": "done", "result_kind_hint": "done"}
        return ModelTurn(
            assistant_message={
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": "submit_result", "arguments": json.dumps(args),
                    },
                }],
            },
            tool_calls=[ToolCall(call_id, "submit_result", args)],
            total_tokens=10,
        )

    def runtime_metadata(self) -> dict[str, Any]:
        return {"model_observations": []}


def _record() -> ChildRecord:
    return ChildRecord(
        child_id="child-1",
        task="work",
        work_units=["ws"],
        targets=[],
        expected_output="out",
        priority="normal",
        # Task 3 strict public-contract validation requires an explicit kind;
        # this fixture exercises a payload-only submission (no report file).
        public_result_contract={"kind": "payload_only"},
    )


def test_provider_receives_compressed_history_without_admission_estimation() -> None:
    backend = OrderingSpyBackend()
    config = ScaffoldConfig.from_file(None, {
        "backend": "scripted_test",
        "workspace_mode": "disabled",
        "child_context_budget_bytes": 12_000,
    })
    agent = ChildAgent(
        backend,
        DisabledWorkspaceRuntime(),
        config,
        ProtocolEmitter(stdout=io.StringIO()),
        TokenUsageLedger(emergency_cap=5_000_000),
    )

    outcome = asyncio.run(agent.run(_record(), "scripted-test", 1))

    assert outcome.kind == "submitted"
    assert len(backend.completed) == 2
    assert serialized_conversation_bytes(
        backend.completed[1], ChildAgent.tools()
    ) <= config.child_context_budget_bytes
    assert len(backend.completed[1][2].get("reasoning_content") or "") < 20_000


def test_uncompressible_base_context_is_infrastructure_failure_without_provider_call() -> None:
    backend = OrderingSpyBackend()
    config = ScaffoldConfig.from_file(None, {
        "backend": "scripted_test",
        "workspace_mode": "disabled",
        "child_context_budget_bytes": 100,
    })
    emitter = ProtocolEmitter(stdout=io.StringIO())
    manager = SubagentManager(
        start={
            "agent_seed": 1,
            "execution_mode": "linear",
            "allowed_work_units": ["ws"],
            "initial_wave": [{
                "workstream_id": "ws",
                "task": "work",
                "targets": [],
                "expected_output": "out",
                "priority": "normal",
            }],
            "workstream_contracts": {"ws": {}},
            "result_contract_enforced": False,
        },
        child_backend=backend,
        workspace=DisabledWorkspaceRuntime(),
        emitter=emitter,
        config=config,
        token_usage=TokenUsageLedger(emergency_cap=5_000_000),
    )
    manager._launch_queued = lambda: None
    manager.spawn_initial_wave()
    record = next(iter(manager.children.values()))

    asyncio.run(manager._run_child(record))

    assert record.status == "infrastructure_failed"
    assert manager.unresolved_count() == 0
    assert backend.calls == 0
    failure = next(e for e in emitter.events if e["type"] == "infrastructure_failure")
    assert failure["component"] == "child_context_budget"
