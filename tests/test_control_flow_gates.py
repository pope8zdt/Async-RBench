from __future__ import annotations

import pytest

from async_rbench.evaluation.control_flow_gates import (
    GATE_EXECUTION_MODES, dynamic_control_score, dynamic_dimension_scores,
    dynamic_decision_group_scores, evaluate_control_flow_checks,
    merge_test_point_pass_rate, semantic_task_score,
)
from async_rbench.evaluation.weighting import GATE_DYNAMIC_DIMENSIONS


def _check(gate, args, execution_modes, anchors=("anchor",)):
    return {
        "id": f"x.cf.{gate}", "gate": gate, "gate_args": args,
        "dimension": GATE_DYNAMIC_DIMENSIONS[gate],
        "execution_modes": list(execution_modes), "outcome_anchors": list(anchors),
        "critical": False, "measurement_type": "control",
        "capability_target": "async_dynamic_replanning", "relevance_tier": "direct",
    }


def _v6_check(gate, args, anchors=("anchor",)):
    check = _check(gate, args, GATE_EXECUTION_MODES[gate], anchors)
    check["requires_outcome_anchor"] = True
    return check


def _facts(**overrides):
    facts = {
        "scenario_entry": True, "scenario_constructed": True,
        "consumed_completion_ids": {"auth"},
        "authoritative_delivery": {"completion_id": "auth", "seq": 10},
        "stale_deliveries": [{"completion_id": "stale", "seq": 20}],
        "stale_retained_completion_ids": set(), "invalidating_deliveries": [],
        "final_artifacts": {}, "artifact_commits": {},
        "cancellation_opportunity_children": set(),
        "timely_cancelled_children": set(), "unnecessary_cancellation_count": 0,
        "spawned_by_id": {}, "workstream_results": {},
    }
    facts.update(overrides)
    return facts


def _commit(artifact_id, seq, lineage):
    return {"artifact_id": artifact_id, "seq": seq, "lineage_completion_ids": lineage}


def test_wait_gate_requires_no_pre_authority_commit():
    check = _check("wait_for_authority", {"artifacts": ["a"]}, GATE_EXECUTION_MODES["wait_for_authority"])
    final = _commit("a", 12, ["auth"])
    passed, _ = evaluate_control_flow_checks(
        [check], "async", _facts(final_artifacts={"a": final}, artifact_commits={"a": [final]}),
        [{"id": "anchor", "passed": True}],
    )
    assert passed[0]["status"] == "pass"
    early = _commit("a", 9, [])
    failed, _ = evaluate_control_flow_checks(
        [check], "async", _facts(final_artifacts={"a": final}, artifact_commits={"a": [early, final]}),
        [{"id": "anchor", "passed": True}],
    )
    assert failed[0]["status"] == "fail"


def test_stale_and_cancel_gates_use_evaluator_facts():
    stale = _check("reject_late_stale", {"artifacts": ["a"]}, GATE_EXECUTION_MODES["reject_late_stale"])
    contaminated = _commit("a", 21, ["stale"])
    results, _ = evaluate_control_flow_checks(
        [stale], "async",
        _facts(final_artifacts={"a": contaminated}, stale_retained_completion_ids={"stale"}),
        [{"id": "anchor", "passed": True}],
    )
    assert results[0]["status"] == "fail"

    cancel = _check("timely_cancellation", {"workstreams": ["old"]}, GATE_EXECUTION_MODES["timely_cancellation"])
    facts = _facts(
        cancellation_opportunity_children={"c1"}, timely_cancelled_children={"c1"},
        spawned_by_id={"c1": {"work_units": ["old"]}},
    )
    results, counts = evaluate_control_flow_checks(
        [cancel], "async", facts, [{"id": "anchor", "passed": True}],
    )
    assert results[0]["status"] == "pass" and counts["applicable"] == 1


def test_cancel_gate_fails_when_benchmark_created_no_real_opportunity():
    cancel = _check(
        "timely_cancellation", {"workstreams": ["old"]},
        GATE_EXECUTION_MODES["timely_cancellation"],
    )
    results, counts = evaluate_control_flow_checks(
        [cancel], "async", _facts(), [{"id": "anchor", "passed": True}],
    )
    assert counts["applicable"] == 1
    assert results[0]["status"] == "fail"
    assert "no progressed superseded child" in results[0]["reasons"][0]


def test_rederive_and_x_merge_respect_applicability():
    check = _check("rederive_from_authority", {"artifacts": ["a"]}, GATE_EXECUTION_MODES["rederive_from_authority"])
    final = _commit("a", 12, ["auth"])
    results, _ = evaluate_control_flow_checks(
        [check], "async", _facts(
            final_artifacts={"a": final},
            invalidating_deliveries=[{"seq": 10, "invalidates_artifacts": ["a"]}],
        ), [{"id": "anchor", "passed": True}],
    )
    # The outcome anchor no longer gates the process point: a passing trace gate
    # with a failing anchor is still a process PASS (no double penalty).
    independent, _ = evaluate_control_flow_checks(
        [check], "async", _facts(
            final_artifacts={"a": final},
            invalidating_deliveries=[{"seq": 10, "invalidates_artifacts": ["a"]}],
        ), [{"id": "anchor", "passed": False}],
    )
    assert independent[0]["anchor_passed"] is False
    assert independent[0]["gate_passed"] is True
    assert independent[0]["status"] == "pass"
    assert results[0]["status"] == "pass"
    semantic = [{"id": str(i), "passed": i < 20} for i in range(24)]
    # The registry fixes this process point at direct research relevance (3).
    assert merge_test_point_pass_rate(semantic, None, results) == pytest.approx(29 / 30)

    not_applicable, counts = evaluate_control_flow_checks(
        [check], "linear", _facts(), [{"id": "anchor", "passed": True}],
    )
    assert not_applicable[0]["status"] == "not_applicable"
    assert counts["applicable"] == 0


def test_process_point_passes_independently_of_outcome_anchor():
    # Process right + outcome wrong: reject_late_stale passes on the pure trace
    # gate while the anchored semantic point fails. Independence means the two
    # dimensions do not double-penalise the same failure.
    check = _check("reject_late_stale", {"artifacts": ["a"]}, GATE_EXECUTION_MODES["reject_late_stale"])
    final = _commit("a", 12, ["auth"])
    results, counts = evaluate_control_flow_checks(
        [check], "async",
        _facts(final_artifacts={"a": final}, stale_retained_completion_ids=set()),
        [{"id": "anchor", "passed": False}],
    )
    assert results[0]["anchor_passed"] is False
    assert results[0]["gate_passed"] is True
    assert results[0]["status"] == "pass"
    assert counts["passed"] == 1 and counts["applicable"] == 1


def test_generic_authority_and_selective_replan_gates_cover_v8_dimensions():
    resolve = _check(
        "resolve_authority", {"artifacts": ["affected"]},
        GATE_EXECUTION_MODES["resolve_authority"],
    )
    replan = _check(
        "selective_replan",
        {"artifacts": ["affected"], "preserve_artifacts": ["stable"]},
        GATE_EXECUTION_MODES["selective_replan"],
    )
    affected = _commit("affected", 12, ["auth"])
    stable = _commit("stable", 8, [])
    facts = _facts(
        final_artifacts={"affected": affected, "stable": stable},
        artifact_commits={"affected": [affected], "stable": [stable]},
        invalidating_deliveries=[
            {"seq": 10, "invalidates_artifacts": ["affected"]},
        ],
    )
    results, counts = evaluate_control_flow_checks(
        [resolve, replan], "async", facts,
        [{"id": "anchor", "passed": True}],
    )
    assert [item["status"] for item in results] == ["pass", "pass"]
    assert [item["dimension"] for item in results] == [
        "state_revision", "plan_revision",
    ]
    assert counts["passed"] == counts["applicable"] == 2

    unnecessary = _commit("stable", 13, [])
    failed, _ = evaluate_control_flow_checks(
        [replan], "async",
        {**facts, "artifact_commits": {"affected": [affected], "stable": [stable, unnecessary]}},
        [{"id": "anchor", "passed": True}],
    )
    assert failed[0]["status"] == "fail"
    assert "unnecessarily recommitted" in failed[0]["reasons"][0]


def test_merge_test_point_pass_rate_uses_frozen_relevance_weights():
    semantic = [
        {"id": "s1", "passed": True},
        {"id": "s2", "passed": False},
    ]
    registry = {
        "checks": [
            {"id": "s1", "category": "stale_exclusion", "relevance_tier": "critical"},
            {"id": "s2", "category": "lineage_reverification", "relevance_tier": "base"},
        ]
    }
    control_flow = [
        {"id": "c1", "gate": "reject_late_stale", "status": "pass", "relevance_tier": "critical"},
        {"id": "c2", "gate": "timely_cancellation", "status": "fail", "relevance_tier": "direct"},
    ]
    assert merge_test_point_pass_rate(
        semantic, None, control_flow, semantic_registry=registry,
    ) == 0.56
    assert dynamic_control_score(control_flow) == 0.5
    assert dynamic_dimension_scores(control_flow) == {
        "state_revision": 1.0, "plan_revision": 0.0,
    }


def test_v6_wait_requires_consumption_before_final_commit_and_local_outcome():
    check = _v6_check("wait_for_authority", {"artifacts": ["a"]})
    final = _commit("a", 14, ["auth"])
    facts = _facts(
        final_artifacts={"a": final}, artifact_commits={"a": [final]},
        consumption_by_completion_id={"auth": {"seq": 12}},
    )
    passed, _ = evaluate_control_flow_checks(
        [check], "async", facts, [{"id": "anchor", "passed": True}],
    )
    assert passed[0]["process_status"] == passed[0]["status"] == "pass"

    outcome_failed, _ = evaluate_control_flow_checks(
        [check], "async", facts, [{"id": "anchor", "passed": False}],
    )
    assert outcome_failed[0]["process_status"] == "pass"
    assert outcome_failed[0]["status"] == "fail"


def test_v6_selective_replan_requires_real_pre_and_post_event_states():
    check = _v6_check(
        "selective_replan",
        {"artifacts": ["affected"], "preserve_artifacts": ["stable"]},
    )
    before = _commit("affected", 8, [])
    after = _commit("affected", 12, ["auth"])
    stable = _commit("stable", 7, [])
    facts = _facts(
        final_artifacts={"affected": after, "stable": stable},
        artifact_commits={"affected": [before, after], "stable": [stable]},
        invalidating_deliveries=[{"seq": 10, "invalidates_artifacts": ["affected"]}],
    )
    passed, _ = evaluate_control_flow_checks(
        [check], "async", facts, [{"id": "anchor", "passed": True}],
    )
    assert passed[0]["status"] == "pass"

    no_provisional, _ = evaluate_control_flow_checks(
        [check], "async",
        {**facts, "artifact_commits": {"affected": [after], "stable": [stable]}},
        [{"id": "anchor", "passed": True}],
    )
    assert no_provisional[0]["status"] == "fail"
    assert "no pre-invalidation state" in no_provisional[0]["reasons"][0]


def test_v6_closure_requires_post_authority_reverification():
    check = _v6_check("rederive_from_authority", {"artifacts": ["a"]})
    final = _commit("a", 12, ["auth"])
    facts = _facts(
        final_artifacts={"a": final},
        invalidating_deliveries=[{"seq": 10, "invalidates_artifacts": ["a"]}],
    )
    failed, _ = evaluate_control_flow_checks(
        [check], "async", facts, [{"id": "anchor", "passed": True}],
    )
    assert failed[0]["status"] == "fail"
    assert "post-authority verification" in failed[0]["reasons"][0]
    passed, _ = evaluate_control_flow_checks(
        [check], "async", {**facts, "post_authority_verification": True},
        [{"id": "anchor", "passed": True}],
    )
    assert passed[0]["status"] == "pass"


def test_v7_dynamic_score_macros_causal_groups_not_stage_tags():
    results = [
        {"id": "a", "status": "pass", "decision_group": "classify", "dimension": "event_intake", "relevance_tier": "direct"},
        {"id": "b", "status": "fail", "decision_group": "close", "dimension": "closure", "relevance_tier": "direct"},
        {"id": "c", "status": "pass", "decision_group": "close", "dimension": "closure", "relevance_tier": "direct"},
    ]
    assert dynamic_decision_group_scores(results) == {"classify": 1.0, "close": 0.5}
    assert dynamic_control_score(results) == 0.75


def test_v7_semantic_score_macros_requirement_groups():
    registry = {"checks": [
        {"id": "a1", "requirement_group": "a", "relevance_tier": "direct"},
        {"id": "a2", "requirement_group": "a", "relevance_tier": "direct"},
        {"id": "b1", "requirement_group": "b", "relevance_tier": "direct"},
    ]}
    results = [
        {"id": "a1", "passed": True}, {"id": "a2", "passed": True},
        {"id": "b1", "passed": False},
    ]
    assert semantic_task_score(results, None, registry) == 0.5
