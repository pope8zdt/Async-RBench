from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

import pytest

from async_rbench.evaluation.protocol import TraceRecorder
from async_rbench.evaluation.runner import _export_validation_controller_state_private
from async_rbench.evaluation.scheduler import DeliveryController
from async_rbench.evaluation.validation_runner import (
    AdapterPrePresentationCapture,
    assert_branch_equivalence,
    build_validation_checkpoint,
    read_adapter_capture,
    replay_completion_bundle,
    restore_scaffold_from_checkpoint,
)
from async_rbench.evaluation.validation_checkpoint import (
    CHECKPOINT_VERSION,
    ValidationCheckpoint,
    WorkspaceSnapshotReference,
    write_checkpoint,
)
from async_rbench.evaluation.workspace_runtime import (
    DisabledWorkspaceRuntime,
    ValidationWorkspaceSnapshot,
)
from async_rbench.profiles.reference_scaffold_api.adapter import build_parser
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.profiles.reference_scaffold_api.gateway import DeliveryReader, ProtocolEmitter
from async_rbench.profiles.reference_scaffold_api.runtime import ChildRecord, ReferenceScaffold


class NoCallBackend:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, **_: object):
        self.calls += 1
        raise AssertionError("model must not be called after checkpoint capture")


class PreparedWorkspace(DisabledWorkspaceRuntime):
    async def export_validation_controller_state(
        self, *, target_completion_id: str,
    ) -> dict[str, object]:
        return {
            "controller_state": {"delivered": [target_completion_id]},
            "prefix_trace_sha256": "d" * 64,
            "target_delivery": {
                "type": "result_delivered",
                "completion_id": target_completion_id,
                "benchmark_event_id": "event-target",
                "delivery_occurrence_id": "gateway-occ-2",
                "payload": {"revision": "v2"},
            },
        }

    async def prepare_result_presentation(
        self, delivery_occurrence_id: str, *, turn_id: str,
    ) -> dict[str, object]:
        return {
            "prepared": True,
            "delivery_occurrence_id": delivery_occurrence_id,
            "turn_id": turn_id,
            "snapshot_digest": "b" * 64,
        }

    async def capture_validation_snapshot(
        self, snapshot_id: str, *, tree_sha256: str,
    ) -> ValidationWorkspaceSnapshot:
        return ValidationWorkspaceSnapshot(
            snapshot_id=snapshot_id,
            image_name="main:snapshot",
            image_id="sha256:" + "a" * 64,
            tree_sha256=tree_sha256,
        )

    async def capture_validation_child_snapshot(
        self, snapshot_id: str, child_id: str, *, tree_sha256: str,
    ) -> ValidationWorkspaceSnapshot:
        return ValidationWorkspaceSnapshot(
            snapshot_id=f"{snapshot_id}:child:{child_id}",
            image_name=f"{child_id}:snapshot",
            image_id="sha256:" + "c" * 64,
            tree_sha256=tree_sha256,
        )


def _scaffold(capture: AdapterPrePresentationCapture) -> tuple[ReferenceScaffold, NoCallBackend]:
    config = ScaffoldConfig.from_file(
        None,
        {"backend": "scripted_test", "workspace_mode": "disabled"},
    )
    backend = NoCallBackend()
    scaffold = ReferenceScaffold(
        start={
            "instruction": "task",
            "execution_mode": "async",
            "agent_seed": 2026,
            "allowed_artifacts": ["final"],
            "allowed_work_units": ["work-a"],
            "initial_wave": [],
            "workstream_contracts": {},
        },
        config=config,
        backend=backend,
        workspace=PreparedWorkspace(),
        emitter=ProtocolEmitter(stdout=io.StringIO()),
        delivery_reader=DeliveryReader(stdin=io.StringIO()),
        validation_capture_hook=capture,
    )
    scaffold.messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": "pre-event plan"},
    ]
    scaffold.manager.children["child-1"] = ChildRecord(
        child_id="child-1",
        task="work",
        work_units=["work-a"],
        targets=[],
        expected_output="result",
        priority="normal",
        status="completed",
        completion_id="completion-target",
    )
    scaffold.manager.completion_to_child["completion-target"] = "child-1"
    return scaffold, backend


def test_capture_stops_before_target_delivery_enters_model_context(tmp_path: Path) -> None:
    capture_path = tmp_path / "adapter-capture.json"
    capture = AdapterPrePresentationCapture(
        capture_path,
        target_workstream_id="work-a",
        checkpoint_id="ckpt-0123456789abcdef",
    )
    scaffold, backend = _scaffold(capture)
    scaffold.manager.children["child-2"] = ChildRecord(
        child_id="child-2",
        task="other work",
        work_units=["work-b"],
        targets=[],
        expected_output="other result",
        priority="normal",
        status="running",
    )

    async def exercise() -> None:
        async def finish_inflight_child() -> None:
            await asyncio.sleep(0.02)
            record = scaffold.manager.children["child-2"]
            record.status = "completed"
            record.completion_id = "completion-later"
            record.payload = {"summary": "captured later"}
            scaffold.manager.completion_to_child["completion-later"] = "child-2"
            scaffold.emitter.emit(
                "child_completed",
                child_id="child-2",
                completion_id="completion-later",
                payload=record.payload,
            )

        scaffold.manager.children["child-2"].asyncio_task = asyncio.create_task(
            finish_inflight_child()
        )
        await scaffold.manager.handle_delivery(
            {
                "type": "result_delivered",
                "child_id": "child-1",
                "completion_id": "completion-target",
                "payload": {"revision": "v2"},
                "payload_sha256": "a" * 64,
            }
        )
        await scaffold.run()

    asyncio.run(exercise())

    captured = read_adapter_capture(capture_path)
    assert captured["target_occurrence"]["completion_id"] == "completion-target"
    assert captured["target_occurrence"]["payload"]["workstream_id"] == "work-a"
    assert captured["scaffold_state"]["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": "pre-event plan"},
    ]
    assert "ASYNC_RBENCH_DELIVERY" not in json.dumps(captured)
    assert captured["main_workspace"] == {
        "snapshot_id": "ckpt-0123456789abcdef",
        "image_name": "main:snapshot",
        "image_id": "sha256:" + "a" * 64,
        "tree_sha256": "b" * 64,
    }
    assert captured["kernel_capture"]["prefix_trace_sha256"] == "d" * 64
    assert captured["kernel_capture"]["target_delivery"]["benchmark_event_id"] == (
        "event-target"
    )
    assert set(captured["child_workspaces"]) == {"child-2"}
    assert captured["child_workspaces"]["child-2"]["image_id"] == (
        "sha256:" + "c" * 64
    )
    assert captured["completion_bundle"] == [
        {
            "type": "child_completed",
            "child_id": "child-2",
            "completion_id": "completion-later",
            "payload": {"summary": "captured later"},
        }
    ]
    assert scaffold.manager.presentation_queue.pending_occurrence_ids == ["occ-1"]
    assert scaffold.finish_status == "validation_checkpoint_captured"
    assert backend.calls == 0
    event = next(
        item for item in scaffold.emitter.events
        if item.get("type") == "fork_bundle_captured"
    )
    assert event["bundle_id"] == captured["adapter_capture_sha256"]
    assert event["main_transcript_digest"] == captured["main_transcript_digest"]


def test_branch_equivalence_fails_closed_on_any_invariant_mismatch() -> None:
    common = {
        "checkpoint_digest": "a" * 64,
        "main_workspace_tree_digest": "b" * 64,
        "main_transcript_digest": "c" * 64,
        "controller_state_digest": "d" * 64,
        "completion_bundle_digest": "e" * 64,
        "remaining_budget_digest": "f" * 64,
        "target_delivery_digest": "1" * 64,
    }
    branches = {
        "oracle_replan": dict(common),
        "native_agent": dict(common),
        "frozen_plan": dict(common),
    }
    assert_branch_equivalence(branches)
    branches["frozen_plan"]["target_delivery_digest"] = "2" * 64

    with pytest.raises(ValueError, match="target_delivery_digest"):
        assert_branch_equivalence(branches)


def test_adapter_parser_accepts_private_validation_modes(tmp_path: Path) -> None:
    parser = build_parser()
    capture = parser.parse_args(
        [
            "--validation-capture",
            str(tmp_path / "capture.json"),
            "--validation-target-workstream-id",
            "work-a",
            "--validation-checkpoint-id",
            "ckpt-0123456789abcdef",
        ]
    )
    assert capture.validation_capture == tmp_path / "capture.json"
    assert capture.validation_target_workstream_id == "work-a"
    assert capture.validation_checkpoint_id == "ckpt-0123456789abcdef"

    resume = parser.parse_args(
        [
            "--validation-resume",
            str(tmp_path / "capture.json"),
            "--validation-condition",
            "native_agent",
        ]
    )
    assert resume.validation_condition == "native_agent"


def test_checkpoint_builder_requires_replay_evidence_for_every_inflight_child() -> None:
    adapter_capture = {
        "schema_version": "drs-validation-adapter-capture-1.0",
        "target_workstream_id": "work-a",
        "target_occurrence": {
            "occurrence_id": "occ-2",
            "completion_id": "completion-target",
            "payload": {
                "type": "result_delivered",
                "child_id": "child-1",
                "completion_id": "completion-target",
                "workstream_id": "work-a",
                "payload": {"revision": "v2"},
                "payload_sha256": "9" * 64,
            },
            "receive_seq": 2,
            "replay_of_occurrence_id": None,
            "benchmark_event_id": None,
            "scored": True,
        },
        "scaffold_state": {
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "assistant", "content": "pre-event plan"},
            ],
            "manager": {
                "children": [
                    {"child_id": "child-running", "status": "running"},
                ]
            },
        },
    }
    main_snapshot = ValidationWorkspaceSnapshot(
        snapshot_id="checkpoint-1",
        image_name="main:snapshot",
        image_id="sha256:" + "a" * 64,
        tree_sha256="b" * 64,
    )
    child_snapshot = ValidationWorkspaceSnapshot(
        snapshot_id="checkpoint-1:child:child-running",
        image_name="child:snapshot",
        image_id="sha256:" + "c" * 64,
        tree_sha256="d" * 64,
    )
    completion_bundle = [
        {
            "type": "child_completed",
            "child_id": "child-running",
            "completion_id": "completion-later",
            "payload": {"summary": "later result"},
        }
    ]
    common = {
        "checkpoint_id": "ckpt-0123456789abcdef",
        "instance_key": "case-a::seed-1",
        "model_id": "model-a",
        "repeat": 2026,
        "target_event_id": "event-target",
        "adapter_capture": adapter_capture,
        "controller_state": {"delivered": ["completion-old"]},
        "prefix_trace_sha256": "e" * 64,
        "main_workspace": main_snapshot,
        "target_delivery": {
            "type": "result_delivered",
            "benchmark_event_id": "event-target",
            "delivery_occurrence_id": "gateway-occ-2",
            "completion_id": "completion-target",
            "payload": {"revision": "v2"},
        },
        "completion_bundle": completion_bundle,
        "remaining_budget": {"main_steps": 90, "emergency_tokens": 4000000},
        "source_digests": {
            "case_bundle_sha256": "f" * 64,
            "profile_sha256": "1" * 64,
            "event_contract_sha256": "2" * 64,
        },
    }

    with pytest.raises(ValueError, match="child-running.*workspace snapshot"):
        build_validation_checkpoint(child_workspaces={}, **common)

    checkpoint = build_validation_checkpoint(
        child_workspaces={"child-running": child_snapshot},
        **common,
    )
    assert checkpoint.main_workspace.image_id == main_snapshot.image_id
    assert checkpoint.child_workspaces[0].child_id == "child-running"
    assert checkpoint.completion_bundle[0]["completion_id"] == "completion-later"


def test_completion_bundle_rehydrates_inflight_child_without_live_task() -> None:
    capture = AdapterPrePresentationCapture(
        Path("unused.json"), target_workstream_id="work-a"
    )
    scaffold, _ = _scaffold(capture)
    record = scaffold.manager.children["child-1"]
    record.status = "running"
    record.completion_id = None
    scaffold.manager.completion_to_child.clear()

    replay_completion_bundle(
        scaffold,
        [
            {
                "type": "child_completed",
                "child_id": "child-1",
                "completion_id": "completion-later",
                "payload": {"summary": "captured result"},
                "tokens": 17,
            }
        ],
    )

    assert record.status == "completed"
    assert record.completion_id == "completion-later"
    assert record.payload == {"summary": "captured result"}
    assert record.tokens == 17
    assert record.asyncio_task is None
    assert scaffold.manager.completion_to_child == {
        "completion-later": "child-1"
    }

    with pytest.raises(ValueError, match="unknown child"):
        replay_completion_bundle(
            scaffold,
            [{"type": "child_cancelled", "child_id": "missing", "reason": "x"}],
        )


def test_resume_restores_scaffold_and_replays_captured_completion(
    tmp_path: Path,
) -> None:
    capture = AdapterPrePresentationCapture(
        tmp_path / "unused.json", target_workstream_id="work-a"
    )
    source, _ = _scaffold(capture)
    source.messages = [
        {"role": "system", "content": "system"},
        {"role": "assistant", "content": "pre-event plan"},
    ]
    source.manager.children["child-1"].status = "running"
    source.manager.children["child-1"].completion_id = None
    source.manager.completion_to_child.clear()
    checkpoint = ValidationCheckpoint(
        schema_version=CHECKPOINT_VERSION,
        checkpoint_id="ckpt-0123456789abcdef",
        instance_key="case-a::seed-1",
        model_id="model-a",
        repeat=2026,
        target_event_id="event-target",
        main_messages=tuple(source.messages),
        scaffold_state=source.export_validation_state(),
        controller_state={"delivered": ["completion-old"]},
        prefix_trace_sha256="1" * 64,
        main_workspace=WorkspaceSnapshotReference(
            image_id="sha256:" + "2" * 64,
            tree_sha256="3" * 64,
        ),
        child_workspaces=(
            WorkspaceSnapshotReference(
                image_id="sha256:" + "4" * 64,
                tree_sha256="5" * 64,
                child_id="child-1",
            ),
        ),
        target_delivery={
            "type": "result_delivered",
            "benchmark_event_id": "event-target",
            "delivery_occurrence_id": "gateway-occ-2",
            "completion_id": "completion-target",
            "payload": {"revision": "v2"},
        },
        completion_bundle=(
            {
                "type": "child_completed",
                "child_id": "child-1",
                "completion_id": "completion-later",
                "payload": {"summary": "captured result"},
                "tokens": 17,
            },
        ),
        remaining_budget={"main_steps": 90, "emergency_tokens": 4000000},
        source_digests={
            "case_bundle_sha256": "6" * 64,
            "profile_sha256": "7" * 64,
            "event_contract_sha256": "8" * 64,
        },
    )
    path = tmp_path / "checkpoint.json"
    write_checkpoint(path, checkpoint)
    restored, _ = _scaffold(capture)

    loaded = restore_scaffold_from_checkpoint(restored, path)

    assert loaded == checkpoint
    assert restored.messages == source.messages
    assert restored.manager.children["child-1"].status == "completed"
    assert restored.manager.children["child-1"].completion_id == "completion-later"


def test_kernel_capture_joins_private_event_identity_to_public_delivery() -> None:
    recorder = TraceRecorder("episode-a")
    recorder.record(
        {
            "type": "result_delivery_evaluator_fact",
            "completion_id": "completion-target",
            "benchmark_event_id": "event-target",
            "delivery_occurrence_id": "gateway-occ-2",
        },
        "kernel",
    )
    recorder.record(
        {
            "type": "result_delivered",
            "child_id": "child-1",
            "completion_id": "completion-target",
            "workstream_id": "work-a",
            "payload": {"revision": "v2"},
            "payload_sha256": "9" * 64,
        },
        "gateway",
    )
    controller = DeliveryController(
        "async", {"scenarios": {"async": {"events": []}}}
    )

    captured = _export_validation_controller_state_private(
        controller,
        recorder,
        target_completion_id="completion-target",
    )

    assert captured["target_delivery"]["benchmark_event_id"] == "event-target"
    assert captured["target_delivery"]["delivery_occurrence_id"] == "gateway-occ-2"
    assert captured["target_delivery"]["payload"] == {"revision": "v2"}
    assert len(captured["prefix_trace_sha256"]) == 64
    assert captured["controller_state"]["execution_mode"] == "async"
