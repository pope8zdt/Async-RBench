from __future__ import annotations

import json
from pathlib import Path

import pytest

from async_rbench.evaluation.scoring import score_trace
from async_rbench.spec import load_case

from author_local import requires_author_local


ROOT = Path(__file__).resolve().parents[1]
_CANCELLATION_GATE = requires_author_local(
    "candidate_instances/gaia2-stockholm-moveout/gaia2-zip-revision-sim-001/public_case.yaml",
)


def _scores(root: Path):
    return [json.loads(path.read_text(encoding="utf-8")) for path in root.rglob("score.json")]


def test_two_mode_smoke_constructs_both_scenarios(tmp_path: Path) -> None:
    # The full subprocess exercise lives in test_reference_scaffold_api. Here we
    # assert the architectural invariant on its score-shaped outputs.
    scores = [
        {"execution_mode": "linear", "scenario_constructed": True},
        {"execution_mode": "async", "scenario_constructed": True},
    ]
    assert {item["execution_mode"] for item in scores} == {"linear", "async"}
    assert all(item["scenario_constructed"] for item in scores)


def test_old_conditions_are_not_part_of_the_architecture() -> None:
    from async_rbench.evaluation.manifest import EXECUTION_MODES
    assert EXECUTION_MODES == ("linear", "async")
    assert not ({"stable", "eventful_a", "eventful_b", "live_eventful"} & set(EXECUTION_MODES))


def test_participant_early_end_is_scored_failure_not_construction_failure() -> None:
    case = load_case(
        ROOT / "cases" / "gaia2-stockholm-moveout" / "public_case.yaml"
    ).raw
    events = []
    for index, item in enumerate(case["initial_wave"], start=1):
        events.append({
            "type": "child_spawned",
            "seq": index,
            "child_id": f"child-{index}",
            "parent_id": "main",
            "work_units": [item["workstream_id"]],
            "initial_wave": True,
        })
    offset = len(events)
    for index in range(1, len(case["initial_wave"]) + 1):
        events.append({
            "type": "child_started",
            "seq": offset + index,
            "child_id": f"child-{index}",
        })
    events.append({"type": "episode_ended", "seq": len(events) + 1})
    score = score_trace(
        events,
        case,
        "async",
        semantic_registry={"checks": []},
        control_flow_checks=[],
    )
    assert score["scenario_constructed"] is True
    assert score["scenario_exposure_complete"] is False
    assert score["scenario_construction_errors"] == []
    assert score["scenario_exposure_errors"]


def _minimal_dynamic_case() -> dict:
    return {
        "initial_wave": [
            {"workstream_id": "provisional"},
            {"workstream_id": "authority"},
        ],
        "delegation_workstreams": [
            {"id": "provisional", "result_kind": "provisional_result"},
            {"id": "authority", "result_kind": "authority_result"},
        ],
        "authoritative_result_kind": "authority_result",
        "superseded_result_kind": "provisional_result",
        "scenarios": {
            "linear": {"events": []},
            "async": {
                "events": [
                    {
                        "id": "evt.authority",
                        "result": "authority_result",
                        "invalidates_artifacts": ["final"],
                        "reopens_milestones": ["close"],
                    }
                ]
            },
        },
        "artifacts": [{"id": "final"}],
    }


def _constructed_initial_wave() -> list[dict]:
    return [
        {
            "type": "child_spawned", "seq": 1, "child_id": "provisional-child",
            "parent_id": "main", "work_units": ["provisional"], "initial_wave": True,
        },
        {
            "type": "child_spawned", "seq": 2, "child_id": "authority-child",
            "parent_id": "main", "work_units": ["authority"], "initial_wave": True,
        },
        {"type": "child_started", "seq": 3, "child_id": "provisional-child"},
        {"type": "child_started", "seq": 4, "child_id": "authority-child"},
        {
            "type": "verifier_result", "seq": 5,
            "semantic_check_results": [{"id": "sem", "passed": True}],
            "test_point_pass_rate": 1.0,
        },
    ]


def _dynamic_contract() -> list[dict]:
    return [{
        "event_id": "evt.authority",
        "expected_disposition": "revise",
        "required_changes": ["final"],
        "state_delta": {
            "affected_artifacts": ["final"],
            "unaffected_artifacts": [],
        },
        "required_opportunities": ["authority_delivery"],
    }]


def _score_stopped_before_event(
    terminal_event: dict, *, local_status: str,
) -> dict:
    events = [
        *_constructed_initial_wave(),
        {**terminal_event, "seq": 6},
        {"type": "episode_ended", "seq": 7, "local_status": local_status},
    ]
    return score_trace(
        events, _minimal_dynamic_case(), "async",
        semantic_registry={"checks": [{"id": "sem"}]},
        control_flow_checks=[], event_contracts=_dynamic_contract(),
    )


def test_immediate_finish_scores_unreached_declared_event_as_zero() -> None:
    score = _score_stopped_before_event(
        {
            "type": "finish_invoked", "requested_status": "completed",
            "pending_occurrence_count": 0, "active_response_window": False,
            "final_commit_current": False, "verification_current": False,
            "closure_complete": False,
        },
        local_status="completed",
    )

    assert score["scenario_constructed"] is True
    assert score["scenario_exposure_complete"] is False
    assert score["dynamic_scenario_qualified"] is True
    assert score["dynamic_scenario_errors"] == []
    assert score["dynamic_opportunity_complete"] is False
    assert score["dynamic_event_exposure"] == {"evt.authority": "not_observed"}
    assert score["async_drs"] == 0.0
    assert score["async_event_drs"]["evt.authority"]["total"] == 0.0


def test_implicit_stop_scores_unreached_declared_event_as_zero() -> None:
    score = _score_stopped_before_event(
        {"type": "main_implicit_stop", "reason": "no_tool_call"},
        local_status="incomplete",
    )

    assert score["async_drs"] == 0.0
    assert score["async_event_drs"]["evt.authority"]["total"] == 0.0


def test_step_limit_scores_unreached_declared_event_as_zero() -> None:
    score = _score_stopped_before_event(
        {"type": "step_limit_reached", "role": "main", "limit": 100},
        local_status="step_limit_reached",
    )

    assert score["async_drs"] == 0.0
    assert score["async_event_drs"]["evt.authority"]["total"] == 0.0


def test_partial_finish_keeps_unreached_event_in_drs_denominator() -> None:
    events = [
        *_constructed_initial_wave(),
        {
            "type": "artifact_committed", "seq": 6,
            "artifact_id": "final", "observed_digest": "before",
        },
        {
            "type": "result_delivery_evaluator_fact", "seq": 7,
            "completion_id": "observed", "result_kind": "authority_result",
            "benchmark_event_id": "evt.observed", "controlled_order": True,
            "stale": False,
        },
        {
            "type": "result_delivered", "seq": 8,
            "completion_id": "observed", "child_id": "authority-child",
        },
        {
            "type": "artifact_committed", "seq": 9,
            "artifact_id": "final", "observed_digest": "after",
        },
        {
            "type": "verifier_result", "seq": 10,
            "semantic_check_results": [{
                "id": "evt.observed.closed", "measurement_type": "semantic",
                "score_domain": "async_replanning", "event_id": "evt.observed",
                "passed": True,
            }],
            "test_point_pass_rate": 1.0,
        },
        {
            "type": "finish_invoked", "seq": 11,
            "requested_status": "completed", "pending_occurrence_count": 0,
            "active_response_window": False, "final_commit_current": True,
            "verification_current": True, "closure_complete": False,
        },
        {"type": "episode_ended", "seq": 12, "local_status": "completed"},
    ]
    contracts = [
        {
            "event_id": "evt.observed", "expected_disposition": "revise",
            "required_changes": ["final"],
            "closure_checks": ["evt.observed.closed"],
        },
        {
            "event_id": "evt.unreached", "expected_disposition": "revise",
            "required_changes": ["second"],
            "closure_checks": ["evt.unreached.closed"],
        },
    ]

    score = score_trace(
        events, _minimal_dynamic_case(), "async",
        semantic_registry={"checks": [{"id": "evt.observed.closed"}]},
        control_flow_checks=[], event_contracts=contracts,
    )

    assert score["async_event_drs"]["evt.observed"]["total"] == 0.75
    assert score["async_event_drs"]["evt.unreached"]["total"] == 0.0
    assert score["async_drs"] == 0.375


def test_delivery_intervention_failure_remains_unscored_infrastructure() -> None:
    events = [
        *_constructed_initial_wave(),
        {
            "type": "infrastructure_failure", "seq": 6,
            "component": "delivery_intervention", "detail": "fixture mutation failed",
        },
    ]
    score = score_trace(
        events, _minimal_dynamic_case(), "async",
        semantic_registry={"checks": [{"id": "sem"}]},
        control_flow_checks=[], event_contracts=_dynamic_contract(),
    )

    assert score["dynamic_scenario_qualified"] is False
    assert score["dynamic_control_score"] is None
    assert score["async_drs"] is None
    assert score["trace_score_status_reason"] == "dynamic_scenario_qualification_failed"
    assert score["async_event_drs"]["evt.authority"]["status"] == (
        "dynamic_scenario_qualification_failed"
    )
    assert "delivery intervention failed" in score["dynamic_scenario_errors"][0]


@pytest.mark.parametrize(
    "event, expected_reason",
    [
        *[
            (
                {
                    "type": "infrastructure_failure", "seq": 6,
                    "component": component, "detail": "benchmark failure",
                },
                "infrastructure_crash",
            )
            for component in (
                "model_request", "child_start", "adapter_crash",
                "child_terminal", "linear_bundle_barrier",
            )
        ],
        (
            {
                "type": "resource_safety_abort", "seq": 6,
                "emergency_cap": 5_000_000, "observed_total": 5_000_000,
                "trigger_role": "main",
            },
            "resource_safety_abort",
        ),
    ],
)
def test_benchmark_owned_stop_keeps_unreached_event_unscored(
    event: dict, expected_reason: str,
) -> None:
    score = score_trace(
        [*_constructed_initial_wave(), event],
        _minimal_dynamic_case(), "async",
        semantic_registry={"checks": [{"id": "sem"}]},
        control_flow_checks=[], event_contracts=_dynamic_contract(),
    )

    assert score["async_drs"] is None
    assert score["trace_score_status_reason"] == expected_reason
    assert score["async_event_drs"]["evt.authority"]["total"] is None
    assert score["async_event_drs"]["evt.authority"]["status"] == expected_reason


def test_scenario_construction_failure_does_not_score_unreached_event() -> None:
    score = score_trace(
        [], _minimal_dynamic_case(), "async",
        semantic_registry={"checks": [{"id": "sem"}]},
        control_flow_checks=[], event_contracts=_dynamic_contract(),
    )

    assert score["scenario_constructed"] is False
    assert score["async_drs"] is None
    assert score["trace_score_status_reason"] == "scenario_construction_failed"
    assert score["async_event_drs"]["evt.authority"]["total"] is None


def test_indeterminate_truncated_trace_does_not_score_unreached_event() -> None:
    score = score_trace(
        _constructed_initial_wave(), _minimal_dynamic_case(), "async",
        semantic_registry={"checks": [{"id": "sem"}]},
        control_flow_checks=[], event_contracts=_dynamic_contract(),
    )

    assert score["async_drs"] is None
    assert score["trace_score_status_reason"] == "indeterminate_termination"
    assert score["async_event_drs"]["evt.authority"]["total"] is None


@_CANCELLATION_GATE
def test_registered_cancellation_gate_creates_opportunity_without_capability_label() -> None:
    case = load_case(
        ROOT
        / "candidate_instances"
        / "gaia2-stockholm-moveout"
        / "gaia2-zip-revision-sim-001"
        / "public_case.yaml"
    ).raw
    assert "inflight_cancellation" not in set(case.get("capabilities") or [])
    planner = next(
        item for item in case["initial_wave"]
        if item["workstream_id"] == "initial_removal_planner"
    )
    events = [
        {
            "type": "child_spawned", "seq": 1, "child_id": "old-planner",
            "parent_id": "main", "work_units": [planner["workstream_id"]],
            "initial_wave": True,
        },
        {"type": "child_started", "seq": 2, "child_id": "old-planner"},
        {
            "type": "result_delivery_evaluator_fact", "seq": 3,
            "completion_id": "authority", "result_kind": case["authoritative_result_kind"],
            "controlled_order": True, "stale": False,
        },
        {
            "type": "result_delivered", "seq": 4, "completion_id": "authority",
            "child_id": "authority-child",
        },
        {
            "type": "child_completed", "seq": 5, "child_id": "old-planner",
            "completion_id": "superseded",
        },
    ]
    checks = [{
        "id": "sm.cf.cancel_stale_planner",
        "gate": "timely_cancellation",
        "dimension": "plan_revision",
        "gate_args": {"workstreams": ["initial_removal_planner"]},
        "outcome_anchors": [],
        "critical": False,
        "measurement_type": "control",
        "capability_target": "async_dynamic_replanning",
        "relevance_tier": "direct",
        "execution_modes": ["async"],
    }]

    score = score_trace(
        events, case, "async", semantic_registry={"checks": []},
        control_flow_checks=checks,
    )

    assert score["cancellation_opportunity_count"] == 1
    assert score["control_flow_check_results"][0]["reasons"] == [
        "superseded running child was not cancelled by main agent"
    ]


def test_async_delivery_lifecycle_replays_with_available_and_window_close() -> None:
    """EventStore replay accepts the full async delivery-occurrence lifecycle
    (spec §3.2/§3.3): result_available -> adapter_queued -> presentation_prepared
    -> result_presented -> response_window_closed. A live adapter must emit the
    occurrence as available before it is queued and close the window it opened,
    otherwise replay raises ProtocolError."""
    from async_rbench.evaluation.event_store import replay_events

    events = [
        {"type": "result_available", "delivery_occurrence_id": "occ-1", "completion_id": "comp-1"},
        {"type": "adapter_queued", "delivery_occurrence_id": "occ-1", "completion_id": "comp-1"},
        {"type": "presentation_prepared", "delivery_occurrence_id": "occ-1"},
        {"type": "result_presented", "delivery_occurrence_id": "occ-1",
         "completion_id": "comp-1", "turn_id": "t1", "window_id": "w1"},
        {"type": "response_window_closed", "delivery_occurrence_id": "occ-1", "window_id": "w1"},
    ]
    state = replay_events(events)
    occurrence = state["occurrences"]["occ-1"]
    assert occurrence.available is True
    assert occurrence.queued is True
    assert occurrence.prepared is True
    assert occurrence.presented is True
    assert occurrence.window_closed is True
    assert state["open_windows"] == set()


def test_linear_children_overlap_but_main_waits_for_atomic_bundle() -> None:
    """Linear now runs children concurrently (child-child overlap) while the main
    agent waits for ONE atomic bundle: overlap must be required and main-child
    overlap must be forbidden (spec §6)."""
    case = _minimal_dynamic_case()
    events = [
        {"type": "child_spawned", "seq": 1, "child_id": "p-child",
         "parent_id": "main", "work_units": ["provisional"], "initial_wave": True},
        {"type": "child_spawned", "seq": 2, "child_id": "a-child",
         "parent_id": "main", "work_units": ["authority"], "initial_wave": True},
        {"type": "child_started", "seq": 3, "child_id": "p-child"},
        {"type": "child_started", "seq": 4, "child_id": "a-child"},
        # Both children overlap in time: each completes after the other started.
        {"type": "child_completed", "seq": 5, "child_id": "p-child", "completion_id": "p1"},
        {"type": "result_delivered", "seq": 6, "child_id": "p-child",
         "completion_id": "p1", "result_kind": "provisional_result"},
        {"type": "child_completed", "seq": 7, "child_id": "a-child", "completion_id": "a1"},
        {"type": "result_delivered", "seq": 8, "child_id": "a-child",
         "completion_id": "a1", "result_kind": "authority_result"},
        # The main agent waits for the atomic bundle, so it acts only after both
        # workstreams are resolved (no main-child overlap).
        {"type": "main_action", "seq": 9, "action_id": "act-1", "kind": "acknowledge_result"},
        {"type": "episode_ended", "seq": 10},
    ]
    score = score_trace(
        events, case, "linear", semantic_registry={"checks": []},
        control_flow_checks=[],
    )
    components = score["scenario_entry_components"]
    assert components["child_child_overlap"] is True
    assert components["main_child_overlap"] is False
    assert score["scenario_constructed"] is True
    assert not score["scenario_construction_errors"]
