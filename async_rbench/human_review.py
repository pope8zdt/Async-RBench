"""Fixed-choice human review contracts and deterministic dispositions."""

from __future__ import annotations

from typing import Any


YES_NO = ("pending", "yes", "no", "uncertain")
TASK_REVIEW_QUESTIONS = {
    "independent_result_producer": YES_NO,
    "affected_work_started_before_arrival": YES_NO,
    "arrival_order_changes_plan": YES_NO,
    "plan_change_required": YES_NO,
    "executable_consequence_observable": YES_NO,
    "source_semantics_preserved": YES_NO,
    "environment_reproducible": YES_NO,
    "prompt_leakage_risk": YES_NO,
}
RUN_REVIEW_QUESTIONS = {
    "task_version_match": ("pending", "exact", "instruction_only", "mismatch", "unknown"),
    "trajectory_quality": ("pending", "usable", "partial", "unusable"),
    "trigger_is_independent_result": YES_NO,
    "evidence_boundary_valid": YES_NO,
    "causal_plan_change_visible": YES_NO,
    "arrival_order_observable": YES_NO,
    "executable_consequence_supported": YES_NO,
    "failure_attribution": (
        "pending", "model", "benchmark", "infrastructure", "not_failure", "uncertain",
    ),
}


def task_review_template() -> dict[str, Any]:
    return {
        "schema_version": "fixed-choice-v1",
        "answers": {field: "pending" for field in TASK_REVIEW_QUESTIONS},
        "computed_decision": "pending",
    }


def run_review_template() -> dict[str, Any]:
    return {
        "schema_version": "fixed-choice-v1",
        "answers": {field: "pending" for field in RUN_REVIEW_QUESTIONS},
        "computed_decision": "pending",
    }


def task_review_recommendation(source_runs: list[dict[str, Any]]) -> dict[str, str]:
    """Map the initial screen for a task to reviewer-editable default choices."""
    screens = [row.get("codex_screen") or {} for row in source_runs]
    if any(screen.get("decision") == "promote_to_human" for screen in screens):
        return {
            "independent_result_producer": "yes",
            "affected_work_started_before_arrival": "yes",
            "arrival_order_changes_plan": "yes",
            "plan_change_required": "yes",
            "executable_consequence_observable": "yes",
            "source_semantics_preserved": "yes",
            "environment_reproducible": "yes",
            "prompt_leakage_risk": "no",
        }
    benchmarks = {str(row.get("benchmark") or "") for row in source_runs}
    return {
        "independent_result_producer": "uncertain",
        "affected_work_started_before_arrival": "uncertain",
        "arrival_order_changes_plan": "uncertain",
        "plan_change_required": "uncertain",
        "executable_consequence_observable": "uncertain",
        "source_semantics_preserved": "yes",
        "environment_reproducible": "yes" if benchmarks <= {"OSWorld"} else "uncertain",
        "prompt_leakage_risk": "no",
    }


def run_review_recommendation(source: dict[str, Any]) -> dict[str, str]:
    """Map one run's initial screen to reviewer-editable default choices."""
    screen = source.get("codex_screen") or {}
    direct = screen.get("decision") == "promote_to_human"
    quality = str(screen.get("trajectory_quality") or "")
    if quality not in {"usable", "partial", "unusable"}:
        quality = "usable"
    solved = source.get("manifest_solved")
    attribution = "not_failure" if solved is not False else "model"
    if source.get("benchmark") in {"GAIA2", "SentinelBench"}:
        attribution = "not_failure"
    boundary = "yes" if direct else "uncertain"
    return {
        "task_version_match": "exact",
        "trajectory_quality": quality,
        "trigger_is_independent_result": boundary,
        "evidence_boundary_valid": boundary,
        "causal_plan_change_visible": boundary,
        "arrival_order_observable": boundary,
        "executable_consequence_supported": boundary,
        "failure_attribution": attribution,
    }


def task_review_decision(review: dict[str, Any]) -> str:
    answers = review.get("answers") or {}
    if any(answers.get(field) == "pending" for field in TASK_REVIEW_QUESTIONS):
        return "pending"
    positive = (
        "independent_result_producer", "affected_work_started_before_arrival",
        "arrival_order_changes_plan", "plan_change_required",
        "executable_consequence_observable", "source_semantics_preserved",
        "environment_reproducible",
    )
    if any(answers.get(field) == "no" for field in positive):
        return "reject"
    if answers.get("prompt_leakage_risk") == "yes":
        return "reject"
    if any(answers.get(field) == "uncertain" for field in TASK_REVIEW_QUESTIONS):
        return "expand_trace"
    return "accept"


def run_review_decision(review: dict[str, Any]) -> str:
    answers = review.get("answers") or {}
    if any(answers.get(field) == "pending" for field in RUN_REVIEW_QUESTIONS):
        return "pending"
    if answers.get("task_version_match") == "mismatch":
        return "reject"
    if answers.get("trajectory_quality") == "unusable":
        return "reject"
    positive = (
        "trigger_is_independent_result", "evidence_boundary_valid",
        "causal_plan_change_visible", "arrival_order_observable",
        "executable_consequence_supported",
    )
    if any(answers.get(field) == "no" for field in positive):
        return "reject"
    if answers.get("failure_attribution") in {"benchmark", "infrastructure"}:
        return "reject"
    uncertain = (
        answers.get("task_version_match") in {"instruction_only", "unknown"}
        or answers.get("trajectory_quality") == "partial"
        or answers.get("failure_attribution") == "uncertain"
        or any(answers.get(field) == "uncertain" for field in positive)
    )
    return "expand_trace" if uncertain else "accept"


def validate_fixed_choice_review(review: dict[str, Any], kind: str) -> list[str]:
    catalog = TASK_REVIEW_QUESTIONS if kind == "task" else RUN_REVIEW_QUESTIONS
    decision_fn = task_review_decision if kind == "task" else run_review_decision
    answers = review.get("answers") if isinstance(review, dict) else None
    if not isinstance(answers, dict):
        return ["answers must be an object"]
    errors = []
    if set(answers) != set(catalog):
        errors.append("answers must contain exactly the fixed-choice question fields")
    for field, choices in catalog.items():
        if answers.get(field) not in choices:
            errors.append(f"{field} must be one of {list(choices)!r}")
    computed = decision_fn(review)
    if review.get("computed_decision") not in {computed, "pending"}:
        errors.append("computed_decision does not match fixed-choice answers")
    return errors
