from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from async_rbench.evaluation.runner import (
    CAPABILITY_METHODS, EpisodeConfig, _dispatch_capability, run_episode,
)
from async_rbench.evaluation.protocol import TraceRecorder
from async_rbench.evaluation.event_store import EventStore
from async_rbench.evaluation.workspace_runtime import CommandResult
from async_rbench.protocol_sdk.capability import CapabilityRuntimeProxy


ROOT = Path(__file__).resolve().parents[1]


def test_proxy_encodes_request_and_decodes_command_result():
    captured: list[dict] = []
    proxy = CapabilityRuntimeProxy(captured.append)

    async def exercise():
        task = asyncio.create_task(proxy.main_terminal("echo hi", 10))
        await asyncio.sleep(0)  # let _request run up to its first await
        assert len(captured) == 1
        request = captured[0]
        assert request["type"] == "capability_request"
        assert request["capability"] == "main_terminal"
        assert request["args"] == {"command": "echo hi", "timeout": 10}
        proxy.handle_response({
            "type": "capability_response", "request_id": request["request_id"],
            "ok": True, "result": {"exit_code": 0, "output": "hi"},
        })
        return await task

    result = asyncio.run(exercise())
    assert isinstance(result, CommandResult)
    assert result.exit_code == 0
    assert result.output == "hi"


def test_proxy_passes_scalar_arguments_and_decodes_scalar_result():
    captured: list[dict] = []
    proxy = CapabilityRuntimeProxy(captured.append)

    async def exercise():
        task = asyncio.create_task(proxy.create_child("c1"))
        await asyncio.sleep(0)
        request = captured[0]
        assert request["capability"] == "create_child"
        assert request["args"] == {"child_id": "c1"}
        proxy.handle_response({
            "type": "capability_response", "request_id": request["request_id"],
            "ok": True, "result": "ws-c1",
        })
        return await task

    assert asyncio.run(exercise()) == "ws-c1"


def test_proxy_decodes_private_artifact_observation_summary():
    captured: list[dict] = []
    proxy = CapabilityRuntimeProxy(captured.append)

    async def exercise():
        task = asyncio.create_task(proxy.observe_artifact("artifact-1"))
        await asyncio.sleep(0)
        request = captured[0]
        assert request["capability"] == "observe_artifact"
        proxy.handle_response({
            "type": "capability_response", "request_id": request["request_id"],
            "ok": True, "result": {"observed_path": "/app/a", "observed_digest": "a" * 64},
        })
        return await task

    assert asyncio.run(exercise()) == {"observed_path": "/app/a", "observed_digest": "a" * 64}


def test_proxy_raises_on_error_response():
    captured: list[dict] = []
    proxy = CapabilityRuntimeProxy(captured.append)

    async def exercise():
        task = asyncio.create_task(proxy.cleanup())
        await asyncio.sleep(0)
        request = captured[0]
        proxy.handle_response({
            "type": "capability_response", "request_id": request["request_id"],
            "ok": False, "error": "docker daemon not running",
        })
        return await task

    with pytest.raises(RuntimeError, match="docker daemon not running"):
        asyncio.run(exercise())


def test_capability_messages_do_not_reach_the_event_source(tmp_path: Path):
    # A no-container run of the conformance mock exercises the stdio capability
    # RPC (prepare_event_assets round-trips through the kernel). The transport
    # messages must never appear in the scored event source.
    config = EpisodeConfig(
            episode_id="rpc-smoke", case_id="secure-release", execution_mode="linear",
        guidance="incentive", agent_seed=1,
        adapter_command=[sys.executable, str(ROOT / "adapters" / "conformance_mock.py")],
        output_dir=tmp_path, use_container=False, timeout_sec=120,
    )
    asyncio.run(run_episode(ROOT, config))

    event_source = (tmp_path / "event_source.jsonl").read_text(encoding="utf-8")
    events = [json.loads(line) for line in event_source.splitlines() if line.strip()]
    assert events, "episode should produce a non-empty event source"
    types = {event.get("type") for event in events}
    assert "capability_request" not in types
    assert "capability_response" not in types


def test_kernel_capability_allowlist_rejects_unknown_method():
    assert "__class__" not in CAPABILITY_METHODS
    assert "main_terminal" in CAPABILITY_METHODS

    class FakeProcess:
        def __init__(self):
            self.messages = []

    process = FakeProcess()
    process.stdin = None

    async def exercise():
        # _dispatch_capability emits through _send; use a minimal process
        # whose stdin captures the encoded response.
        class Stdin:
            def write(self, data):
                process.messages.append(json.loads(data.decode()))
            async def drain(self):
                return None
        process.stdin = Stdin()
        await _dispatch_capability(
            object(),
            {"type": "capability_request", "request_id": "r1", "capability": "__class__", "args": {}},
            process,
            asyncio.Lock(),
        )

    asyncio.run(exercise())
    assert process.messages[0]["ok"] is False
    assert "unsupported capability" in process.messages[0]["error"]


def test_child_terminal_capability_records_exact_private_command_and_result():
    class Workspace:
        async def child_terminal(self, child_id, command, timeout):
            assert (child_id, command, timeout) == (
                "child-7", "python -c \"print('exact')\"", 19,
            )
            return CommandResult(3, "exact output\nwith stderr")

    class Process:
        def __init__(self):
            self.messages = []

    process = Process()

    class Stdin:
        def write(self, data):
            process.messages.append(json.loads(data.decode()))

        async def drain(self):
            return None

    process.stdin = Stdin()
    recorder = TraceRecorder("terminal-audit")
    asyncio.run(_dispatch_capability(
        Workspace(),
        {
            "type": "capability_request", "request_id": "terminal-r1",
            "capability": "child_terminal",
            "args": {
                "child_id": "child-7",
                "command": "python -c \"print('exact')\"",
                "timeout": 19,
            },
        },
        process,
        asyncio.Lock(),
        recorder,
    ))

    assert process.messages[0]["ok"] is True
    assert process.messages[0]["result"] == {
        "exit_code": 3, "output": "exact output\nwith stderr",
    }
    started, finished = recorder.events
    assert started["type"] == "child_terminal_started"
    assert started["command"] == "python -c \"print('exact')\""
    assert started["timeout_sec"] == 19
    assert finished["type"] == "child_terminal_finished"
    assert finished["exit_code"] == 3
    assert finished["output"] == "exact output\nwith stderr"
    assert finished["output_truncated"] is False
    source = EventStore.from_records(recorder.events, "terminal-audit")
    assert {event["visibility"] for event in source.events} == {"kernel_private"}


def test_proxy_encodes_prepare_result_presentation_and_observe_main_state():
    captured: list[dict] = []
    proxy = CapabilityRuntimeProxy(captured.append)

    async def exercise():
        prep_task = asyncio.create_task(
            proxy.prepare_result_presentation("occ-1", turn_id="t1")
        )
        await asyncio.sleep(0)
        assert captured[0]["capability"] == "prepare_result_presentation"
        assert captured[0]["args"] == {
            "delivery_occurrence_id": "occ-1", "turn_id": "t1",
        }
        proxy.handle_response({
            "type": "capability_response", "request_id": captured[0]["request_id"],
            "ok": True, "result": {"prepared": True, "snapshot_digest": "d" * 64},
        })
        prepared = await prep_task

        observe_task = asyncio.create_task(
            proxy.observe_main_state("tool_completed:terminal", action_id="a1", turn_id="t1")
        )
        await asyncio.sleep(0)
        assert captured[1]["capability"] == "observe_main_state"
        assert captured[1]["args"] == {
            "reason": "tool_completed:terminal", "action_id": "a1", "turn_id": "t1",
        }
        proxy.handle_response({
            "type": "capability_response", "request_id": captured[1]["request_id"],
            "ok": True, "result": {"provisional_observed": True},
        })
        observed = await observe_task
        return prepared, observed

    prepared, observed = asyncio.run(exercise())
    assert prepared == {"prepared": True, "snapshot_digest": "d" * 64}
    assert observed == {"provisional_observed": True}


def test_dispatch_prepare_result_presentation_records_kernel_private_boundary():
    class Workspace:
        async def main_terminal(self, command, timeout):
            raise AssertionError("no observation points expected for an empty case")

    class Process:
        def __init__(self):
            self.messages = []

    process = Process()

    class Stdin:
        def write(self, data):
            process.messages.append(json.loads(data.decode()))

        async def drain(self):
            return None

    process.stdin = Stdin()
    recorder = TraceRecorder("presentation-audit")
    asyncio.run(_dispatch_capability(
        Workspace(),
        {
            "type": "capability_request", "request_id": "prep-r1",
            "capability": "prepare_result_presentation",
            "args": {"delivery_occurrence_id": "occ-1", "turn_id": "t1"},
        },
        process,
        asyncio.Lock(),
        recorder,
        case_spec={},
    ))

    assert process.messages[0]["ok"] is True
    assert process.messages[0]["result"]["prepared"] is True
    assert process.messages[0]["result"]["snapshot_digest"]
    prepared, = recorder.events
    assert prepared["type"] == "presentation_prepared"
    assert prepared["delivery_occurrence_id"] == "occ-1"
    assert prepared["turn_id"] == "t1"
    source = EventStore.from_records(recorder.events, "presentation-audit")
    assert {event["visibility"] for event in source.events} == {"kernel_private"}


def test_dispatch_prepare_result_presentation_fails_on_incomplete_snapshot():
    class Workspace:
        async def main_terminal(self, command, timeout):
            return CommandResult(1, "")

    class Process:
        def __init__(self):
            self.messages = []

    process = Process()

    class Stdin:
        def write(self, data):
            process.messages.append(json.loads(data.decode()))

        async def drain(self):
            return None

    process.stdin = Stdin()
    asyncio.run(_dispatch_capability(
        Workspace(),
        {
            "type": "capability_request", "request_id": "prep-fail",
            "capability": "prepare_result_presentation",
            "args": {"delivery_occurrence_id": "occ-2", "turn_id": "t2"},
        },
        process,
        asyncio.Lock(),
        TraceRecorder("presentation-fail-audit"),
        case_spec={"observation_points": [
            {"point_id": "p1", "kind": "file", "path": "/app/nonexistent"},
        ]},
    ))

    assert process.messages[0]["ok"] is True
    assert process.messages[0]["result"]["prepared"] is False
    assert process.messages[0]["result"]["error"] == "incomplete_snapshot"


def test_dispatch_observe_main_state_without_point_records_false_provisional_fact():
    """§4.1(5): a case with no decision-bearing observation point cannot establish
    provisional, but the kernel-private fact is still recorded (with
    ``provisional_established`` false) so the event survives replay."""
    class Workspace:
        async def main_terminal(self, command, timeout):
            raise AssertionError("no observation points expected for an empty case")

    class Process:
        def __init__(self):
            self.messages = []

    process = Process()

    class Stdin:
        def write(self, data):
            process.messages.append(json.loads(data.decode()))

        async def drain(self):
            return None

    process.stdin = Stdin()
    recorder = TraceRecorder("observe-audit")
    asyncio.run(_dispatch_capability(
        Workspace(),
        {
            "type": "capability_request", "request_id": "obs-r1",
            "capability": "observe_main_state",
            "args": {
                "reason": "tool_completed:terminal",
                "action_id": "a1", "turn_id": "t1",
            },
        },
        process,
        asyncio.Lock(),
        recorder,
        case_spec={},
    ))

    assert process.messages[0]["ok"] is True
    assert process.messages[0]["result"]["provisional_observed"] is False
    fact, = recorder.events
    assert fact["type"] == "provisional_observed"
    assert fact["provisional_established"] is False
    assert fact["reason"] == "no_decision_bearing_points"
    assert fact["action_id"] == "a1"
    assert fact["turn_id"] == "t1"
    assert fact["provisional_digest"] is None
    source = EventStore.from_records(recorder.events, "observe-audit")
    assert {event["visibility"] for event in source.events} == {"kernel_private"}


def test_dispatch_observe_main_state_with_point_establishes_provisional_fact():
    """§4.1(5) happy path: a declared observation point + an observed snapshot
    establishes provisional through the kernel capability dispatch."""
    class Workspace:
        async def main_terminal(self, command, timeout):
            return CommandResult(0, "answer=42\n")

    class Process:
        def __init__(self):
            self.messages = []

    process = Process()

    class Stdin:
        def write(self, data):
            process.messages.append(json.loads(data.decode()))

        async def drain(self):
            return None

    process.stdin = Stdin()
    recorder = TraceRecorder("observe-audit")
    asyncio.run(_dispatch_capability(
        Workspace(),
        {
            "type": "capability_request", "request_id": "obs-r2",
            "capability": "observe_main_state",
            "args": {
                "reason": "tool_completed:terminal",
                "action_id": "a2", "turn_id": "t2",
            },
        },
        process,
        asyncio.Lock(),
        recorder,
        case_spec={"observation_points": [
            {"point_id": "state", "kind": "file", "path": "/app/state"},
        ]},
    ))

    assert process.messages[0]["ok"] is True
    assert process.messages[0]["result"]["provisional_observed"] is True
    fact, = recorder.events
    assert fact["type"] == "provisional_observed"
    assert fact["provisional_established"] is True
    assert fact["provisional_digest"]
    assert fact["observed_points"] == {"state": "answer=42"}
    source = EventStore.from_records(recorder.events, "observe-audit")
    assert {event["visibility"] for event in source.events} == {"kernel_private"}


def test_dispatch_require_listed_for_both_new_capabilities():
    assert "prepare_result_presentation" in CAPABILITY_METHODS
    assert "observe_main_state" in CAPABILITY_METHODS
