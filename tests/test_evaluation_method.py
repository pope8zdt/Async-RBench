from __future__ import annotations

from pathlib import Path

from async_rbench.evaluation.aggregate import aggregate_reports
from async_rbench.evaluation.scheduler import DeliveryController
from async_rbench.evaluation.runner import (
    _apply_delivery_intervention, _record_gateway_outcome,
)
from async_rbench.spec import load_case


ROOT = Path(__file__).resolve().parents[1]


def _case():
    return load_case(ROOT / "cases" / "data-recovery-service" / "public_case.yaml").raw


def test_scheduler_accepts_only_frozen_execution_modes() -> None:
    DeliveryController("linear", _case())
    DeliveryController("async", _case())
    try:
        DeliveryController("eventful_a", _case())
    except ValueError as exc:
        assert "unknown execution mode" in str(exc)
    else:
        raise AssertionError("legacy condition unexpectedly accepted")


def test_async_delivery_uses_completion_order() -> None:
    case = _case()
    controller = DeliveryController("async", case)
    controller.spawned = {"c1": {}, "c2": {}}
    first = {"type": "child_completed", "child_id": "c2", "completion_id": "p2", "result_kind": "result_02", "payload": {}}
    second = {"type": "child_completed", "child_id": "c1", "completion_id": "p1", "result_kind": "result_01", "payload": {}}
    assert controller.on_complete(first)[0]["completion_id"] == "p2"
    assert controller.on_complete(second)[0]["completion_id"] == "p1"


def test_async_authority_waits_for_observed_provisional_artifacts() -> None:
    case = {
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [{
                "id": "late-authority",
                "result": "authority",
                "trigger": "after_artifacts_committed",
                "after_artifacts": ["draft", "preserved"],
            }]},
        },
    }
    controller = DeliveryController("async", case)
    controller.spawned = {"c1": {}, "c2": {}}
    completion = {
        "type": "child_completed", "child_id": "c1",
        "completion_id": "authority-1", "result_kind": "authority", "payload": {},
    }
    assert controller.on_complete(completion) == []
    assert controller.on_observation({"type": "artifact_committed", "artifact_id": "draft"}) == []
    deliveries = controller.on_observation({
        "type": "artifact_committed", "artifact_id": "preserved",
    })
    assert [item["completion_id"] for item in deliveries] == ["authority-1"]


def test_force_release_bypasses_unmet_artifact_boundary_for_shutdown_only() -> None:
    case = {
        "scenarios": {"async": {"events": [{
            "id": "late-authority", "result": "authority",
            "trigger": "after_artifacts_committed", "after_artifacts": ["draft"],
        }]}},
    }
    controller = DeliveryController("async", case)
    controller.spawned = {"c1": {}, "c2": {}}
    assert controller.on_complete({
        "type": "child_completed", "child_id": "c1",
        "completion_id": "authority-1", "result_kind": "authority", "payload": {},
    }) == []
    assert controller.force_release()[0]["completion_id"] == "authority-1"


def test_deadline_release_is_controlled_and_participant_visible() -> None:
    case = {
        "scenarios": {"async": {"events": [{
            "id": "late-authority", "result": "authority",
            "trigger": "after_artifacts_committed", "after_artifacts": ["draft"],
        }]}}
    }
    controller = DeliveryController("async", case)
    controller.spawned = {"c1": {}, "c2": {}}
    assert controller.on_complete({
        "type": "child_completed", "child_id": "c1",
        "completion_id": "authority-1", "result_kind": "authority", "payload": {},
    }) == []
    delivery = controller.deadline_release()[0]
    assert delivery["controlled_order"] is True
    assert delivery["delivery_fallback_reason"] == "max_hold_seconds"


def test_hold_deadline_is_absolute_across_adapter_events() -> None:
    case = {
        "scenarios": {"async": {"events": [{
            "id": "late-authority", "result": "authority",
            "trigger": "after_artifacts_committed", "after_artifacts": ["draft"],
        }]}}
    }
    controller = DeliveryController("async", case)
    controller.spawned = {"c1": {}, "c2": {}}
    assert controller.on_complete({
        "type": "child_completed", "child_id": "c1",
        "completion_id": "authority-1", "result_kind": "authority", "payload": {},
    }) == []
    started = controller.completion_held_at_monotonic["authority-1"]
    assert controller.remaining_hold_seconds(15, now=started + 4) == 11
    # Main actions do not restart the wall-clock deadline.
    controller.on_main_action({"type": "main_action"})
    assert controller.remaining_hold_seconds(15, now=started + 16) == 0


def test_live_intervention_records_a_real_state_transition() -> None:
    import asyncio

    class Workspace:
        def __init__(self):
            self.state = "nginx"

        async def main_terminal(self, command, timeout):
            from async_rbench.evaluation.workspace_runtime import CommandResult
            if command == "observe":
                return CommandResult(0, self.state + "\n")
            self.state = "decoy"
            return CommandResult(0, "")

    class Recorder:
        def __init__(self):
            self.rows = []

        def record(self, row, source):
            value = {**row, "source": source}
            self.rows.append(value)
            return value

    case = {"scenarios": {"async": {"events": [{
        "id": "authority", "intervention": {
            "mutation_command": "mutate",
            "observer_commands": {"runtime_state": "observe"},
            "required_changed_artifacts": ["runtime_state"],
        },
    }]}}}
    recorder = Recorder()
    passed = asyncio.run(_apply_delivery_intervention(
        Workspace(), case,
        {"type": "result_delivered", "benchmark_event_id": "authority"},
        recorder, set(),
    ))
    assert passed is True
    evidence = next(row for row in recorder.rows if row["type"] == "intervention_applied")
    assert evidence["changed_artifacts"] == ["runtime_state"]
    assert evidence["passed"] is True


def test_held_result_has_a_main_action_delivery_deadline() -> None:
    case = {
        "scenarios": {"async": {"events": [{
            "id": "late-authority", "result": "authority",
            "trigger": "after_artifacts_committed", "after_artifacts": ["draft"],
            "max_hold_main_actions": 2,
        }]}}
    }
    controller = DeliveryController("async", case)
    controller.spawned = {"c1": {}, "c2": {}}
    assert controller.on_complete({
        "type": "child_completed", "child_id": "c1",
        "completion_id": "authority-1", "result_kind": "authority", "payload": {},
    }) == []
    assert controller.on_main_action({"type": "capability_request"}) == []
    delivery = controller.on_main_action({"type": "capability_request"})[0]
    assert delivery["controlled_order"] is True
    assert delivery["delivery_fallback_reason"] == "max_hold_main_actions"


def test_fallback_reason_is_persisted_in_private_evaluator_fact() -> None:
    class Recorder:
        def __init__(self) -> None:
            self.rows = []

        def record(self, row, source):
            value = {**row, "source": source}
            self.rows.append(value)
            return value

    recorder = Recorder()
    _record_gateway_outcome(recorder, {
        "type": "result_delivered",
        "completion_id": "authority-1",
        "result_kind": "authority",
        "benchmark_event_id": "late-authority",
        "controlled_order": True,
        "delivery_fallback_reason": "max_hold_seconds",
        "payload": {},
    }, {})
    fact = next(
        row for row in recorder.rows
        if row["type"] == "result_delivery_evaluator_fact"
    )
    assert fact["delivery_fallback_reason"] == "max_hold_seconds"


def test_result_boundary_releases_without_participant_artifact() -> None:
    case = {
        "scenarios": {"async": {"events": [{
            "id": "late-authority", "result": "authority",
            "trigger": "after_results_delivered", "after_results": ["provisional"],
        }]}},
    }
    controller = DeliveryController("async", case, min_initial_children=0)
    authority = {
        "type": "child_completed", "child_id": "ca", "completion_id": "a1",
        "result_kind": "authority", "payload": {},
    }
    provisional = {
        "type": "child_completed", "child_id": "cp", "completion_id": "p1",
        "result_kind": "provisional", "payload": {},
    }
    assert controller.on_complete(authority) == []
    delivered = controller.on_complete(provisional)
    assert [item["result_kind"] for item in delivered] == ["provisional", "authority"]


def test_evaluator_receipt_is_held_then_delivered_only_through_gateway() -> None:
    case = {
        "scenarios": {"async": {"events": [{
            "id": "late-authority", "result": "authority",
            "trigger": "after_results_delivered", "after_results": ["provisional"],
        }]}},
    }
    controller = DeliveryController("async", case, min_initial_children=0)
    assert controller.inject_evaluator_result(
        injection_id="late-authority", result_kind="authority",
        payload={"receipt": {"case_id": "c"}},
    ) == []
    delivered = controller.on_complete({
        "type": "child_completed", "child_id": "cp", "completion_id": "p1",
        "result_kind": "provisional", "payload": {},
    })
    assert [item["result_kind"] for item in delivered] == ["provisional", "authority"]
    authority = delivered[-1]
    assert authority["child_id"] == "evaluator"
    assert authority["payload"] == {"receipt": {"case_id": "c"}}


def test_primary_effect_is_paired_linear_minus_async() -> None:
    common = {
        "case_id": "c", "instance_id": "seed-1", "repeat": 0,
        "guidance": "incentive", "score_status": "scored",
        "leaderboard_eligible": False, "scenario_constructed": True,
    }
    report = aggregate_reports([
        {**common, "episode_id": "l", "execution_mode": "linear", "test_point_pass_rate": 0.9},
        {**common, "episode_id": "a", "execution_mode": "async", "test_point_pass_rate": 0.6},
    ], bootstrap_iterations=5)
    assert round(report["development_summary"]["paired_async_replanning_drop"], 6) == 0.3
