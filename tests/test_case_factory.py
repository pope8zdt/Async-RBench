from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from async_rbench.case_factory import (
    build_candidate_backlog, build_transformation_spec, scaffold_candidate_instance,
    validate_candidate_instance,
)
from async_rbench.dataset_policy import difficulty_profile, load_dataset_policy
from async_rbench.dynamic_pilot import _event_contract, _secure_points
from async_rbench.spec import load_case
from async_rbench.case_quality import instruction_sha256
from async_rbench.evaluation.weighting import (
    DYNAMIC_CONTROL_DIMENSIONS, SCORE_POLICY_VERSION,
)

from author_local import requires_author_local


ROOT = Path(__file__).resolve().parents[1]
_CANDIDATE_SOURCE = requires_author_local(
    "upstream/terminal-bench/original-tasks-locked/git-leak-recovery/task.yaml",
)
SIMPLE_DEMO = ROOT / "examples/simple-review/secure-release-demo.json"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def _accepted_trajectory() -> dict:
    return {
        "review_id": "trajectory-1",
        "human_review": {
            "review_decision": "accept",
            "task_match": "yes",
            "version_match": "exact",
            "trajectory_quality": "usable",
            "failure_attribution": "model",
            "replanning_evidence": "direct",
            "research_events": ["late_authoritative_result"],
            "recommended_uses": ["counterfactual_source"],
            "evidence_step_ids": [3, 5],
            "reviewer_note": "usable causal evidence",
        },
    }


def _accepted_decision(trajectory_id: str = "trajectory-1") -> dict:
    return {
        "decision_id": "decision-1",
        "trajectory_review_id": trajectory_id,
        "task_name": "secure-release",
        "agent_proposal": {"event_type": "redelegation"},
        "human_review": {
            "trigger_can_be_async_result": "yes",
            "arrival_order_matters": "yes",
            "plan_change_required": "yes",
            "affected_scope": "multiple_branches",
            "semantic_consequence_observable": "yes",
            "control_consequence_observable": "yes",
            "prompt_leakage_risk": "no",
            "benchmark_eligible": "accept",
            "capability_target": "async_dynamic_replanning",
            "relevance_tier": "critical",
            "topology_roles": ["authority_producer", "downstream_consumer"],
            "evidence_step_ids": [3, 5],
            "reviewer_note": "approved",
        },
    }


def _candidate(tmp_path: Path) -> Path:
    candidate = tmp_path / "seed-2"
    shutil.copytree(ROOT / "cases" / "secure-release", candidate)
    evidence = candidate / "review_evidence"
    _write_jsonl(evidence / "trajectories.jsonl", [_accepted_trajectory()])
    _write_jsonl(evidence / "decisions.jsonl", [_accepted_decision()])
    manifest = json.loads(
        (ROOT / "tests/verifier_mutations/mutation_manifest.json").read_text(encoding="utf-8")
    )
    (candidate / "mutation_families.json").write_text(json.dumps({
        "families": [
            family for family in manifest["families"]
            if family["case_id"] == "secure-release"
        ],
    }), encoding="utf-8")
    profile = difficulty_profile(
        load_case(candidate / "public_case.yaml"), load_dataset_policy(ROOT),
    )
    (candidate / "candidate_metadata.json").write_text(json.dumps({
        "schema_version": "2",
        "case_id": "secure-release",
        "instance_id": "seed-2",
        "stage": "approved_for_promotion",
        "review_evidence": {
            "trajectory_reviews": "review_evidence/trajectories.jsonl",
            "decision_reviews": "review_evidence/decisions.jsonl",
        },
        "design_binding": {
            "accepted_decision_ids": ["decision-1"],
            "primary_event_theme": "late_or_out_of_order_superseded_result",
            "async_scenario_class": "result_eventful",
            "capabilities": [
                "stale_result_rejection", "selective_invalidation",
                "verification_reopen",
            ],
            "dynamic_decision_contract": {
                "prior_state": "a pre-rewrite patch exists",
                "late_event": "the authoritative rewrite arrives",
                "affected_scope": ["vulnerability_patch", "release_manifest"],
                "required_response": ["reject stale patch", "rebuild and verify"],
                "forbidden_response": ["deploy stale patch"],
                "observable_evidence": ["artifact lineage", "verification trace"],
            },
            "dynamic_control_dimensions": list(DYNAMIC_CONTROL_DIMENSIONS),
            "score_policy_version": SCORE_POLICY_VERSION,
        },
        "human_approval": {
            "status": "approved", "reviewer": "reviewer-1",
            "reviewed_at": "2026-08-27T00:00:00Z",
        },
        "dataset_binding": {"split": "calibration"},
        "difficulty_profile": profile,
        "execution_evidence": "review_evidence/release_evidence.json",
    }), encoding="utf-8")
    public = yaml.safe_load((candidate / "public_case.yaml").read_text(encoding="utf-8"))
    sources = []
    for source in public["source_tasks"]:
        task_path = ROOT / source["upstream_path"] / "task.yaml"
        task = yaml.safe_load(task_path.read_text(encoding="utf-8"))
        sources.append({
            "task_id": source["id"],
            "task_path": f"{source['upstream_path']}/task.yaml",
            "instruction_sha256": instruction_sha256(task["instruction"]),
            "requirement_mappings": [{
                "source_anchor": next(
                    line.strip() for line in task["instruction"].splitlines() if line.strip()
                ),
                "requirement_ids": ["test.public-contract"],
            }],
        })
    semantic = json.loads(
        (candidate / "task/tests/semantic_checks.json").read_text(encoding="utf-8")
    )
    dynamic = json.loads(
        (candidate / "task/tests/control_flow_checks.json").read_text(encoding="utf-8")
    )
    private_path = candidate / "private/private_case.yaml"
    private = yaml.safe_load(private_path.read_text(encoding="utf-8"))
    for item in private["information_sufficiency"]:
        item["requirement_ids"] = ["test.public-contract"]
    private_path.write_text(yaml.safe_dump(private, sort_keys=False), encoding="utf-8")
    equivalence = candidate / "task/equivalence_solutions/test-alternative.sh"
    equivalence.parent.mkdir(parents=True, exist_ok=True)
    equivalence.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    negative_dir = candidate / "task/negative_mutations"
    negative_dir.mkdir(parents=True, exist_ok=True)
    for name in ("negative-a.sh", "negative-b.sh"):
        (negative_dir / name).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    quality = {
        "schema_version": "1",
        "source_contract": {
            "instruction_preservation": "requirements_manifest",
            "sources": sources,
            "manifest_review": {
                "reviewer_id": "test-reviewer",
                "reviewed_at": "2026-08-27T00:00:00Z",
                "decision": "approved",
            },
        },
        "requirements": [{
            "id": "test.public-contract",
            "public_evidence": [{
                "path": "task/task.yaml",
                "contains": "The repository at /app/repo",
            }],
            "covers": {
                "semantic_checks": [item["id"] for item in semantic["checks"]],
                "dynamic_control_checks": [item["id"] for item in dynamic["checks"]],
                "workstream_validators": [item["id"] for item in public["workstreams"]],
                "hidden_checks": list(private["hidden_checks"]),
            },
        }],
        "equivalence_solutions": [{
            "id": "test-alternative",
            "path": "task/equivalence_solutions/test-alternative.sh",
            "distinguishes_from_oracle": "Test fixture with a distinct script path.",
        }],
        "negative_mutations": [
            {
                "id": "negative-a", "path": "task/negative_mutations/negative-a.sh",
                "must_fail": [semantic["checks"][0]["id"]],
            },
            {
                "id": "negative-b", "path": "task/negative_mutations/negative-b.sh",
                "must_fail": [semantic["checks"][1]["id"]],
            },
        ],
    }
    (candidate / "private/quality_contract.yaml").write_text(
        yaml.safe_dump(quality, sort_keys=False), encoding="utf-8",
    )
    return candidate


@_CANDIDATE_SOURCE
def test_candidate_instance_passes_all_static_promotion_gates(tmp_path: Path) -> None:
    metadata, errors = validate_candidate_instance(
        ROOT, "secure-release", _candidate(tmp_path), require_execution_evidence=False,
    )
    assert metadata is not None
    assert errors == []


@_CANDIDATE_SOURCE
def test_candidate_instance_cannot_promote_without_executed_release_evidence(tmp_path: Path) -> None:
    _, errors = validate_candidate_instance(ROOT, "secure-release", _candidate(tmp_path))
    assert any("missing executed Oracle/verifier evidence" in error for error in errors)


@_CANDIDATE_SOURCE
def test_candidate_instance_rejects_missing_quality_contract(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    (candidate / "private/quality_contract.yaml").unlink()
    _, errors = validate_candidate_instance(
        ROOT, "secure-release", candidate, require_execution_evidence=False,
    )
    assert any("missing transformed-case quality contract" in error for error in errors)


@_CANDIDATE_SOURCE
def test_candidate_instance_rejects_unlinked_accepted_decision(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    _write_jsonl(
        candidate / "review_evidence/decisions.jsonl",
        [_accepted_decision("different-trajectory")],
    )
    _, errors = validate_candidate_instance(ROOT, "secure-release", candidate)
    assert any("does not reference an accepted trajectory" in error for error in errors)


@_CANDIDATE_SOURCE
def test_candidate_instance_requires_explicit_human_approval(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    metadata_path = candidate / "candidate_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["human_approval"]["status"] = "pending"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    _, errors = validate_candidate_instance(ROOT, "secure-release", candidate)
    assert "human_approval.status must be 'approved'" in errors


@_CANDIDATE_SOURCE
def test_candidate_design_binding_must_match_private_contract(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    metadata_path = candidate / "candidate_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["design_binding"]["primary_event_theme"] = "conflicting_valid_results"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    _, errors = validate_candidate_instance(ROOT, "secure-release", candidate)
    assert "design_binding.primary_event_theme must match private classification" in errors


def test_human_accepts_export_to_non_promoting_candidate_backlog() -> None:
    report = build_candidate_backlog([_accepted_trajectory()], [_accepted_decision()])
    assert report["valid"] is True
    assert report["candidate_count"] == 1
    candidate = report["candidates"][0]
    assert candidate["status"] == "awaiting_case_transformation"
    assert candidate["suggested_primary_event_themes"] == [
        "child_failure_or_implicit_error"
    ]
    assert report["policy"]["automatic_oracle"] is False
    assert report["policy"]["automatic_promotion"] is False


def test_candidate_backlog_rejects_decision_from_unaccepted_trajectory() -> None:
    trajectory = _accepted_trajectory()
    trajectory["human_review"]["review_decision"] = "reject"
    report = build_candidate_backlog([trajectory], [_accepted_decision()])
    assert report["valid"] is False
    assert report["candidate_count"] == 0


def _simple_annotation(review_id: str) -> dict:
    return {
        "schema_version": "2",
        "review_id": review_id,
        "reviewer_id": "pilot-reviewer",
        "answers": {
            "late_after_work_started": "yes",
            "requires_plan_change": "yes",
            "evidence_is_faithful": "yes",
        },
        "route": "candidate_confirmed",
        "evidence_problem_parts": [],
    }


def _transformation_plan(review_id: str) -> dict:
    plan = {
        "review_id": review_id,
        "target_family": "secure-release",
        "instance_id": "authority-after-patch-001",
        "template_instance": "seed-1",
        "source_event_type": "reverification",
        "primary_event_theme": "late_or_out_of_order_superseded_result",
        "secondary_event_themes": ["delayed_authoritative_result"],
        "async_scenario_class": "result_eventful",
        "capabilities": [
            "stale_result_rejection", "selective_invalidation", "verification_reopen",
        ],
        "affected_scope": "multiple_branches",
        "topology_roles": ["authority_producer", "downstream_consumer"],
        "event_schedule": {"sr_a_patch": 2, "sr_a_rewrite": 5},
        "dynamic_decision_contract": {
            "prior_state": "a patch is prepared against the pre-rewrite history",
            "late_event": "the authoritative history rewrite arrives",
            "affected_scope": ["vulnerability_patch", "release_manifest"],
            "required_response": ["reject stale patch", "rebuild from rewritten history"],
            "forbidden_response": ["deploy pre-rewrite patch", "skip reverification"],
            "observable_evidence": ["result consumption", "artifact lineage", "verification"],
        },
        "event_contracts": [_event_contract(
            "sr_a_rewrite", "late_or_out_of_order_superseded_result",
            affected=["vulnerability_patch", "git_server", "release_manifest"],
            unaffected=["nginx_config"],
            opportunities=[
                "stale_completion", "pre_event_affected_commit",
                "pre_event_unaffected_commit",
            ],
            trigger_after=["vulnerability_patch", "nginx_config"],
        )],
        "dataset_split": "calibration",
        "human_approval": {
            "status": "approved", "reviewer": "pilot-owner",
            "reviewed_at": "2026-08-28T00:00:00+08:00",
        },
    }
    plan["dynamic_point_plan"] = _secure_points()
    return plan


def test_simple_review_builds_a_transformation_spec() -> None:
    record = json.loads(SIMPLE_DEMO.read_text(encoding="utf-8"))
    spec = build_transformation_spec(
        record, [_simple_annotation(record["review_id"])],
        _transformation_plan(record["review_id"]),
    )
    assert spec["status"] == "ready_for_scaffolding"
    assert spec["review_consensus"]["reviewer_count"] == 1
    assert spec["design"]["event_schedule"] == {"sr_a_patch": 2, "sr_a_rewrite": 5}
    assert spec["design"]["dynamic_decision_contract"]["required_response"]
    assert len(spec["design"]["dynamic_point_plan"]) == len(_secure_points())


def test_nonconfirmed_simple_review_cannot_build_a_spec() -> None:
    record = json.loads(SIMPLE_DEMO.read_text(encoding="utf-8"))
    annotation = _simple_annotation(record["review_id"])
    annotation["answers"]["requires_plan_change"] = "no"
    annotation["route"] = "no_replanning_need"
    with pytest.raises(ValueError, match="not eligible"):
        build_transformation_spec(
            record, [annotation], _transformation_plan(record["review_id"]),
        )


def test_transformation_spec_scaffolds_a_complete_candidate(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "cases").mkdir(parents=True)
    shutil.copytree(ROOT / "cases/secure-release", root / "cases/secure-release")
    shutil.copy2(ROOT / "cases/registry.json", root / "cases/registry.json")
    shutil.copy2(ROOT / "dataset_policy.json", root / "dataset_policy.json")
    mutation_dir = root / "tests/verifier_mutations"
    mutation_dir.mkdir(parents=True)
    shutil.copy2(
        ROOT / "tests/verifier_mutations/mutation_manifest.json",
        mutation_dir / "mutation_manifest.json",
    )
    record = json.loads(SIMPLE_DEMO.read_text(encoding="utf-8"))
    spec = build_transformation_spec(
        record, [_simple_annotation(record["review_id"])],
        _transformation_plan(record["review_id"]),
    )
    candidate = scaffold_candidate_instance(root, spec)
    assert (candidate / "candidate_metadata.json").is_file()
    assert (candidate / "transformation_spec.json").is_file()
    private = (candidate / "private/private_case.yaml").read_text(encoding="utf-8")
    assert "sr_a_patch" in private and "at: 2" in private
    assert "sr_a_rewrite" in private
    assert "trigger: after_artifacts_committed" in private
    assert "- vulnerability_patch" in private and "- nginx_config" in private
    registry = json.loads(
        (candidate / "task/tests/control_flow_checks.json").read_text(encoding="utf-8")
    )
    assert registry["version"] == "7"
    assert registry["event_contracts"][0]["event_id"] == "sr_a_rewrite"
    assert len(registry["checks"]) == len(_secure_points())
