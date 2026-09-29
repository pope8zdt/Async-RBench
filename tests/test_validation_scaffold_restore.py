from __future__ import annotations

import asyncio
import io
import json

import pytest

from async_rbench.evaluation.presentation import DeliveryOccurrence
from async_rbench.evaluation.workspace_runtime import DisabledWorkspaceRuntime
from async_rbench.profiles.conformance_mock.scripted_backend import ScriptedTestBackend
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.profiles.reference_scaffold_api.gateway import DeliveryReader, ProtocolEmitter
from async_rbench.profiles.reference_scaffold_api.runtime import ChildRecord, ReferenceScaffold


START = {
    "instruction": "complete the task",
    "execution_mode": "async",
    "agent_seed": 2026,
    "allowed_artifacts": ["final"],
    "allowed_work_units": ["work-a"],
    "initial_wave": [],
    "workstream_contracts": {},
}


def _scaffold() -> ReferenceScaffold:
    config = ScaffoldConfig.from_file(
        None,
        {"backend": "scripted_test", "workspace_mode": "disabled"},
    )
    return ReferenceScaffold(
        start=START,
        config=config,
        backend=ScriptedTestBackend(),
        workspace=DisabledWorkspaceRuntime(),
        emitter=ProtocolEmitter(stdout=io.StringIO()),
        delivery_reader=DeliveryReader(stdin=io.StringIO()),
    )


def test_scaffold_round_trip_preserves_participant_state_not_runtime_objects() -> None:
    async def exercise() -> None:
        source = _scaffold()
        source.messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "task"},
            {"role": "assistant", "content": "plan"},
        ]
        source.next_turn_index = 7
        source._action_counter = 4
        source._accepted_state_revision = 2
        source._final_commit_revision = 2
        source._verification_revision = 1
        source._verification_passed = False
        source.token_usage.total = 120
        source.token_usage.main = 80
        source.token_usage.child = 40
        source.token_usage.by_actor.update({"main": 80, "child:child-1": 40})

        pending_task = asyncio.create_task(asyncio.sleep(60))
        source.manager.children["child-1"] = ChildRecord(
            child_id="child-1",
            task="work",
            work_units=["work-a"],
            targets=["/app/a"],
            expected_output="result",
            priority="normal",
            status="running",
            asyncio_task=pending_task,
            attempt_number=2,
            prior_attempt_rejection={"reason_codes": ["missing_field"]},
        )
        source.manager.completion_to_child["completion-old"] = "child-1"
        source.manager.attempt_counts["work-a"] = 2
        source.manager.workstream_rejections["work-a"] = {
            "reason_codes": ["missing_field"]
        }
        source.manager.workstream_evidence_digests["work-a"].append("a" * 64)
        source.manager.recovery_spawn_counts["work-a"] = 1
        source.manager.duplicate_evidence_retries["work-a"] = 1
        source.manager._started_child_ids.add("child-1")
        source.manager._counter = 3
        source.manager._completion_counter = 2
        source.manager._occurrence_counter = 2

        first = DeliveryOccurrence(
            occurrence_id="occ-1",
            completion_id="completion-old",
            payload={"completion_id": "completion-old"},
            receive_seq=1,
        )
        second = DeliveryOccurrence(
            occurrence_id="occ-2",
            completion_id="completion-new",
            payload={"completion_id": "completion-new"},
            receive_seq=2,
            benchmark_event_id="target-event",
            scored=True,
        )
        source.manager.presentation_queue.enqueue(first)
        source.manager.presentation_queue.enqueue(second)
        source.manager.presentation_queue.mark_presented(
            "occ-1", turn_id="t6", window_id="w6"
        )

        state = source.export_validation_state()
        encoded = json.dumps(state, sort_keys=True)
        assert "asyncio_task" not in encoded
        assert "_delivery_event" not in encoded
        assert "provider_client" not in encoded

        restored = _scaffold()
        old_delivery_event = restored.manager._delivery_event
        restored.restore_validation_state(state)

        assert restored.messages == source.messages
        assert restored.next_turn_index == 7
        assert restored._action_counter == 4
        assert restored._accepted_state_revision == 2
        assert restored._final_commit_revision == 2
        assert restored._verification_revision == 1
        assert restored._verification_passed is False
        assert restored.token_usage.snapshot == source.token_usage.snapshot
        assert restored.manager.children["child-1"].status == "running"
        assert restored.manager.children["child-1"].asyncio_task is None
        assert restored.manager.completion_to_child == {"completion-old": "child-1"}
        assert restored.manager.attempt_counts == source.manager.attempt_counts
        assert restored.manager.workstream_rejections == source.manager.workstream_rejections
        assert restored.manager.presentation_queue.pending_occurrence_ids == ["occ-2"]
        assert restored.manager.presentation_queue.active_window is not None
        assert restored.manager.presentation_queue.active_window.window_id == "w6"
        assert restored.manager._delivery_event is old_delivery_event
        assert restored.manager._delivery_event is not source.manager._delivery_event

        pending_task.cancel()
        await asyncio.gather(pending_task, return_exceptions=True)

    asyncio.run(exercise())


def test_scaffold_restore_rejects_unknown_state_fields() -> None:
    scaffold = _scaffold()
    state = scaffold.export_validation_state()
    state["condition"] = "oracle_replan"

    with pytest.raises(ValueError, match="unknown scaffold validation fields"):
        scaffold.restore_validation_state(state)
