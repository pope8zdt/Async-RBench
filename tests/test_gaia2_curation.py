from __future__ import annotations

import json

from async_rbench.gaia2_curation import build_gaia2_review_records
from async_rbench.simple_review import (
    audit_paired_reviews, build_blind_calibration_batch,
    simulate_paired_calibration_reviews,
    validate_simple_review_record,
)


def _row(with_causal_bridge: bool = True) -> dict:
    prior_id = "OracleEvent-AGENT-prior"
    env_id = "Event-ENV-late"
    affected_dependencies = [env_id] if with_causal_bridge else [prior_id]
    return {
        "id": "row-1", "scenario_id": "scenario-1", "split": "validation",
        "category": "adaptability",
        "data": json.dumps({
            "metadata": {"definition": {"scenario_id": "scenario-1"}},
            "events": [
                {
                    "class_name": "Event", "event_type": "USER", "event_id": "user-1",
                    "dependencies": [], "action": {"app": "UI", "function": "message", "args": [
                        {"name": "content", "value": "Book a ride and adapt if the date changes."}
                    ]},
                },
                {
                    "class_name": "OracleEvent", "event_type": "AGENT", "event_id": prior_id,
                    "dependencies": ["user-1"], "action": {"app": "Cabs", "function": "order", "args": []},
                },
                {
                    "class_name": "Event", "event_type": "ENV", "event_id": env_id,
                    "dependencies": [prior_id], "action": {"app": "Mail", "function": "reply", "args": [
                        {"name": "content", "value": "The arrival date changed."}
                    ]},
                },
                {
                    "class_name": "OracleEvent", "event_type": "AGENT", "event_id": "agent-after",
                    "dependencies": affected_dependencies,
                    "action": {"app": "Cabs", "function": "reschedule", "args": []},
                },
            ],
        }),
    }


def test_gaia2_causal_bridge_becomes_a_blind_review_record() -> None:
    records, mapping = build_gaia2_review_records([_row()])
    assert len(records) == len(mapping) == 1
    assert records[0]["schema_version"] == "3"
    assert records[0]["source"]["benchmark"] == "dynamic-environment"
    assert records[0]["task_goal"].startswith("Book a ride")
    assert validate_simple_review_record(records[0]) == []
    assert mapping[0]["scenario_id"] == "scenario-1"
    assert mapping[0]["late_event_id"] == "Event-ENV-late"
    public = json.dumps(records[0], ensure_ascii=False)
    assert "OracleEvent" not in public
    assert "Event-ENV" not in public
    assert records[0]["evidence_card"]["prior_work"]["excerpts"][0]["step_id"] == "步骤1"


def test_gaia2_without_prior_env_affected_bridge_is_rejected() -> None:
    records, mapping = build_gaia2_review_records([_row(with_causal_bridge=False)])
    assert records == []
    assert mapping == []


def test_calibration_batch_blinds_and_stably_mixes_strata() -> None:
    candidate, _ = build_gaia2_review_records([_row()])
    control = json.loads(json.dumps(candidate))
    control[0]["review_id"] = "control-source-id"
    control[0]["source"]["benchmark"] = "revealing-benchmark"
    first, first_map = build_blind_calibration_batch(
        candidate, control, candidate_limit=1, audit_limit=1, seed="fixed",
    )
    second, second_map = build_blind_calibration_batch(
        candidate, control, candidate_limit=1, audit_limit=1, seed="fixed",
    )
    assert first == second
    assert first_map == second_map
    assert len(first) == 2
    assert {item["source"]["benchmark"] for item in first} == {"blinded-source"}
    assert {item["stratum"] for item in first_map} == {
        "candidate", "hard_negative_control",
    }


def test_paired_review_audit_checks_controls_and_builds_no_queue_on_agreement() -> None:
    candidate, _ = build_gaia2_review_records([_row()])
    control = json.loads(json.dumps(candidate))
    control[0]["review_id"] = "control-source-id"
    records, source_map = build_blind_calibration_batch(
        candidate, control, candidate_limit=1, audit_limit=1, seed="fixed",
    )
    annotations = []
    for reviewer_id in ("R1", "R2"):
        for record in records:
            stratum = next(
                item["stratum"] for item in source_map
                if item["blind_review_id"] == record["review_id"]
            )
            independent = "no" if stratum == "hard_negative_control" else "yes"
            answers = {
                "independent_async_source": independent,
                "late_after_work_started": "yes",
                "requires_plan_change": "yes",
                "evidence_is_faithful": "yes",
            }
            annotations.append({
                "review_id": record["review_id"],
                "reviewer_id": reviewer_id,
                "answers": answers,
                "evidence_problem_parts": [],
            })
    report, queue = audit_paired_reviews(records, annotations, source_map)
    assert report["complete_two_reviewer_batch"] is True
    assert report["raw_question_agreement"] == 1.0
    assert report["hidden_control_false_positive_count"] == 0
    assert report["ready_for_case_design"] is True
    assert queue == []


def test_simulated_pair_is_disclosed_and_routes_hidden_control_out() -> None:
    candidate, _ = build_gaia2_review_records([_row()])
    control = json.loads(json.dumps(candidate))
    control[0]["review_id"] = "control-source-id"
    records, source_map = build_blind_calibration_batch(
        candidate, control, candidate_limit=1, audit_limit=1, seed="fixed",
    )
    first, second = simulate_paired_calibration_reviews(records, source_map)
    assert len(first) == len(second) == 2
    assert all(item["review_origin"] == "simulated_pipeline_validation" for item in first)
    assert all(item["simulation_disclosure"] for item in first + second)
    routes = {item["review_id"]: item["route"] for item in first}
    control_id = next(
        item["blind_review_id"] for item in source_map
        if item["stratum"] == "hard_negative_control"
    )
    assert routes[control_id] == "ordinary_sequential_observation"
