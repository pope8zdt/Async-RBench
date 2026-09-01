"""Mode-neutral task-outcome scoring for capsule experiments.

The leaderboard score must measure the same semantic outcome in ReAct,
linear, and async executions.  Mode-specific process points are intentionally
kept out of this scorer and are reported as diagnostics by the runner.
"""

from __future__ import annotations

from typing import Any

from .authoritative_capsule import canonical_sha256


def _point(
    point_id: str,
    description: str,
    weight: float,
    passed: bool,
    **metadata: Any,
) -> dict[str, Any]:
    return {
        "id": point_id,
        "description": description,
        "weight": weight,
        "passed": bool(passed),
        **metadata,
    }


def _result(case_id: str, points: list[dict[str, Any]]) -> dict[str, Any]:
    score = sum(float(item["weight"]) for item in points if item["passed"])
    return {
        "case_id": case_id,
        "score": round(score, 8),
        "test_point_count": len(points),
        "passed_point_count": sum(bool(item["passed"]) for item in points),
        "unscored_point_count": 0,
        "test_points": points,
    }


def _required_points(
    public: dict[str, Any], expected: dict[str, Any], completed: set[str],
) -> list[dict[str, Any]]:
    required = [str(value) for value in expected.get("affected_work_ids") or []]
    descriptions = {
        str(item["id"]): str(item.get("description") or "")
        for item in (public.get("causal_record") or {}).get("affected_work") or []
    }
    per_action = 0.70 / len(required) if required else 0.70
    if not required:
        return [_point(
            "required_outcome_vacuous",
            "The task defines no event-affected action.",
            0.70,
            True,
        )]
    return [
        _point(
            f"required_action_{index:02d}",
            descriptions.get(action_id) or f"Complete required action {index}",
            per_action,
            action_id in completed,
            action_id=action_id,
        )
        for index, action_id in enumerate(required, 1)
    ]


def score_capsule_task_outcome(
    public: dict[str, Any], expected: dict[str, Any], submission: dict[str, Any],
) -> dict[str, Any]:
    """Score a linear/async final submission using mode-neutral outcomes."""
    final_actions = [str(value) for value in submission.get("final_action_ids") or []]
    completed = set(final_actions)
    required = {str(value) for value in expected.get("affected_work_ids") or []}
    superseded = {str(value) for value in expected.get("superseded_work_ids") or []}
    prior = {str(value) for value in expected.get("prior_work_ids") or []}
    revised = submission.get("revised_plan") or {}
    closure = submission.get("closure") or {}
    closure_payload = {
        "event_id": expected["event_id"],
        "final_action_ids": list(expected.get("affected_work_ids") or []),
        "preserved_work_ids": list(expected.get("prior_work_ids") or []),
    }

    points = _required_points(public, expected, completed)
    points.extend([
        _point(
            "no_superseded_action",
            "No provisional or superseded action appears in the final outcome.",
            0.10,
            not bool(completed & superseded),
        ),
        _point(
            "no_extraneous_or_duplicate_action",
            "The final action list contains no unrelated or duplicate work.",
            0.10,
            len(final_actions) == len(completed) and not bool(completed - (required | prior)),
        ),
        _point(
            "prior_work_preserved",
            "Previously completed unaffected work is preserved exactly.",
            0.05,
            {str(value) for value in revised.get("preserved_work_ids") or []} == prior,
        ),
        _point(
            "closure_verified",
            "The final state is reverified against the canonical outcome.",
            0.05,
            closure.get("reverified") is True
            and closure.get("final_revision") == canonical_sha256(closure_payload),
        ),
    ])
    return _result(str(public["case_id"]), points)


def score_react_task_outcome(
    public: dict[str, Any], expected: dict[str, Any], state: Any,
) -> dict[str, Any]:
    """Score a blocking ReAct state with the same semantic point families."""
    state_dict = state.as_dict() if hasattr(state, "as_dict") else dict(state)
    executions = list(state_dict.get("executed_actions") or [])
    executed = [str(item.get("action_id") or "") for item in executions]
    completed = set(executed)
    required = {str(value) for value in expected.get("affected_work_ids") or []}
    superseded = {str(value) for value in expected.get("superseded_work_ids") or []}
    prior = {str(value) for value in expected.get("prior_work_ids") or []}
    required_steps = [
        int(item.get("step") or 0)
        for item in executions
        if str(item.get("action_id") or "") in required
    ]
    latest_required_step = max(required_steps, default=0)
    closure_verified = bool(state_dict.get("finished")) and any(
        int(item.get("step") or 0) > latest_required_step
        for item in state_dict.get("final_inspections") or []
    )

    points = _required_points(public, expected, completed)
    points.extend([
        _point(
            "no_superseded_action",
            "No provisional or superseded action was executed.",
            0.10,
            not bool(completed & superseded),
        ),
        _point(
            "no_extraneous_or_duplicate_action",
            "No unrelated or duplicate action was executed.",
            0.10,
            len(executed) == len(completed) and not bool(completed - required),
        ),
        _point(
            "prior_work_preserved",
            "Previously completed work was not repeated or invalidated.",
            0.05,
            not bool(completed & prior),
        ),
        _point(
            "closure_verified",
            "The final state was inspected after required work and before finish.",
            0.05,
            closure_verified,
        ),
    ])
    return _result(str(public["case_id"]), points)
