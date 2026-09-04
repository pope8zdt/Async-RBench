from __future__ import annotations

import json
from pathlib import Path

from async_rbench.evaluation.audit import audit_run
from async_rbench.spec import discover_cases, validate_case


ROOT = Path(__file__).resolve().parents[1]


def test_all_workstreams_have_passing_positive_and_negative_contract_fixtures(
    contract_fixtures: dict,
) -> None:
    result = contract_fixtures
    assert result["workstream_count"] > 0
    assert result["failed_workstreams"] == []
    assert result["passed_count"] == result["workstream_count"]


def test_case_validation_guards_public_private_evidence_sufficiency() -> None:
    errors = [error for case in discover_cases(ROOT) for error in validate_case(case)]
    assert errors == []


def test_run_audit_separates_public_and_private_rejections(
    tmp_path: Path, contract_fixtures: dict,
) -> None:
    episode = tmp_path / "episode-1"
    episode.mkdir()
    score = {
        "episode_id": "episode-1",
        "case_id": "secure-release",
        "execution_mode": "async",
        "score_status": "scored",
        "participant_metadata": {"max_main_steps": 2, "max_child_steps": 1},
        "main_tokens": 7,
        "child_tokens": 5,
        "total_tokens": 12,
        "episode_duration_ms": 123.0,
        "result_contract_rejected_count": 1,
    }
    (episode / "score.json").write_text(json.dumps(score), encoding="utf-8")
    events = [
        {"type": "child_spawned", "child_id": "child-1", "work_units": ["security_patch"]},
        {"type": "child_spawned", "child_id": "child-2", "work_units": ["step_limited"]},
        {"type": "child_spawned", "child_id": "child-3", "work_units": ["safety_abort"]},
        {"type": "agent_progress", "phase": "model_call_finished", "role": "main", "turn": 2},
        {"type": "agent_progress", "phase": "model_call_finished", "role": "child:child-1", "turn": 1},
        {"type": "agent_progress", "phase": "model_call_finished", "role": "child:child-2", "turn": 1},
        {
            "type": "child_completed", "child_id": "child-1",
            "payload": {"evidence": {"finding": "incomplete"}},
        },
        {
            "type": "result_rejection_evaluator_fact", "completion_id": "completion-1",
            "reason_codes": ["missing_required_evidence", "validator_command_failed"],
        },
        {
            "type": "result_rejected", "child_id": "child-1", "completion_id": "completion-1",
            "workstream_id": "security_patch",
            "reason_codes": ["missing_required_evidence", "result_contract_rejected"],
        },
        {"type": "step_limit_reached", "role": "main", "limit": 2},
        {"type": "child_step_limit_reached", "child_id": "child-2", "reason": "horizon"},
        {"type": "child_resource_safety_abort", "child_id": "child-3", "reason": "fuse"},
        {"type": "episode_ended", "local_status": "resource_safety_abort"},
    ]
    (episode / "event_source.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8",
    )

    report = audit_run(tmp_path, ROOT, contract_fixtures=contract_fixtures)
    assert report["episode_count"] == 1
    assert report["rejections"]["private_reason_counts"] == {
        "missing_required_evidence": 1,
        "validator_command_failed": 1,
    }
    assert report["rejections"]["private_validator_review_rejection_count"] == 1
    assert report["rejections"]["rejections_with_public_structural_reason_count"] == 1
    assert report["resources"]["main_step_limit_reached_count"] == 1
    assert report["resources"]["child_step_limit_hit_count"] == 1
    assert report["resources"]["child_resource_safety_abort_count"] == 1
    assert report["resources"]["resource_safety_abort_episode_count"] == 1
    assert report["rejections"]["root_cause_counts"] == {
        "participant_structural_contract_violation": 1,
    }
    assert report["validator_observation_coverage"]["workstream_count"] == (
        contract_fixtures["workstream_count"]
    )
    assert report["artifact_compatibility"]["all_episodes_match_current"] is False
