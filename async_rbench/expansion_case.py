"""Runnable mode-neutral capsules compiled from adjudicated v2 blueprints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .authoritative_capsule import canonical_sha256, oracle_submission
from .react_baseline import BlockingReActEnvironment
from .shared_task_scoring import score_capsule_task_outcome
from .shared_task_scoring import score_react_task_outcome


def load_case(case_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    public = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    expected = json.loads((case_dir / "private" / "expected.json").read_text(encoding="utf-8"))
    return public, expected


def score_submission(case_dir: Path, submission: dict[str, Any]) -> dict[str, Any]:
    public, expected = load_case(case_dir)
    return score_capsule_task_outcome(public, expected, submission)


def oracle(case_dir: Path, mode: str) -> dict[str, Any]:
    return oracle_submission(case_dir, mode)


def verify_file(case_dir: Path, submission_path: Path) -> dict[str, Any]:
    submission = json.loads(submission_path.read_text(encoding="utf-8"))
    return score_submission(case_dir, submission)


def point_specs(public: dict[str, Any], expected: dict[str, Any]) -> list[dict[str, Any]]:
    descriptions = {
        str(row["id"]): str(row.get("description") or "")
        for row in (public.get("causal_record") or {}).get("affected_work") or []
    }
    required = list(map(str, expected.get("affected_work_ids") or []))
    each = 0.70 / len(required)
    points = [
        {
            "id": f"required_action_{index:02d}",
            "weight": each,
            "description": descriptions[action_id],
            "mode_neutral": True,
        }
        for index, action_id in enumerate(required, 1)
    ]
    points.extend([
        {"id": "no_superseded_action", "weight": 0.10, "description": "No stale action survives in the final outcome.", "mode_neutral": True},
        {"id": "no_extraneous_or_duplicate_action", "weight": 0.10, "description": "No unrelated or duplicate action is committed.", "mode_neutral": True},
        {"id": "prior_work_preserved", "weight": 0.05, "description": "Valid prior work is preserved exactly.", "mode_neutral": True},
        {"id": "closure_verified", "weight": 0.05, "description": "The final state is reverified.", "mode_neutral": True},
    ])
    return points


def oracle_gate(case_dir: Path) -> dict[str, Any]:
    results = {}
    for mode in ("linear", "async"):
        result = score_submission(case_dir, oracle(case_dir, mode))
        results[mode] = result
    return results


def react_oracle_gate(case_dir: Path) -> dict[str, Any]:
    """Prove feasibility in the blocking, single-agent ReAct harness."""
    public, expected = load_case(case_dir)
    environment = BlockingReActEnvironment(public, expected)
    environment.call("inspect_current_state")
    environment.call("query_authoritative_evidence")
    for action_id in expected.get("affected_work_ids") or []:
        environment.call("execute_action", {"action_id": action_id})
    environment.call("inspect_final_state")
    environment.call("finish", {"summary": "All required outcomes completed and reverified."})
    return {
        "score": score_react_task_outcome(public, expected, environment.state),
        "state": environment.state.as_dict(),
        "trace": environment.trace,
    }


def mutation_gate(case_dir: Path) -> list[dict[str, Any]]:
    public, expected = load_case(case_dir)
    base = oracle(case_dir, "async")
    mutations: list[tuple[str, dict[str, Any]]] = []
    required = list(expected.get("affected_work_ids") or [])
    for index, action_id in enumerate(required, 1):
        mutant = json.loads(json.dumps(base))
        mutant["final_action_ids"] = [value for value in mutant["final_action_ids"] if value != action_id]
        mutations.append((f"required_action_{index:02d}", mutant))
    mutant = json.loads(json.dumps(base)); mutant["final_action_ids"] += list(expected.get("superseded_work_ids") or [])
    mutations.append(("no_superseded_action", mutant))
    mutant = json.loads(json.dumps(base)); mutant["final_action_ids"].append("extraneous:unknown")
    mutations.append(("no_extraneous_or_duplicate_action", mutant))
    mutant = json.loads(json.dumps(base)); mutant["revised_plan"]["preserved_work_ids"] = []
    mutations.append(("prior_work_preserved", mutant))
    mutant = json.loads(json.dumps(base)); mutant["closure"]["reverified"] = False
    mutations.append(("closure_verified", mutant))
    results = []
    for target, submission in mutations:
        score = score_submission(case_dir, submission)
        point = next(item for item in score["test_points"] if item["id"] == target)
        results.append({
            "target_point": target,
            "target_failed": not point["passed"],
            "mutant_score": score["score"],
            "passed": not point["passed"] and score["score"] < 1.0,
        })
    return results


def capsule_sha256(case_dir: Path) -> str:
    public, _ = load_case(case_dir)
    return canonical_sha256(public)
