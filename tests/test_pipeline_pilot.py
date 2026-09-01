from async_rbench.pipeline_pilot import (
    promotion_eligibility, simulate_review_annotations, validate_screening_report,
)


def _record(review_id: str) -> dict:
    excerpt = {"step_id": "1", "actor": "tool", "text": "evidence"}
    return {
        "schema_version": "2",
        "review_id": review_id,
        "source": {"benchmark": "bench", "task_id": "task", "trajectory_id": review_id},
        "task_goal": "complete the task",
        "evidence_card": {
            "prior_work": {"summary": "prior", "excerpts": [excerpt]},
            "late_information": {"summary": "late", "excerpts": [excerpt]},
            "affected_action": {"summary": "affected", "excerpts": [excerpt]},
            "expanded_context": [],
        },
    }


def test_simulated_answers_are_disclosed_and_exercise_both_routes() -> None:
    annotations = simulate_review_annotations(
        [_record("candidate"), _record("negative")], {"candidate"}, "SIM-01",
    )
    assert [item["route"] for item in annotations] == [
        "candidate_confirmed", "no_replanning_need",
    ]
    assert all(item["review_origin"] == "simulated_pipeline_validation" for item in annotations)
    assert all(item["review_seconds"] is None for item in annotations)


def test_simulated_candidate_is_never_promotion_eligible() -> None:
    eligible, error = promotion_eligibility({
        "pilot_validation": {"simulated_review": True, "promotion_eligible": False},
    })
    assert eligible is False
    assert "cannot be promoted" in str(error)


def test_screening_report_requires_count_conservation() -> None:
    report = {
        "source": {"trajectory_count": 10},
        "normalization": {"prepared_count": 8, "failure_count": 2},
        "strict_screen": {
            "screened_count": 7, "screening_failure_count": 1,
            "candidate_decision_count": 2, "reject_reason_counts": {"ordinary": 5},
        },
        "human_review": {"main_count": 1, "boundary_count": 1},
    }
    assert validate_screening_report(report) == []
    report["strict_screen"]["screened_count"] = 6
    assert "prepared count does not equal screened plus screening failures" in validate_screening_report(report)
