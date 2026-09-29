from __future__ import annotations

from types import SimpleNamespace

import pytest

from async_rbench.evaluation.scheduler import DeliveryController


CASE = {
    "scenarios": {"async": {"events": []}},
    "authoritative_result_kind": "authority",
}


def _populated_controller() -> DeliveryController:
    controller = DeliveryController("async", CASE, min_initial_children=2)
    controller.on_spawn(
        {
            "type": "child_spawned",
            "child_id": "child-1",
            "parent_id": "main",
            "work_units": ["work-a"],
        }
    )
    controller.on_child_started({"child_id": "child-1"})
    controller.on_complete(
        {
            "type": "child_completed",
            "child_id": "child-1",
            "completion_id": "completion-1",
            "result_kind": "authority",
            "payload": {"revision": "v2"},
        },
        SimpleNamespace(valid=True, reason_codes=()),
    )
    controller.consumed.add("completion-old")
    controller.committed_artifacts.add("artifact-a")
    controller.scope_snapshot = {"scope": "v2"}
    controller.dependency_graph_edges = {"edge-a": ("left", "right")}
    controller.revision_audits.append({"type": "scope_revision", "applied": True})
    controller.pressure_audits.append({"type": "resource_pressure", "applied": True})
    controller.deadline_audits.append({"type": "deadline_update", "reason": "new SLA"})
    controller._effective_deadline_wall = 1045.0
    controller._response_window_active = True
    controller._occurrence_ordinal = 3
    controller._delivery_occurrence_of_completion = {
        "completion-old": "gateway-occ-2"
    }
    controller.completion_held_at_monotonic["completion-1"] = 88.0
    return controller


def test_controller_state_round_trip_preserves_logical_state_and_rebases_clocks() -> None:
    source = _populated_controller()

    state = source.export_validation_state(now_monotonic=100.0, now_wall=1000.0)
    restored = DeliveryController.from_validation_state(
        CASE,
        state,
        now_monotonic=500.0,
        now_wall=2000.0,
    )

    assert restored.execution_mode == "async"
    assert restored.min_initial_children == 2
    assert restored.spawned == source.spawned
    assert restored.completions == source.completions
    assert restored.delivered == source.delivered
    assert restored.consumed == {"completion-old"}
    assert restored.committed_artifacts == {"artifact-a"}
    assert restored.running_children == set()
    assert restored.scope_snapshot == {"scope": "v2"}
    assert restored.dependency_graph_edges == {"edge-a": ("left", "right")}
    assert restored.revision_audits == source.revision_audits
    assert restored.pressure_audits == source.pressure_audits
    assert restored.deadline_audits == source.deadline_audits
    assert restored._effective_deadline_wall == pytest.approx(2045.0)
    assert restored._response_window_active is True
    assert restored._occurrence_ordinal == 3
    assert restored._delivery_occurrence_of_completion == {
        "completion-old": "gateway-occ-2"
    }
    assert restored.completion_held_at_monotonic["completion-1"] == pytest.approx(488.0)


def test_controller_export_contains_relative_time_not_process_clock_values() -> None:
    state = _populated_controller().export_validation_state(
        now_monotonic=100.0,
        now_wall=1000.0,
    )

    assert state["completion_hold_elapsed_seconds"] == {"completion-1": 12.0}
    assert state["deadline_remaining_seconds"] == 45.0
    assert "completion_held_at_monotonic" not in state
    assert "effective_deadline_wall" not in state


def test_controller_restore_rejects_unknown_fields_and_mode_mismatch() -> None:
    state = _populated_controller().export_validation_state(
        now_monotonic=100.0,
        now_wall=1000.0,
    )
    state["unexpected"] = True

    with pytest.raises(ValueError, match="unknown controller validation fields"):
        DeliveryController.from_validation_state(CASE, state)

    state.pop("unexpected")
    state["execution_mode"] = "linear"
    with pytest.raises(ValueError, match="does not match case schedule"):
        DeliveryController.from_validation_state(CASE, state)
