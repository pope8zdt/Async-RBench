from __future__ import annotations

import asyncio
import io
from pathlib import Path

import yaml

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
                    "id": "replay", "type": "completion_replay",
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
            {"id": "implicit-error", "type": "implicit_error_result", "result": "authority"},
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
            {"id": "implicit-error", "type": "implicit_error_result", "result": "authority"},
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
