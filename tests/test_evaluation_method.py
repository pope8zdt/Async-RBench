from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

import yaml

import async_rbench.evaluation.runner as runner_module
from async_rbench.evaluation.case_contract import public_delivery

from async_rbench.evaluation.aggregate import aggregate_reports
from async_rbench.evaluation.scheduler import DeliveryController
from async_rbench.evaluation.runner import (
    _apply_delivery_intervention, _make_start, _record_gateway_outcome,
    EpisodeConfig,
)
from async_rbench.evaluation.workspace_runtime import DisabledWorkspaceRuntime
from async_rbench.profiles.conformance_mock.scripted_backend import ScriptedTestBackend
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig
from async_rbench.profiles.reference_scaffold_api.gateway import DeliveryReader, ProtocolEmitter
from async_rbench.profiles.reference_scaffold_api.runtime import ReferenceScaffold
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


# --- Presentation handshake (Task 4 §3.3 / §5.1(4)) -----------------------
#
# The runtime prepares the evaluator-owned before-snapshot S_i^- and only
# authorizes presenting a delivery occurrence once the snapshot is complete.
# A failed snapshot must leave the occurrence queued and un-presented (spec
# §5.1(4)).  Order (spec §3.3, §5.1(2)): budget admitted -> presentation
# prepared -> delivery message appended -> main API request started ->
# result_presented.  These tests drive that handshake at the runtime seam.


def _rt_start() -> dict:
    case_path = ROOT / "cases" / "data-recovery-service" / "public_case.yaml"
    case = load_case(case_path).raw
    task = yaml.safe_load((case_path.parent / "task" / "task.yaml").read_text(encoding="utf-8"))
    config = EpisodeConfig(
        episode_id="test-presentation", case_id="data-recovery-service",
        execution_mode="async", guidance="incentive", agent_seed=1,
        adapter_command=[], output_dir=ROOT / "artifacts" / "test-unused",
        use_container=False,
    )
    return _make_start(config, case, task, None, "0123456789ab")


def _rt_scaffold(start: dict) -> ReferenceScaffold:
    config = ScaffoldConfig.from_file(
        None, {"backend": "scripted_test", "workspace_mode": "disabled"},
    )
    return ReferenceScaffold(
        start=start,
        config=config,
        backend=ScriptedTestBackend(),
        workspace=DisabledWorkspaceRuntime(),
        emitter=ProtocolEmitter(stdout=io.StringIO()),
        delivery_reader=DeliveryReader(),
    )


def _inject_delivery(scaffold: ReferenceScaffold, child_id: str, completion_id: str) -> None:
    from async_rbench.profiles.reference_scaffold_api.runtime import ChildRecord
    scaffold.manager.children[child_id] = ChildRecord(
        child_id=child_id, task="work", work_units=["wal_recovery"], targets=[],
        expected_output="out", priority="high", status="completed_hidden",
        completion_id=completion_id,
    )
    scaffold.manager.completion_to_child[completion_id] = child_id


def test_presentation_failed_snapshot_leaves_occurrence_queued() -> None:
    """A rejected before-snapshot never marks the occurrence presented (spec §5.1(4))."""
    class RejectingWorkspace(DisabledWorkspaceRuntime):
        async def prepare_result_presentation(self, delivery_occurrence_id, *, turn_id):
            return {"prepared": False, "error": "incomplete_snapshot"}

    async def exercise() -> None:
        scaffold = _rt_scaffold(_rt_start())
        scaffold.workspace = RejectingWorkspace()
        _inject_delivery(scaffold, "child-1", "compl-1")
        await scaffold.manager.handle_delivery(
            {"completion_id": "compl-1", "payload": {"id": 1}},
        )
        candidate = scaffold.manager.select_presentable()
        assert candidate is not None
        prepared_id = await scaffold._prepare_presentation(candidate, "t1")
        assert prepared_id is None
        # The occurrence stays queued (still selectable) and was never presented.
        again = scaffold.manager.select_presentable()
        assert again is not None and again.completion_id == "compl-1"
        assert scaffold.manager.presentation_queue.presented_occurrence(
            candidate.occurrence_id
        ) is None

    asyncio.run(exercise())


def test_presentation_prepared_snapshot_is_then_marked_presented() -> None:
    """Order: prepare S^- -> append delivery -> start request -> result_presented."""
    class AcceptingWorkspace(DisabledWorkspaceRuntime):
        async def prepare_result_presentation(self, delivery_occurrence_id, *, turn_id):
            return {"prepared": True, "snapshot_digest": "d" * 64}

    async def exercise() -> None:
        scaffold = _rt_scaffold(_rt_start())
        scaffold.workspace = AcceptingWorkspace()
        _inject_delivery(scaffold, "child-1", "compl-1")
        await scaffold.manager.handle_delivery(
            {"completion_id": "compl-1", "payload": {"id": 1}},
        )
        candidate = scaffold.manager.select_presentable()
        assert candidate is not None
        # Handshake authorizes presenting: the before-snapshot is prepared first.
        prepared_id = await scaffold._prepare_presentation(candidate, "t1")
        assert prepared_id == candidate.occurrence_id
        # Only after the request that carries it starts is it marked presented,
        # which emits the public result_presented boundary.
        scaffold.manager.mark_presented(
            candidate.occurrence_id, turn_id="t1", window_id="w1",
        )
        presented = scaffold.manager.presentation_queue.presented_occurrence(
            candidate.occurrence_id,
        )
        assert presented is not None

    asyncio.run(exercise())


# --- Real specialised-event stimuli (Task 9) --------------------------------
#
# Each of the 8 stimulus mechanisms is tested at the DeliveryController seam —
# the gateway is the only actor that can produce a designed timeout/crash, an
# implicit-error marker, a live scope/dependency revision, a resource-pressure
# boundary, or an applied deadline update, so these tests assert the mechanism
# invariants the controller owns (occurrence identity, in-flight proof,
# designed-vs-infra classification, before/after digests, pressure proof).


def test_completion_replay_same_completion_new_occurrence() -> None:
    """A replay is a fresh gateway occurrence, not a clone of the completion."""
    case = {
        "authoritative_result_kind": "authority",
        "superseded_result_kind": "provisional",
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [
                {"id": "authority", "result": "authority"},
                {
                    "id": "replay", "stimulus_type": "completion_replay",
                    "replay_of_result": "authority", "trigger": "after_consumed",
                },
            ]},
        },
    }
    controller = DeliveryController("async", case)
    controller.spawned = {"c1": {}, "c2": {}}
    original = controller.on_complete({
        "child_id": "c1", "completion_id": "p1", "result_kind": "authority",
        "payload": {"revision": "v2"},
    })[0]
    replay = controller.on_consumed({"completion_id": "p1"})[0]
    # Same completion, new delivery occurrence (spec §3.3): the occurrence id is
    # what distinguishes one delivery of the same completion from another.
    assert replay["completion_id"] == original["completion_id"]
    assert replay["replay_of_completion_id"] == original["completion_id"]
    assert replay["delivery_occurrence_id"] != original["delivery_occurrence_id"]
    assert replay["replay_of_occurrence_id"] == original["delivery_occurrence_id"]
    assert replay["replayed"] is True
    assert replay["payload_sha256"] == original["payload_sha256"]


def test_designed_child_timeout_is_model_visible_and_scored() -> None:
    """A designed timeout requires the child to have been running and is delivered."""
    controller = DeliveryController("async", {
        "scenarios": {"linear": {"events": []}, "async": {"events": []}},
    })
    # The gateway must have observed the child in flight before it can design a
    # terminal outcome for it (spec §6.2).
    assert controller.on_child_started({
        "type": "child_started", "child_id": "c1",
    }) == []
    delivery = controller.apply_child_terminal_outcome(
        child_id="c1", completion_id="p1", result_kind="authority",
        payload={"result": "partial"}, outcome="timeout",
        detail="designed timeout", designed=True,
    )[0]
    assert delivery["type"] == "result_delivered"
    assert delivery["completion_id"] == "p1"
    assert delivery["terminal_outcome"] == "timeout"
    assert delivery["evaluator_designed_failure"] is True
    assert delivery["evaluator_terminal_reason"] == "designed timeout"
    assert "delivery_occurrence_id" in delivery
    audit = controller.terminal_outcomes[-1]
    assert audit["designed"] is True
    assert audit["was_in_flight"] is True
    assert audit["outcome"] == "timeout"


def test_designed_child_timeout_refused_when_child_not_in_flight() -> None:
    """A design cannot attach a terminal outcome to a child that never ran."""
    controller = DeliveryController("async", {
        "scenarios": {"linear": {"events": []}, "async": {"events": []}},
    })
    assert controller.apply_child_terminal_outcome(
        child_id="ghost", completion_id="p9", result_kind="authority",
        payload={"result": "partial"}, outcome="timeout",
        detail="designed timeout", designed=True,
    ) == []
    assert controller.infrastructure_failures == []
    assert controller.terminal_outcomes[-1]["was_in_flight"] is False


def test_designed_child_crash_is_scored_infra_crash_is_unscored() -> None:
    """A case-designed crash is scored; a provider/workspace crash is unscored."""
    controller = DeliveryController("async", {
        "scenarios": {"linear": {"events": []}, "async": {"events": []}},
    })
    controller.on_child_started({"type": "child_started", "child_id": "c1"})
    # Case-designed crash source -> scored, model-visible terminal outcome.
    designed = controller.apply_child_crash(
        child_id="c1", completion_id="p1", result_kind="authority",
        payload={"result": "boom"}, crash_source="case_designed",
        detail="case-designed crash",
    )[0]
    assert designed["type"] == "result_delivered"
    assert designed["terminal_outcome"] == "crash"
    assert designed["evaluator_designed_failure"] is True
    assert controller.infrastructure_failures == []
    # Provider/workspace outage -> parked as an unscored infrastructure failure.
    controller.on_child_started({"type": "child_started", "child_id": "c2"})
    assert controller.apply_child_crash(
        child_id="c2", completion_id="p2", result_kind="authority",
        payload={"result": "boom"}, crash_source="provider_outage",
        detail="provider outage",
    ) == []
    assert controller.infrastructure_failures[-1]["component"] == "child_terminal"
    assert controller.infrastructure_failures[-1]["outcome"] == "crash"
    assert all(
        audit["outcome"] != "crash" or (audit.get("designed") and audit["child_id"] != "c2")
        for audit in controller.terminal_outcomes
    )


def test_implicit_error_passes_structure_but_marks_private_failure() -> None:
    """An implicit-error delivery is structurally valid yet privately a failure."""
    case = {
        "implicit_error_predicate": {
            "type": "evidence_marker", "evidence_field": "injected", "marker": True,
        },
        "scenarios": {"linear": {"events": []}, "async": {"events": [
            {"id": "implicit-error", "stimulus_type": "implicit_error_result", "result": "authority"},
        ]}},
    }
    controller = DeliveryController("async", case, min_initial_children=0)
    delivery = controller.on_complete({
        "type": "child_completed", "child_id": "c1", "completion_id": "p1",
        "result_kind": "authority",
        "payload": {"evidence": {"injected": True}, "result": 42},
    })[0]
    assert delivery["type"] == "result_delivered"
    assert delivery["evaluator_implicit_error"] is True
    assert delivery["evaluator_implicit_error_measurable"] is True
    assert delivery["evaluator_implicit_error_reason"] == "evidence injected is truthy"


def test_implicit_error_schedule_event_type_is_its_own_truth() -> None:
    """Without a predicate, the private signal is the schedule-event type itself."""
    case = {
        "scenarios": {"linear": {"events": []}, "async": {"events": [
            {"id": "implicit-error", "stimulus_type": "implicit_error_result", "result": "authority"},
        ]}},
    }
    controller = DeliveryController("async", case, min_initial_children=0)
    delivery = controller.on_complete({
        "type": "child_completed", "child_id": "c1", "completion_id": "p1",
        "result_kind": "authority", "payload": {"result": 42},
    })[0]
    assert delivery["evaluator_implicit_error"] is True
    assert delivery["evaluator_implicit_error_measurable"] is True
    assert delivery["evaluator_implicit_error_reason"] == "implicit_error_result schedule event"


def test_task_scope_revision_records_digests_and_keeps_expected_response_private() -> None:
    """A live scope revision records before/after digests and hides the truth."""
    controller = DeliveryController("async", {
        "scenarios": {"linear": {"events": []}, "async": {"events": []}},
    })
    assert controller.apply_task_scope_revision(
        revision_id="r1", new_scope={"ownership": "claimed"},
        participant_visible_fields={"notice": "scope changed"},
        expected_response={"ownership": "claimed"},
    ) == []
    audit = controller.revision_audits[-1]
    assert audit["type"] == "task_scope_revision"
    assert audit["changed"] is True
    for key in ("before_digest", "after_digest"):
        digest = audit[key]
        assert len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest)
    assert audit["participant_visible"] == {"notice": "scope changed"}
    assert audit["expected_response_preserved"] is True
    assert audit["private_expected_response_hidden"] is True


def test_dependency_graph_revision_records_per_edge_digests() -> None:
    """An affected dependency edge carries before/after digests on the audit."""
    controller = DeliveryController("async", {
        "scenarios": {"linear": {"events": []}, "async": {"events": []}},
    })
    controller.dependency_graph_edges = {"db": ("migrate", "seed")}
    assert controller.apply_dependency_graph_revision(
        revision_id="dg1", new_edges={"db": ("migrate", "backfill")},
        participant_visible_fields={"graph_notice": "edge 1 revised"},
        expected_response={"db": ("migrate", "backfill")},
    ) == []
    audit = controller.revision_audits[-1]
    assert audit["type"] == "dependency_graph_revision"
    edge = audit["affected_edges"]["db"]
    for key in ("before_digest", "after_digest"):
        digest = edge[key]
        assert len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest)
    assert edge["changed"] is True
    assert audit["participant_visible"] == {"graph_notice": "edge 1 revised"}
    assert audit["expected_response_preserved"] is True


def test_resource_pressure_requires_designated_straggler_in_flight() -> None:
    """Pressure only activates for a straggler the gateway proved is running."""
    controller = DeliveryController("async", {
        "scenarios": {"linear": {"events": []}, "async": {"events": []}},
    })
    controller.concurrency_limit = 4
    controller.child_pool_remaining = 2
    controller.on_child_started({"type": "child_started", "child_id": "c1"})
    controller.on_child_started({"type": "child_started", "child_id": "c2"})
    assert controller.apply_resource_pressure(
        straggler_child_id="c1", limit=2, pool_remaining=1,
    ) == []
    audit = controller.pressure_audits[-1]
    assert audit["applied"] is True
    assert audit["straggler_in_flight"] is True
    assert audit["active_count"] == 2
    assert audit["active_children"] == ["c1", "c2"]
    assert audit["before_concurrency_limit"] == 4
    assert audit["after_concurrency_limit"] == 2
    assert audit["before_pool_remaining"] == 2
    assert audit["after_pool_remaining"] == 1


def test_resource_pressure_refused_when_straggler_no_longer_in_flight() -> None:
    """Pressure is refused once the designated straggler has already resolved."""
    controller = DeliveryController("async", {
        "scenarios": {"linear": {"events": []}, "async": {"events": []}},
    })
    controller.on_child_started({"type": "child_started", "child_id": "c1"})
    controller.on_complete({
        "type": "child_completed", "child_id": "c1", "completion_id": "p1",
        "result_kind": "authority", "payload": {},
    })
    assert controller.apply_resource_pressure(
        straggler_child_id="c1", limit=2, pool_remaining=1,
    ) == []
    audit = controller.pressure_audits[-1]
    assert audit["applied"] is False
    assert audit["straggler_in_flight"] is False
    assert audit["reason"] == "straggler was not in flight"


def test_deadline_update_applied_and_recorded_before_response_window() -> None:
    """A new deadline is recorded before a response window opens."""
    controller = DeliveryController("async", {
        "scenarios": {"linear": {"events": []}, "async": {"events": []}},
    })
    assert controller.apply_deadline_update(
        deadline_wall=1234.5, reason="initial sla",
    ) == []
    audit = controller.deadline_audits[-1]
    assert audit["before_deadline"] is None
    assert audit["after_deadline"] == 1234.5
    assert audit["applied_before_response_window"] is True
    assert audit["response_window_active"] is False


def test_deadline_update_after_window_open_is_flagged_false() -> None:
    """A window already open means the participant saw the prior deadline."""
    controller = DeliveryController("async", {
        "scenarios": {"linear": {"events": []}, "async": {"events": []}},
    })
    controller.on_response_window(True)
    assert controller.apply_deadline_update(
        deadline_wall=2000, reason="renewed sla",
    ) == []
    audit = controller.deadline_audits[-1]
    assert audit["before_deadline"] is None
    assert audit["after_deadline"] == 2000
    assert audit["applied_before_response_window"] is False
    assert audit["response_window_active"] is True


# --- Review spec-issue fixes (b)/(c): designed terminal reaches main -------------------
#
# (b) the adapter must accept a gateway-owned designed terminal even though its
#     completion_id has no completion_to_child binding; (c) the public
#     projection must expose the observable terminal state while keeping the
#     designed/infrastructure classification and the design reason private.


def test_public_delivery_projects_terminal_outcome_but_hides_design_fact() -> None:
    """(c) main sees the child terminated; it never sees the design classification."""
    outcome = {
        "type": "result_delivered", "child_id": "c1", "completion_id": "p1",
        "result_kind": "authority", "payload": {"result": "partial"},
        "payload_sha256": "a" * 64,
        "terminal_outcome": "timeout",
        "evaluator_designed_failure": True,
        "evaluator_terminal_reason": "designed timeout",
    }
    public = public_delivery(outcome, workstream_id="ws1")
    assert public["terminal_outcome"] == "timeout"
    assert public["child_id"] == "c1"
    # The scoring-only classification and reason never reach the participant.
    assert "evaluator_designed_failure" not in public
    assert "evaluator_terminal_reason" not in public
    assert "result_kind" not in public
    # A normal (non-terminal) delivery carries no terminal field at all.
    normal = public_delivery({
        "type": "result_delivered", "child_id": "c1", "completion_id": "p1",
        "payload": {"result": "ok"}, "payload_sha256": "b" * 64,
    }, workstream_id="ws1")
    assert "terminal_outcome" not in normal


def _register_in_flight_child(scaffold: ReferenceScaffold, child_id: str) -> None:
    """Register a child that is still running and has no completion binding."""
    from async_rbench.profiles.reference_scaffold_api.runtime import ChildRecord
    scaffold.manager.children[child_id] = ChildRecord(
        child_id=child_id, task="work", work_units=["wal_recovery"], targets=[],
        expected_output="out", priority="high", status="running",
        completion_id=None,
    )


def test_handle_delivery_accepts_designed_terminal_outcome() -> None:
    """(b) a gateway-designed terminal is bound to a known child via child_id."""
    async def exercise() -> None:
        scaffold = _rt_scaffold(_rt_start())
        _register_in_flight_child(scaffold, "c1")
        # The delivery carries a synthetic completion_id the adapter never saw;
        # the terminal_outcome marker is what tells it this is a gateway-owned
        # child terminal for an in-flight child.
        await scaffold.manager.handle_delivery({
            "type": "result_delivered", "completion_id": "p1", "child_id": "c1",
            "result_kind": "authority", "payload": {"result": "partial"},
            "payload_sha256": "a" * 64,
            "terminal_outcome": "timeout",
            "evaluator_designed_failure": True,
            "evaluator_terminal_reason": "designed timeout",
        })
        candidate = scaffold.manager.select_presentable()
        assert candidate is not None
        assert candidate.completion_id == "p1"
        # (c) the enqueued occurrence exposes the terminal state, not the design.
        assert candidate.payload["terminal_outcome"] == "timeout"
        assert "evaluator_designed_failure" not in candidate.payload
        assert "evaluator_terminal_reason" not in candidate.payload

    asyncio.run(exercise())


def test_handle_delivery_still_rejects_unrelated_unknown_completion() -> None:
    """(b) unknown completions that are not a designed terminal stay rejected."""
    async def exercise() -> None:
        scaffold = _rt_scaffold(_rt_start())
        # No in-flight child and no terminal marker: unchanged "unknown" path.
        await scaffold.manager.handle_delivery({
            "type": "result_delivered", "completion_id": "p9",
            "child_id": "ghost", "payload": {},
        })
        assert scaffold.manager.select_presentable() is None

    asyncio.run(exercise())


# --- Review spec-issue fix (a): a case declaration reaches an apply_* producer ---


def test_consume_declared_stimuli_fires_designed_timeout_once() -> None:
    """(a) a case-declared child_timeout schedule event fires apply_*."""
    case = {
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [
                {"id": "designed-timeout", "stimulus_type": "child_timeout",
                 "child_id": "c1", "result": "authority",
                 "payload": {"result": "partial"},
                 "outcome_detail": "designed timeout"},
            ]},
        },
    }
    controller = DeliveryController("async", case)
    controller.on_child_started({"type": "child_started", "child_id": "c1"})
    started = {"type": "child_started", "child_id": "c1"}
    deliveries = controller.consume_declared_stimuli(started)
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery["type"] == "result_delivered"
    assert delivery["completion_id"] == "terminal:designed-timeout"
    assert delivery["terminal_outcome"] == "timeout"
    assert delivery["evaluator_designed_failure"] is True
    # The declared stimulus fires exactly once for the child.
    assert controller.consume_declared_stimuli(started) == []
    # A child that never went in flight is refused, not delivered.
    other = DeliveryController("async", case)
    assert other.consume_declared_stimuli({"type": "child_started", "child_id": "c1"}) == []


def _write_stimulus_case(tmp_path: Path) -> Path:
    case = tmp_path / "case"
    (case / "private").mkdir(parents=True)
    (case / "task" / "tests").mkdir(parents=True)
    (case / "task" / "assets").mkdir(parents=True)
    (case / "public_case.yaml").write_text(yaml.safe_dump({
        "format_version": 2, "case_id": "stimulus-case",
        "title": "Designed child terminal", "task_instruction_path": "task/task.yaml",
        "workstreams": [{
            "id": "authority", "task": "recover", "targets": [],
            "expected_output": "out", "priority": "normal",
        }],
        "artifacts": [],
    }), encoding="utf-8")
    (case / "private/private_case.yaml").write_text(yaml.safe_dump({
        "case_id": "stimulus-case",
        "scenarios": {"async": {"events": [
            {"id": "designed-timeout", "stimulus_type": "child_timeout", "child_id": "c1",
             "result": "authority", "payload": {"result": "partial"},
             "outcome_detail": "designed timeout"},
        ]}},
    }), encoding="utf-8")
    (case / "task/task.yaml").write_text(yaml.safe_dump({
        "instruction": "Recover the state.",
    }), encoding="utf-8")
    (case / "task/run-tests.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (case / "task/tests/semantic_checks.json").write_text(
        json.dumps({"checks": []}), encoding="utf-8")
    (case / "task/tests/control_flow_checks.json").write_text(
        json.dumps({"version": "1", "checks": []}), encoding="utf-8")
    return case


def test_run_episode_triggers_declared_child_timeout(
    tmp_path: Path, monkeypatch,
) -> None:
    """(a) run_episode consumes the case declaration and emits the delivery."""
    class _Stdin:
        def write(self, _payload: bytes) -> None:
            return None

        async def drain(self) -> None:
            return None

    class _FakeProcess:
        def __init__(self, events: list[dict]) -> None:
            self.stdin = _Stdin()
            self.stderr = asyncio.StreamReader()
            self.stdout = asyncio.StreamReader()
            self.stdout.feed_data(
                b"".join(json.dumps(event).encode() + b"\n" for event in events)
            )
            self.stdout.feed_eof()
            self.stderr.feed_eof()
            self.returncode = 0

        async def wait(self) -> int:
            return self.returncode

        def kill(self) -> None:
            self.returncode = -9

    events = [
        {"type": "participant_metadata", "backend": "scripted_test",
         "main_model": "scripted-main", "child_model": "scripted-child",
         "workspace_mode": "container_clone"},
        {"type": "ready"},
        {"type": "child_spawned", "child_id": "c1", "work_units": ["authority"]},
        {"type": "child_started", "child_id": "c1"},
        {"type": "episode_ended", "final_answer": "done",
         "local_status": "completed", "declared_task_success": True},
    ]
    fake_docker = lambda *_a, **_k: __import__("types").SimpleNamespace(stdout="", returncode=0)
    monkeypatch.setattr(runner_module, "_docker", fake_docker)
    monkeypatch.setattr(
        runner_module, "build_workspace_runtime",
        lambda *_a, **_k: __import__(
            "async_rbench.evaluation.workspace_runtime",
            fromlist=["DisabledWorkspaceRuntime"],
        ).DisabledWorkspaceRuntime(),
    )
    async def fake_subprocess(*_a, **_k) -> _FakeProcess:
        return _FakeProcess(events)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)

    case_dir = _write_stimulus_case(tmp_path)
    config = EpisodeConfig(
        episode_id="stimulus-trigger", case_id="stimulus-case",
        execution_mode="async", guidance="incentive", agent_seed=1,
        adapter_command=["fake-adapter"], output_dir=tmp_path / "out",
        use_container=False, timeout_sec=10,
        case_dir_override=case_dir,
    )
    asyncio.run(runner_module.run_episode(ROOT, config))

    trace = (tmp_path / "out" / "trace.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in trace.splitlines() if line.strip()]
    terminal_deliveries = [
        row for row in rows
        if row.get("type") == "result_delivered" and row.get("terminal_outcome") == "timeout"
    ]
    assert terminal_deliveries
    assert terminal_deliveries[0]["child_id"] == "c1"
    # The classification stays a kernel-private audit, not a public delivery field.
    assert all("evaluator_designed_failure" not in row for row in terminal_deliveries)
    assert any(row.get("type") == "child_terminal_outcome" for row in rows)


# --- Task 10 swimlane 0a: shared stimulus_type contract, remaining producers --
#
# The scenario/schedule field that names a stimulus kind is ``stimulus_type``
# (never ``type``, which is reserved for runtime EventStore facts).  The
# consumption seam dispatches every declared live stimulus to its producer
# exactly once, and the four remaining producers (resource_pressure /
# deadline_update / task_scope_revision / dependency_graph_revision) are
# asserted end-to-end through ``run_episode``.


def _write_live_case(tmp_path: Path, *, events: list[dict], case_id: str = "live-stimulus-case") -> Path:
    """Write a minimal runnable async case whose schedule declares ``events``."""
    case = tmp_path / case_id
    (case / "private").mkdir(parents=True)
    (case / "task" / "tests").mkdir(parents=True)
    (case / "task" / "assets").mkdir(parents=True)
    (case / "public_case.yaml").write_text(yaml.safe_dump({
        "format_version": 2, "case_id": case_id,
        "title": "Declared live stimulus", "task_instruction_path": "task/task.yaml",
        "workstreams": [{
            "id": "authority", "task": "recover", "targets": [],
            "expected_output": "out", "priority": "normal",
        }],
        "artifacts": [],
    }), encoding="utf-8")
    (case / "private/private_case.yaml").write_text(yaml.safe_dump({
        "case_id": case_id,
        "scenarios": {"async": {"events": events}},
    }), encoding="utf-8")
    (case / "task/task.yaml").write_text(yaml.safe_dump({
        "instruction": "Recover the state.",
    }), encoding="utf-8")
    (case / "task/run-tests.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (case / "task/tests/semantic_checks.json").write_text(
        json.dumps({"checks": []}), encoding="utf-8")
    (case / "task/tests/control_flow_checks.json").write_text(
        json.dumps({"version": "1", "checks": []}), encoding="utf-8")
    return case


async def _noop_drain(self: object) -> None:
    """Coroutine no-op bound to ``_FakeLiveAdapter.stdin.drain``."""


class _FakeLiveAdapter:
    """A scripted adapter process that replays ``events`` then finishes cleanly."""

    def __init__(self, events: list[dict]) -> None:
        self.events = events
        self.stdin = type("_StdIn", (), {
            "write": lambda self, _payload: None,
            "drain": _noop_drain,
        })()
        self.stderr = asyncio.StreamReader()
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(
            b"".join(json.dumps(event).encode() + b"\n" for event in events)
        )
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        self.returncode = 0

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


def _patch_live_adapter(monkeypatch, events: list[dict]) -> None:
    monkeypatch.setattr(
        runner_module, "_docker",
        lambda *_a, **_k: __import__("types").SimpleNamespace(stdout="", returncode=0),
    )
    monkeypatch.setattr(
        runner_module, "build_workspace_runtime",
        lambda *_a, **_k: DisabledWorkspaceRuntime(),
    )
    async def _spawn(*_a, **_k) -> _FakeLiveAdapter:
        return _FakeLiveAdapter(events)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)


def _adapter_events(child_id: str = "c1") -> list[dict]:
    """The adapter-visible event script that drives one child to ``child_started``."""
    return [
        {"type": "participant_metadata", "backend": "scripted_test",
         "main_model": "scripted-main", "child_model": "scripted-child",
         "workspace_mode": "container_clone"},
        {"type": "ready"},
        {"type": "child_spawned", "child_id": child_id, "work_units": ["authority"]},
        {"type": "child_started", "child_id": child_id},
        {"type": "episode_ended", "final_answer": "done",
         "local_status": "completed", "declared_task_success": True},
    ]


def _live_episode_config(tmp_path: Path, case_dir: Path, episode_id: str) -> EpisodeConfig:
    return EpisodeConfig(
        episode_id=episode_id, case_id=case_dir.name,
        execution_mode="async", guidance="incentive", agent_seed=1,
        adapter_command=["fake-adapter"], output_dir=tmp_path / "out",
        use_container=False, timeout_sec=10,
        case_dir_override=case_dir,
    )


def _trace_rows(tmp_path: Path) -> list[dict]:
    trace = (tmp_path / "out" / "trace.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in trace.splitlines() if line.strip()]


def test_consume_declared_stimuli_dispatches_every_live_kind_once() -> None:
    """The seam fires each declared live stimulus at most once and skips delivery rows."""
    case = {
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [
                # Live rows (no result role) consumed by the seam.
                {"id": "pres", "stimulus_type": "resource_pressure",
                 "straggler_child_id": "c1", "resource": "concurrency_slot", "limit": 2},
                {"id": "deadline", "stimulus_type": "deadline_update",
                 "deadline_wall": 3600.0, "reason": "sla"},
                {"id": "scope", "stimulus_type": "task_scope_revision",
                 "revision_id": "r1", "new_scope": {"a": 1},
                 "participant_visible_fields": {"scope": "b"}},
                {"id": "graph", "stimulus_type": "dependency_graph_revision",
                 "revision_id": "g1", "new_edges": {"db": ["a", "b"]},
                 "participant_visible_fields": {"edges": ["a", "b"]}},
                # A result-bearing revision row is a delivery row: the seam must
                # not consume it (it is governed by _drain / _delivery instead).
                {"id": "auth-scope", "stimulus_type": "task_scope_revision",
                 "result": "authority", "invalidates_artifacts": ["final"]},
            ]},
        },
    }
    controller = DeliveryController("async", case)
    # The runner records the child in flight before the seam consumes it.
    controller.on_child_started({"type": "child_started", "child_id": "c1"})
    # First child boundary fires deadline + both live revisions and the pressure
    # targeted at c1; the result-bearing revision row stays untouched.
    deliveries = controller.consume_declared_stimuli({
        "type": "child_started", "child_id": "c1",
    })
    assert deliveries == []
    assert len(controller.pressure_audits) == 1
    assert controller.pressure_audits[0]["applied"] is True
    assert len(controller.deadline_audits) == 1
    assert controller.deadline_audits[0]["after_deadline"] == 3600.0
    assert len(controller.revision_audits) == 2
    assert {a["revision_id"] for a in controller.revision_audits} == {"r1", "g1"}
    # The seam is idempotent: further child boundaries fire nothing.
    controller.on_child_started({"type": "child_started", "child_id": "c2"})
    assert controller.consume_declared_stimuli({
        "type": "child_started", "child_id": "c2",
    }) == []
    assert len(controller.pressure_audits) == 1
    assert len(controller.deadline_audits) == 1
    assert len(controller.revision_audits) == 2


def test_consume_declared_deadline_update_missing_wall_notes_once() -> None:
    """A deadline_update row without deadline_wall degrades to a single note.

    It is consumed once under its declared id, so later child boundaries neither
    re-append the note nor emit a deadline audit.
    """
    case = {"scenarios": {"linear": {"events": []}, "async": {"events": [
        {"id": "deadline", "stimulus_type": "deadline_update", "reason": "sla"},
    ]}}}
    controller = DeliveryController("async", case)
    for child in ("c1", "c2", "c3"):
        controller.on_child_started({"type": "child_started", "child_id": child})
        assert controller.consume_declared_stimuli({
            "type": "child_started", "child_id": child,
        }) == []
    assert controller.deadline_audits == []
    notes = [n for n in controller.protocol_notes if "deadline_update" in n]
    assert len(notes) == 1
    assert "missing deadline_wall" in notes[0]


def test_consume_declared_deadline_update_malformed_wall_does_not_crash() -> None:
    """A non-numeric deadline_wall degrades to a note instead of a float() crash.

    The row is recorded under its declared id, so the note is appended once and
    no deadline audit is produced.
    """
    case = {"scenarios": {"linear": {"events": []}, "async": {"events": [
        {"id": "deadline", "stimulus_type": "deadline_update",
         "deadline_wall": "2026-09-03T00:00:00Z", "reason": "iso-wall"},
    ]}}}
    controller = DeliveryController("async", case)
    for child in ("c1", "c2"):
        controller.on_child_started({"type": "child_started", "child_id": child})
        assert controller.consume_declared_stimuli({
            "type": "child_started", "child_id": child,
        }) == []
    assert controller.deadline_audits == []
    notes = [n for n in controller.protocol_notes if "deadline_update" in n]
    assert len(notes) == 1
    assert "not numeric" in notes[0]


def test_run_episode_consumes_declared_resource_pressure(
    tmp_path: Path, monkeypatch,
) -> None:
    """A declared resource_pressure stimulus is consumed and audited end-to-end."""
    case = _write_live_case(tmp_path, events=[
        {"id": "pressure", "stimulus_type": "resource_pressure",
         "straggler_child_id": "c1", "resource": "concurrency_slot", "limit": 2,
         "pool_remaining": 1},
    ])
    _patch_live_adapter(monkeypatch, _adapter_events())
    config = _live_episode_config(tmp_path, case, "live-pressure")
    asyncio.run(runner_module.run_episode(ROOT, config))
    facts = [r for r in _trace_rows(tmp_path) if r.get("type") == "resource_pressure"]
    assert facts, "resource_pressure audit never reached the trace"
    assert facts[0]["applied"] is True
    assert facts[0]["straggler_child_id"] == "c1"
    assert facts[0]["visibility"] == "kernel_private"


def test_run_episode_consumes_declared_deadline_update(
    tmp_path: Path, monkeypatch,
) -> None:
    """A declared deadline_update stimulus is consumed and audited end-to-end."""
    case = _write_live_case(tmp_path, events=[
        {"id": "deadline", "stimulus_type": "deadline_update",
         "deadline_wall": 7200.0, "reason": "sla"},
    ])
    _patch_live_adapter(monkeypatch, _adapter_events())
    config = _live_episode_config(tmp_path, case, "live-deadline")
    asyncio.run(runner_module.run_episode(ROOT, config))
    facts = [r for r in _trace_rows(tmp_path) if r.get("type") == "deadline_update"]
    assert facts, "deadline_update audit never reached the trace"
    assert facts[0]["after_deadline"] == 7200.0
    assert facts[0]["visibility"] == "kernel_private"


def test_run_episode_consumes_declared_task_scope_revision(
    tmp_path: Path, monkeypatch,
) -> None:
    """A declared task_scope_revision stimulus is consumed and audited end-to-end."""
    case = _write_live_case(tmp_path, events=[
        {"id": "scope", "stimulus_type": "task_scope_revision",
         "revision_id": "r-live", "new_scope": {"phase": "frozen"},
         "participant_visible_fields": {"scope": "frozen"}},
    ])
    _patch_live_adapter(monkeypatch, _adapter_events())
    config = _live_episode_config(tmp_path, case, "live-scope")
    asyncio.run(runner_module.run_episode(ROOT, config))
    facts = [r for r in _trace_rows(tmp_path) if r.get("type") == "task_scope_revision"]
    assert facts, "task_scope_revision audit never reached the trace"
    assert facts[0]["revision_id"] == "r-live"
    assert facts[0]["visibility"] == "kernel_private"


def test_run_episode_consumes_declared_dependency_graph_revision(
    tmp_path: Path, monkeypatch,
) -> None:
    """A declared dependency_graph_revision stimulus is consumed end-to-end."""
    case = _write_live_case(tmp_path, events=[
        {"id": "graph", "stimulus_type": "dependency_graph_revision",
         "revision_id": "g-live", "new_edges": {"db": ["reader", "writer"]},
         "participant_visible_fields": {"edges": ["reader", "writer"]}},
    ])
    _patch_live_adapter(monkeypatch, _adapter_events())
    config = _live_episode_config(tmp_path, case, "live-graph")
    asyncio.run(runner_module.run_episode(ROOT, config))
    facts = [
        r for r in _trace_rows(tmp_path) if r.get("type") == "dependency_graph_revision"
    ]
    assert facts, "dependency_graph_revision audit never reached the trace"
    assert facts[0]["revision_id"] == "g-live"
    assert facts[0]["visibility"] == "kernel_private"
