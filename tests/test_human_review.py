from async_rbench.human_review import (
    run_review_recommendation,
    run_review_decision,
    run_review_template,
    task_review_recommendation,
    task_review_decision,
    task_review_template,
    validate_fixed_choice_review,
)


def test_initial_screen_maps_to_complete_recommended_answer_sets() -> None:
    source = {
        "benchmark": "GAIA2",
        "manifest_solved": None,
        "codex_screen": {
            "decision": "promote_to_human",
            "trajectory_quality": "usable",
        },
    }
    task_answers = task_review_recommendation([source])
    run_answers = run_review_recommendation(source)
    assert set(task_answers) == set(task_review_template()["answers"])
    assert set(run_answers) == set(run_review_template()["answers"])
    assert task_answers["prompt_leakage_risk"] == "no"
    assert run_answers["trigger_is_independent_result"] == "yes"
    assert run_answers["failure_attribution"] == "not_failure"


def test_task_review_is_fully_computed_from_choices() -> None:
    review = task_review_template()
    for field in review["answers"]:
        review["answers"][field] = "no" if field == "prompt_leakage_risk" else "yes"
    assert task_review_decision(review) == "accept"
    review["answers"]["arrival_order_changes_plan"] = "no"
    assert task_review_decision(review) == "reject"
    review["answers"]["arrival_order_changes_plan"] = "uncertain"
    assert task_review_decision(review) == "expand_trace"


def test_run_review_rejects_benchmark_failures_and_expands_partial_traces() -> None:
    review = run_review_template()
    review["answers"].update({
        "task_version_match": "exact", "trajectory_quality": "usable",
        "trigger_is_independent_result": "yes", "evidence_boundary_valid": "yes",
        "causal_plan_change_visible": "yes", "arrival_order_observable": "yes",
        "executable_consequence_supported": "yes", "failure_attribution": "model",
    })
    assert run_review_decision(review) == "accept"
    review["answers"]["failure_attribution"] = "infrastructure"
    assert run_review_decision(review) == "reject"
    review["answers"]["failure_attribution"] = "model"
    review["answers"]["trajectory_quality"] = "partial"
    assert run_review_decision(review) == "expand_trace"
    assert validate_fixed_choice_review(review, "run") == []
