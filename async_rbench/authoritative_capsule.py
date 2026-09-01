"""Runnable source-derived case capsules used before full benchmark promotion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


POINT_WEIGHTS = {
    "source_identity": 0.10,
    "pre_event_work": 0.10,
    "result_intake": 0.15,
    "plan_revision": 0.15,
    "selective_preservation": 0.10,
    "stale_rejection": 0.15,
    "affected_completion": 0.15,
    "closure_reverification": 0.10,
}


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_capsule(case_dir: Path) -> tuple[dict, dict]:
    public = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    private = json.loads((case_dir / "private" / "expected.json").read_text(encoding="utf-8"))
    return public, private


def oracle_submission(case_dir: Path, mode: str) -> dict:
    public, expected = load_capsule(case_dir)
    if mode not in {"linear", "async"}:
        raise ValueError("mode must be linear or async")
    sequence = int(public["scenarios"][mode]["event_release_tick"])
    final_actions = list(expected["affected_work_ids"])
    revised_plan = {
        "preserved_work_ids": list(expected["prior_work_ids"]),
        "invalidated_work_ids": list(expected["superseded_work_ids"]),
        "required_action_ids": final_actions,
    }
    closure_payload = {
        "event_id": expected["event_id"],
        "final_action_ids": final_actions,
        "preserved_work_ids": list(expected["prior_work_ids"]),
    }
    return {
        "case_id": public["case_id"],
        "source_id": public["source"]["source_id"],
        "instruction_sha256": public["source"]["instruction_sha256"],
        "initial_plan": {
            "completed_before_event": list(expected["prior_work_ids"]),
            "provisional_action_ids": list(expected["superseded_work_ids"]),
        },
        "event_intake": {
            "event_id": expected["event_id"], "sequence": sequence, "accepted": True,
        },
        "revised_plan": revised_plan,
        "final_action_ids": final_actions,
        "closure": {
            "reverified": True,
            "final_revision": canonical_sha256(closure_payload),
        },
    }


def score_submission(case_dir: Path, submission: dict, mode: str) -> dict:
    public, expected = load_capsule(case_dir)
    release_tick = int(public["scenarios"][mode]["event_release_tick"])
    initial = submission.get("initial_plan") or {}
    intake = submission.get("event_intake") or {}
    revised = submission.get("revised_plan") or {}
    final_actions = list(submission.get("final_action_ids") or [])
    closure_payload = {
        "event_id": expected["event_id"],
        "final_action_ids": list(expected["affected_work_ids"]),
        "preserved_work_ids": list(expected["prior_work_ids"]),
    }
    checks = {
        "source_identity": (
            submission.get("source_id") == public["source"]["source_id"]
            and submission.get("instruction_sha256") == public["source"]["instruction_sha256"]
        ),
        "pre_event_work": set(initial.get("completed_before_event") or []) == set(expected["prior_work_ids"]),
        "result_intake": (
            intake.get("event_id") == expected["event_id"]
            and intake.get("accepted") is True
            and int(intake.get("sequence") or 0) >= release_tick
        ),
        "plan_revision": (
            set(revised.get("invalidated_work_ids") or []) == set(expected["superseded_work_ids"])
            and set(revised.get("required_action_ids") or []) == set(expected["affected_work_ids"])
        ),
        "selective_preservation": set(revised.get("preserved_work_ids") or []) == set(expected["prior_work_ids"]),
        "stale_rejection": not (set(final_actions) & set(expected["superseded_work_ids"])),
        # ``final_action_ids`` has historically been ambiguous between actions
        # executed after the event and the full committed action state.  Both
        # are semantically valid when prior work is preserved, so require all
        # affected work and reject anything outside affected+prior work.
        "affected_completion": (
            set(expected["affected_work_ids"]).issubset(set(final_actions))
            and set(final_actions).issubset(
                set(expected["affected_work_ids"]) | set(expected["prior_work_ids"])
            )
        ),
        "closure_reverification": (
            (submission.get("closure") or {}).get("reverified") is True
            and (submission.get("closure") or {}).get("final_revision") == canonical_sha256(closure_payload)
        ),
    }
    point_scores = {key: POINT_WEIGHTS[key] if value else 0.0 for key, value in checks.items()}
    return {
        "case_id": public["case_id"],
        "mode": mode,
        "score": round(sum(point_scores.values()), 8),
        "checks": checks,
        "point_scores": point_scores,
        "scored_point_count": len(checks),
        "unscored_point_count": 0,
    }


def verify_submission_file(case_dir: Path, submission_path: Path, mode: str) -> dict:
    submission = json.loads(submission_path.read_text(encoding="utf-8"))
    return score_submission(case_dir, submission, mode)
