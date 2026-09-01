"""Fail-closed promotion gate for reviewed, transformed case instances."""

from __future__ import annotations

import json
import shutil
import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from .evaluation.mutation_audit import validate_candidate_mutation_suite
from .evaluation.registry_audit import validate_case_registries
from .provenance import validate_sources
from .spec import (
    CASE_INSTANCE_ID_RE, load_case, load_case_registry, resolve_case_instance,
    validate_case,
)
from .simple_review import route_simple_review, validate_simple_review_record
from .trajectory_curation import read_jsonl, validate_review
from .dataset_policy import DATASET_SPLITS, difficulty_profile, load_dataset_policy
from .case_quality import validate_case_quality
from .case_ir import (
    compile_score_plan,
    validate_case_ir,
    validate_score_plan,
    write_case_ir,
)
from .evaluation.weighting import DYNAMIC_CONTROL_DIMENSIONS, SCORE_POLICY_VERSION
from .dynamic_points import (
    participant_leakage_hits, validate_dynamic_point_plan, write_dynamic_registry,
    validate_event_contracts,
)


CANDIDATE_METADATA = "candidate_metadata.json"
RELEASE_EVIDENCE = "review_evidence/release_evidence.json"
REQUIRED_STAGE = "approved_for_promotion"
EVENT_THEME_SUGGESTIONS = {
    "late_authoritative_result": ["delayed_authoritative_result"],
    "conflicting_results": ["conflicting_valid_results"],
    "stale_result_risk": ["late_or_out_of_order_superseded_result"],
    "downstream_invalidation": ["task_scope_or_dependency_change"],
    "selective_preservation": ["task_scope_or_dependency_change"],
    "cancellation": [
        "delayed_authoritative_result", "straggler_under_resource_pressure",
    ],
    "redelegation": ["child_failure_or_implicit_error"],
    "reverification": [
        "partial_then_complete_result", "task_scope_or_dependency_change",
    ],
}


def candidate_promotion_eligibility(
    metadata: dict[str, Any],
) -> tuple[bool, str | None]:
    """Keep simulation-only mechanics candidates outside the official registry."""
    pilot = metadata.get("pilot_validation") or {}
    if pilot.get("simulated_review") is True or pilot.get("promotion_eligible") is False:
        return False, "simulation-only candidate cannot be promoted into the benchmark"
    return True, None


def candidate_bundle_sha256(candidate: Path) -> str:
    """Digest release-relevant candidate bytes, excluding generated execution evidence."""
    excluded = {
        "review_evidence/release_evidence.json",
        "review_evidence/execution_verification.json",
    }
    digest = hashlib.sha256()
    for path in sorted(item for item in candidate.rglob("*") if item.is_file()):
        relative = path.relative_to(candidate).as_posix()
        if (
            relative in excluded
            or relative.startswith("review_evidence/execution_quality/")
            or "__pycache__" in path.parts
            or path.suffix == ".pyc"
        ):
            continue
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def validate_release_evidence(
    candidate: Path, metadata: dict[str, Any], family_id: str, instance_id: str,
) -> list[str]:
    errors: list[str] = []
    evidence_ref = metadata.get("execution_evidence")
    if evidence_ref != RELEASE_EVIDENCE:
        return [f"candidate_metadata.execution_evidence must be {RELEASE_EVIDENCE!r}"]
    evidence_path = candidate / RELEASE_EVIDENCE
    if not evidence_path.is_file():
        return [f"missing executed Oracle/verifier evidence: {evidence_path}"]
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return [f"invalid release evidence {evidence_path}: {exc}"]
    if evidence.get("schema_version") != "1.0" or evidence.get("status") != "pass":
        errors.append("release evidence must be schema 1.0 with status 'pass'")
    if evidence.get("score_policy_version") != SCORE_POLICY_VERSION:
        errors.append("release evidence score policy is stale")
    if evidence.get("case_id") != family_id or evidence.get("instance_id") != instance_id:
        errors.append("release evidence family/instance identity does not match candidate")
    if evidence.get("case_bundle_sha256") != candidate_bundle_sha256(candidate):
        errors.append("release evidence case bundle digest is stale or does not match")
    if evidence.get("oracle_completed") is not True:
        errors.append("release evidence does not record a completed Oracle run")
    dynamic_validation = evidence.get("dynamic_contract_validation")
    if not isinstance(dynamic_validation, dict):
        errors.append("release evidence lacks dynamic contract validation")
    else:
        if dynamic_validation.get("passed") is not True:
            errors.append("dynamic contract validation did not pass")
        try:
            control_registry = json.loads(
                (candidate / "task/tests/control_flow_checks.json").read_text(
                    encoding="utf-8"
                )
            )
            expected_dimensions = {
                str(item.get("dimension") or "")
                for item in control_registry.get("checks") or []
            }
        except (OSError, ValueError, TypeError):
            expected_dimensions = set()
        if set(map(str, dynamic_validation.get("dimensions") or [])) != expected_dimensions:
            errors.append(
                "dynamic contract validation dimensions do not match the case registry"
            )
        if int(dynamic_validation.get("critical_point_count") or 0) < 1:
            errors.append("dynamic contract validation has no critical point")
    quality = evidence.get("quality_execution")
    quality_summary_path = candidate / "review_evidence/execution_quality/summary.json"
    if not isinstance(quality, dict) or quality.get("passed") is not True:
        errors.append("release evidence does not record passing equivalence and negative-mutation runs")
    elif not quality_summary_path.is_file():
        errors.append(f"missing raw quality execution summary: {quality_summary_path}")
    else:
        if quality.get("summary_sha256") != hashlib.sha256(
            quality_summary_path.read_bytes()
        ).hexdigest():
            errors.append("quality execution summary digest does not match release evidence")
        try:
            quality_summary = json.loads(quality_summary_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"invalid quality execution summary: {exc}")
        else:
            if quality_summary.get("passed") is not True:
                errors.append("raw quality execution summary is not passing")
    verification = evidence.get("verification")
    if not isinstance(verification, dict) or verification.get("success") is not True:
        errors.append("release evidence does not record a passing hidden verifier run")
    else:
        report_path = candidate / "review_evidence" / "execution_verification.json"
        if not report_path.is_file():
            errors.append(f"missing raw hidden verifier report: {report_path}")
        else:
            report_digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
            if verification.get("report_sha256") != report_digest:
                errors.append("hidden verifier report digest does not match release evidence")
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError) as exc:
                errors.append(f"invalid hidden verifier report: {exc}")
            else:
                if report.get("success") is not True:
                    errors.append("raw hidden verifier report is not passing")
                if report.get("verifier_bundle_sha256") != verification.get("verifier_bundle_sha256"):
                    errors.append("verifier bundle digest does not match raw report")
    return errors


def build_transformation_spec(
    record: dict[str, Any], annotations: list[dict[str, Any]], plan: dict[str, Any],
) -> dict[str, Any]:
    """Bind confirmed one-minute reviews to an explicit technical case design."""
    errors = validate_simple_review_record(record)
    if errors:
        raise ValueError(f"invalid simple review record: {errors}")
    review_id = str(record["review_id"])
    if str(plan.get("review_id") or "") != review_id:
        raise ValueError("transformation plan review_id must match the review record")
    matching = [item for item in annotations if str(item.get("review_id") or "") == review_id]
    if not matching:
        raise ValueError("at least one human annotation is required")
    reviewer_ids: set[str] = set()
    verified_annotations: list[dict[str, Any]] = []
    for index, annotation in enumerate(matching, 1):
        reviewer_id = str(annotation.get("reviewer_id") or "").strip()
        if not reviewer_id or reviewer_id in reviewer_ids:
            raise ValueError(f"annotation {index} reviewer_id must be non-empty and unique")
        reviewer_ids.add(reviewer_id)
        answers = annotation.get("answers")
        if not isinstance(answers, dict):
            raise ValueError(f"annotation {index} answers must be an object")
        problem_parts = annotation.get("evidence_problem_parts") or []
        if not isinstance(problem_parts, list):
            raise ValueError(f"annotation {index} evidence_problem_parts must be a list")
        routed = route_simple_review(
            {str(key): str(value) for key, value in answers.items()},
            [str(value) for value in problem_parts],
        )
        if annotation.get("route") not in {None, routed["route"]}:
            raise ValueError(f"annotation {index} claimed route does not match its answers")
        if routed["route"] != "candidate_confirmed":
            raise ValueError(
                f"annotation {index} is not eligible for transformation: {routed['route']}"
            )
        verified_annotations.append({**annotation, **routed})

    required_text = (
        "target_family", "instance_id", "template_instance", "source_event_type",
        "primary_event_theme", "async_scenario_class", "affected_scope", "dataset_split",
    )
    missing = [field for field in required_text if not str(plan.get(field) or "").strip()]
    if missing:
        raise ValueError(f"transformation plan is missing required fields: {missing}")
    if not CASE_INSTANCE_ID_RE.fullmatch(str(plan["instance_id"])):
        raise ValueError("transformation plan instance_id is invalid")
    if plan["dataset_split"] not in DATASET_SPLITS:
        raise ValueError(f"transformation plan dataset_split must be one of {sorted(DATASET_SPLITS)}")
    for field in ("secondary_event_themes", "capabilities", "topology_roles"):
        value = plan.get(field)
        if not isinstance(value, list):
            raise ValueError(f"transformation plan {field} must be a list")
    schedule = plan.get("event_schedule")
    if not isinstance(schedule, dict) or not schedule:
        raise ValueError("transformation plan event_schedule must be a non-empty object")
    if any(not str(key).strip() or not isinstance(value, int) or value < 0 for key, value in schedule.items()):
        raise ValueError("event_schedule keys must be non-empty and times non-negative integers")
    dynamic_contract = plan.get("dynamic_decision_contract")
    if not isinstance(dynamic_contract, dict):
        raise ValueError("transformation plan dynamic_decision_contract must be an object")
    for field in ("prior_state", "late_event"):
        if not str(dynamic_contract.get(field) or "").strip():
            raise ValueError(f"dynamic_decision_contract.{field} is required")
    for field in (
        "affected_scope", "required_response", "forbidden_response", "observable_evidence",
    ):
        values = dynamic_contract.get(field)
        if (
            not isinstance(values, list) or not values
            or any(not str(value).strip() for value in values)
        ):
            raise ValueError(
                f"dynamic_decision_contract.{field} must be a non-empty string list"
            )
    case_ir = plan.get("case_ir")
    compiled_score_plan: dict[str, Any] | None = None
    if case_ir is not None:
        ir_errors = validate_case_ir(case_ir)
        if ir_errors:
            raise ValueError(f"invalid transformation plan case_ir: {ir_errors}")
        if str(case_ir.get("case_id")) != str(plan["target_family"]):
            raise ValueError("case_ir.case_id must match transformation target_family")
        if str(case_ir.get("instance_id")) != str(plan["instance_id"]):
            raise ValueError("case_ir.instance_id must match transformation instance_id")
        control_prefix = str(plan.get("control_prefix") or "").strip()
        if not control_prefix:
            raise ValueError("a case_ir transformation requires control_prefix")
        compiled_score_plan = compile_score_plan(case_ir, control_prefix)
    dynamic_points = (
        compiled_score_plan["points"] if compiled_score_plan is not None
        else plan.get("dynamic_point_plan")
    )
    event_contracts = plan.get("event_contracts")
    contract_errors = validate_event_contracts(
        event_contracts,
        event_ids={str(event_id) for event_id in schedule},
    )
    if contract_errors:
        raise ValueError(f"invalid transformation plan event_contracts: {contract_errors}")
    point_errors = validate_dynamic_point_plan(
        dynamic_points,
        event_ids={str(event_id) for event_id in schedule},
        event_contracts=event_contracts,
    )
    if point_errors:
        raise ValueError(f"invalid transformation plan dynamic_point_plan: {point_errors}")
    approval = plan.get("human_approval")
    if not isinstance(approval, dict) or approval.get("status") != "approved":
        raise ValueError("transformation plan requires explicit approved human_approval")
    for field in ("reviewer", "reviewed_at"):
        if not str(approval.get(field) or "").strip():
            raise ValueError(f"human_approval.{field} is required")

    simulation_only = all(
        str(item.get("review_origin") or "") == "simulated_pipeline_validation"
        for item in verified_annotations
    )
    policy = {
        "trajectory_role": "discovery_and_evidence_only",
        "action_sequence_oracle": False,
        "requires_static_promotion_gate": True,
    }
    if simulation_only:
        policy.update({
            "simulation_only": True,
            "promotion_eligible": False,
            "requires_independent_human_rereview": True,
        })
    return {
        "schema_version": "1",
        "status": "ready_for_scaffolding",
        "candidate_id": review_id,
        "source": record["source"],
        "task_goal": record["task_goal"],
        "evidence_card": record["evidence_card"],
        "review_consensus": {
            "required_route": "candidate_confirmed",
            "reviewer_count": len(verified_annotations),
            "reviewer_ids": sorted(reviewer_ids),
            "annotations": verified_annotations,
        },
        "design": {
            "target_family": str(plan["target_family"]),
            "instance_id": str(plan["instance_id"]),
            "template_instance": str(plan["template_instance"]),
            "source_event_type": str(plan["source_event_type"]),
            "primary_event_theme": str(plan["primary_event_theme"]),
            "secondary_event_themes": list(plan["secondary_event_themes"]),
            "async_scenario_class": str(plan["async_scenario_class"]),
            "capabilities": list(plan["capabilities"]),
            "affected_scope": str(plan["affected_scope"]),
            "topology_roles": list(plan["topology_roles"]),
            "event_schedule": dict(schedule),
            "dynamic_decision_contract": {
                "prior_state": str(dynamic_contract["prior_state"]),
                "late_event": str(dynamic_contract["late_event"]),
                "affected_scope": list(dynamic_contract["affected_scope"]),
                "required_response": list(dynamic_contract["required_response"]),
                "forbidden_response": list(dynamic_contract["forbidden_response"]),
                "observable_evidence": list(dynamic_contract["observable_evidence"]),
            },
            "event_contracts": json.loads(json.dumps(event_contracts)),
            "dynamic_point_plan": json.loads(json.dumps(dynamic_points)),
            "case_ir": json.loads(json.dumps(case_ir)) if case_ir is not None else None,
            "score_plan": (
                json.loads(json.dumps(compiled_score_plan))
                if compiled_score_plan is not None else None
            ),
            "control_prefix": str(plan.get("control_prefix") or ""),
            "dataset_split": str(plan["dataset_split"]),
            "human_approval": dict(approval),
        },
        "policy": policy,
    }


def _compatibility_reviews(spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create release-gate evidence from the simpler review plus technical binding."""
    design = spec["design"]
    review_id = str(spec["candidate_id"])
    source_event = str(design["source_event_type"])
    evidence_ids = sorted({
        int(excerpt["step_id"])
        for key in ("prior_work", "late_information", "affected_action")
        for excerpt in spec["evidence_card"][key]["excerpts"]
        if str(excerpt["step_id"]).isdigit()
    })
    trajectory = {
        "review_id": review_id,
        "human_review": {
            "review_decision": "accept",
            "task_match": "yes",
            "version_match": "exact",
            "trajectory_quality": "usable",
            "failure_attribution": "not_failure",
            "replanning_evidence": "direct",
            "research_events": [source_event],
            "recommended_uses": ["counterfactual_source", "test_point_source"],
            "evidence_step_ids": evidence_ids,
            "reviewer_note": "Confirmed by one-minute evidence review; technical design is bound in transformation_spec.json.",
        },
    }
    decision_id = f"{review_id}:transformation"
    decision = {
        "decision_id": decision_id,
        "trajectory_review_id": review_id,
        "task_name": str(design["target_family"]),
        "agent_proposal": {"event_type": source_event},
        "human_review": {
            "trigger_can_be_async_result": "yes",
            "arrival_order_matters": "yes",
            "plan_change_required": "yes",
            "affected_scope": str(design["affected_scope"]),
            "semantic_consequence_observable": "yes",
            "control_consequence_observable": "yes",
            "prompt_leakage_risk": "no",
            "benchmark_eligible": "accept",
            "capability_target": "async_dynamic_replanning",
            "relevance_tier": "critical",
            "topology_roles": list(design["topology_roles"]),
            "evidence_step_ids": evidence_ids,
            "reviewer_note": "Technical transformation approved in transformation_spec.json.",
        },
    }
    return trajectory, decision


def scaffold_candidate_instance(root: Path, spec: dict[str, Any]) -> Path:
    """Create a complete isolated candidate bundle from an approved transformation spec."""
    if spec.get("schema_version") != "1" or spec.get("status") != "ready_for_scaffolding":
        raise ValueError("transformation spec must be schema 1 and ready_for_scaffolding")
    design = spec.get("design")
    if not isinstance(design, dict):
        raise ValueError("transformation spec design must be an object")
    family_id = str(design.get("target_family") or "")
    instance_id = str(design.get("instance_id") or "")
    template_instance = str(design.get("template_instance") or "")
    template = resolve_case_instance(root, family_id, template_instance)
    target = root / "candidate_instances" / family_id / instance_id
    if target.exists():
        raise ValueError(f"candidate instance already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        template.case_dir, target,
        ignore=shutil.ignore_patterns(
            "instances", CANDIDATE_METADATA, "review_evidence", "transformation_spec.json",
        ),
    )
    wrapper_functions = {
        "generate.py": ("export_task", "export_task(Path(__file__).resolve().parent, CASE_ID)"),
        "oracle.py": ("run_oracle", "run_oracle(CASE_ID)"),
        "verify.py": ("run_verifier", "run_verifier(CASE_ID)"),
    }
    for filename, (function_name, invocation) in wrapper_functions.items():
        (target / filename).write_text(
            "from pathlib import Path\n"
            "import sys\n\n"
            "HERE = Path(__file__).resolve()\n"
            "PROJECT_ROOT = next(parent for parent in HERE.parents if (parent / 'async_rbench').is_dir())\n"
            "sys.path.insert(0, str(PROJECT_ROOT))\n"
            f"from async_rbench.docker_case import {function_name}\n\n"
            f"CASE_ID = {family_id!r}\n"
            "if __name__ == '__main__':\n"
            f"    {invocation}\n",
            encoding="utf-8",
        )

    private_path = target / "private" / "private_case.yaml"
    private = yaml.safe_load(private_path.read_text(encoding="utf-8"))
    private["classification"] = {
        "primary_event_theme": design["primary_event_theme"],
        "secondary_event_themes": list(design["secondary_event_themes"]),
        "async_scenario_class": design["async_scenario_class"],
    }
    private["capabilities"] = list(design["capabilities"])
    async_events = ((private.get("scenarios") or {}).get("async") or {}).get("events") or []
    events_by_id = {str(event.get("id")): event for event in async_events}
    unknown_events = sorted(set(design["event_schedule"]) - set(events_by_id))
    if unknown_events:
        shutil.rmtree(target)
        raise ValueError(f"event_schedule references unknown template events: {unknown_events}")
    for event_id, at in design["event_schedule"].items():
        events_by_id[event_id]["at"] = at
    for contract in design["event_contracts"]:
        if contract.get("observation_mode") != "gateway_only":
            continue
        event_id = str(contract["event_id"])
        event = events_by_id[event_id]
        arrival = contract.get("arrival_contract") or {}
        after_results = list(arrival.get("after_results") or [])
        if after_results:
            event["trigger"] = "after_results_delivered"
            event["after_results"] = after_results
            event.pop("after_artifacts", None)
        else:
            event["trigger"] = "after_artifacts_committed"
            event["after_artifacts"] = list(arrival.get("after_artifacts") or [])
            event.pop("after_results", None)
        event.pop("at", None)
    private_path.write_text(
        yaml.safe_dump(private, sort_keys=False, allow_unicode=True), encoding="utf-8",
    )
    if isinstance(design.get("case_ir"), dict):
        score_plan = write_case_ir(
            target, dict(design["case_ir"]), str(design["control_prefix"]),
        )
        dynamic_points = list(score_plan["points"])
    else:
        dynamic_points = list(design["dynamic_point_plan"])
    write_dynamic_registry(target, dynamic_points, list(design["event_contracts"]))
    leakage_hits = participant_leakage_hits(target, dynamic_points)
    if leakage_hits:
        shutil.rmtree(target)
        raise ValueError(f"participant-visible dynamic point leakage: {leakage_hits}")

    evidence_dir = target / "review_evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "candidate_record.json").write_text(
        json.dumps({
            "schema_version": "2", "review_id": spec["candidate_id"],
            "source": spec["source"], "task_goal": spec["task_goal"],
            "evidence_card": spec["evidence_card"],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    (evidence_dir / "simple_annotations.jsonl").write_text(
        "".join(
            json.dumps(annotation, ensure_ascii=False) + "\n"
            for annotation in spec["review_consensus"]["annotations"]
        ),
        encoding="utf-8",
    )
    trajectory, decision = _compatibility_reviews(spec)
    (evidence_dir / "trajectories.jsonl").write_text(
        json.dumps(trajectory, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    (evidence_dir / "decisions.jsonl").write_text(
        json.dumps(decision, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    (target / "transformation_spec.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest = json.loads(
        (root / "tests" / "verifier_mutations" / "mutation_manifest.json")
        .read_text(encoding="utf-8")
    )
    mutation_families = []
    for family in manifest.get("families") or []:
        if str(family.get("case_id")) != family_id:
            continue
        copy = json.loads(json.dumps(family))
        copy["id"] = f"{copy['id']}@{instance_id}"
        mutation_families.append(copy)
    (target / "mutation_families.json").write_text(
        json.dumps({"families": mutation_families}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    decision_id = str(decision["decision_id"])
    profile = difficulty_profile(load_case(target / "public_case.yaml"), load_dataset_policy(root))
    metadata = {
        "schema_version": "2",
        "case_id": family_id,
        "instance_id": instance_id,
        "stage": REQUIRED_STAGE,
        "review_evidence": {
            "trajectory_reviews": "review_evidence/trajectories.jsonl",
            "decision_reviews": "review_evidence/decisions.jsonl",
            "simple_review_record": "review_evidence/candidate_record.json",
            "simple_review_annotations": "review_evidence/simple_annotations.jsonl",
            "transformation_spec": "transformation_spec.json",
        },
        "design_binding": {
            "accepted_decision_ids": [decision_id],
            "primary_event_theme": design["primary_event_theme"],
            "async_scenario_class": design["async_scenario_class"],
            "capabilities": list(design["capabilities"]),
            "dynamic_decision_contract": dict(design["dynamic_decision_contract"]),
            "event_contracts": list(design["event_contracts"]),
            "dynamic_point_count": len(dynamic_points),
            "dynamic_point_ids": [
                str(point["id"]) for point in dynamic_points
            ],
            "dynamic_control_dimensions": sorted({
                str(point["dimension"]) for point in dynamic_points
            }),
            "score_unit": (
                "causal_decision_group" if isinstance(design.get("case_ir"), dict)
                else "legacy_lifecycle_stage"
            ),
            "case_ir": "private/case_ir.json" if isinstance(design.get("case_ir"), dict) else None,
            "score_plan": "private/score_plan.json" if isinstance(design.get("case_ir"), dict) else None,
            "score_policy_version": SCORE_POLICY_VERSION,
        },
        "human_approval": dict(design["human_approval"]),
        "dataset_binding": {"split": design["dataset_split"]},
        "difficulty_profile": profile,
        "execution_evidence": RELEASE_EVIDENCE,
    }
    if (spec.get("policy") or {}).get("simulation_only") is True:
        metadata["pilot_validation"] = {
            "simulated_review": True,
            "promotion_eligible": False,
            "requires_independent_human_rereview": True,
        }
    (target / CANDIDATE_METADATA).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return target


def build_candidate_backlog(
    trajectory_reviews: list[dict[str, Any]],
    decision_reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    """Convert validated human accepts into a non-promoting transformation queue."""
    errors: list[str] = []
    accepted_trajectories: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(trajectory_reviews, 1):
        review_errors = validate_review(record, "trajectory")
        errors.extend(f"trajectory line {index}: {error}" for error in review_errors)
        if not review_errors and (record.get("human_review") or {}).get("review_decision") == "accept":
            review_id = str(record.get("review_id") or "")
            if not review_id or review_id in accepted_trajectories:
                errors.append(f"trajectory line {index}: review_id must be non-empty and unique")
            else:
                accepted_trajectories[review_id] = record

    candidates: list[dict[str, Any]] = []
    seen_decisions: set[str] = set()
    for index, record in enumerate(decision_reviews, 1):
        review_errors = validate_review(record, "decision")
        errors.extend(f"decision line {index}: {error}" for error in review_errors)
        review = record.get("human_review") or {}
        if review_errors or review.get("benchmark_eligible") != "accept":
            continue
        decision_id = str(record.get("decision_id") or "")
        trajectory_id = str(record.get("trajectory_review_id") or "")
        if not decision_id or decision_id in seen_decisions:
            errors.append(f"decision line {index}: decision_id must be non-empty and unique")
            continue
        seen_decisions.add(decision_id)
        if trajectory_id not in accepted_trajectories:
            errors.append(
                f"decision line {index}: accepted decision does not reference an accepted trajectory"
            )
            continue
        proposal = record.get("agent_proposal") or {}
        source_event = str(proposal.get("event_type") or "")
        evidence_step_ids = list(review.get("evidence_step_ids") or [])
        candidates.append({
            "candidate_id": decision_id,
            "task_name": str(record.get("task_name") or ""),
            "trajectory_review_id": trajectory_id,
            "source_event_type": source_event,
            "suggested_primary_event_themes": EVENT_THEME_SUGGESTIONS.get(source_event, []),
            "capability_target": review.get("capability_target"),
            "relevance_tier": review.get("relevance_tier"),
            "topology_roles": list(review.get("topology_roles") or []),
            "evidence_step_ids": evidence_step_ids,
            "affected_scope": review.get("affected_scope"),
            "dynamic_decision_contract_draft": {
                "prior_state": str(
                    proposal.get("prior_state")
                    or "Work identified by the earlier evidence steps has already started."
                ),
                "late_event": str(
                    proposal.get("trigger_summary") or source_event
                ),
                "affected_scope": [str(review.get("affected_scope") or "unspecified")],
                "required_response": [str(
                    proposal.get("required_response")
                    or "Revise the affected plan and close it with new verification."
                )],
                "forbidden_response": [str(
                    proposal.get("counterfactual_failure")
                    or "Continue the superseded plan without revision."
                )],
                "observable_evidence": [
                    f"review evidence step {step_id}" for step_id in evidence_step_ids
                ],
            },
            "dynamic_point_design_draft": {
                "target_count": "2-4 atomic event points or 4-8 main replanning points",
                "required_dimensions": "derive from the event's causal opportunities",
                "event_contract_required": True,
                "required_per_point_fields": [
                    "event_id", "precondition", "expected_behavior",
                    "forbidden_behavior", "primary_evidence", "mutation_id",
                    "independence_key", "evidence_group", "evidence_spec",
                    "precondition_contract", "requires_outcome_anchor",
                ],
                "policy": "human-designed hidden decision units; trajectory is evidence only",
            },
            "status": "awaiting_case_transformation",
        })
    return {
        "schema_version": "1",
        "valid": not errors,
        "trajectory_review_count": len(trajectory_reviews),
        "decision_review_count": len(decision_reviews),
        "accepted_trajectory_count": len(accepted_trajectories),
        "candidate_count": len(candidates),
        "policy": {
            "trajectory_role": "discovery_and_evidence_only",
            "automatic_oracle": False,
            "automatic_promotion": False,
            "next_stage": "human-designed public/private/task transformation",
            "score_policy_version": SCORE_POLICY_VERSION,
            "primary_metric": "dynamic_control_score",
        },
        "candidates": candidates,
        "errors": errors,
    }


def _inside(base: Path, relative: str, label: str, errors: list[str]) -> Path | None:
    candidate = Path(relative)
    if candidate.is_absolute():
        errors.append(f"{label} must be a candidate-relative path")
        return None
    resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError:
        errors.append(f"{label} escapes the candidate directory")
        return None
    return resolved


def _review_records(
    candidate: Path, metadata: dict[str, Any], kind: str, errors: list[str],
) -> list[dict[str, Any]]:
    evidence = metadata.get("review_evidence")
    if not isinstance(evidence, dict):
        errors.append("candidate_metadata.review_evidence must be an object")
        return []
    relative = evidence.get(f"{kind}_reviews")
    if not isinstance(relative, str) or not relative:
        errors.append(f"review_evidence.{kind}_reviews must name a JSONL file")
        return []
    path = _inside(candidate, relative, f"review_evidence.{kind}_reviews", errors)
    if path is None or not path.is_file():
        errors.append(f"missing {kind} review evidence: {path or relative}")
        return []
    try:
        records = read_jsonl(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"invalid {kind} review evidence {path}: {exc}")
        return []
    for index, record in enumerate(records, 1):
        for error in validate_review(record, kind):
            errors.append(f"{path}: line {index}: {error}")
    return records


def validate_candidate_instance(
    root: Path, family_id: str, candidate: Path, *, require_execution_evidence: bool = True,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate review evidence and every static benchmark release gate."""
    candidate = candidate.resolve()
    errors: list[str] = []
    metadata_path = candidate / CANDIDATE_METADATA
    if not candidate.is_dir() or not metadata_path.is_file():
        return None, [f"candidate instance or {CANDIDATE_METADATA} is missing: {candidate}"]
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return None, [f"invalid candidate metadata {metadata_path}: {exc}"]
    if not isinstance(metadata, dict):
        return None, [f"candidate metadata must be an object: {metadata_path}"]
    instance_id = metadata.get("instance_id")
    if metadata.get("schema_version") != "2":
        errors.append("candidate_metadata.schema_version must be '2'")
    if metadata.get("case_id") != family_id:
        errors.append("candidate_metadata.case_id must match --family")
    if not isinstance(instance_id, str) or not CASE_INSTANCE_ID_RE.fullmatch(instance_id):
        errors.append(f"invalid candidate instance_id: {instance_id!r}")
    elif candidate.name != instance_id:
        errors.append("candidate directory name must equal instance_id")
    if metadata.get("stage") != REQUIRED_STAGE:
        errors.append(f"candidate stage must be {REQUIRED_STAGE!r}")
    dataset_binding = metadata.get("dataset_binding")
    if not isinstance(dataset_binding, dict) or dataset_binding.get("split") not in DATASET_SPLITS:
        errors.append("candidate_metadata.dataset_binding.split must be calibration, development, or test")
    approval = metadata.get("human_approval")
    if not isinstance(approval, dict):
        errors.append("candidate_metadata.human_approval must be an object")
    else:
        if approval.get("status") != "approved":
            errors.append("human_approval.status must be 'approved'")
        if not str(approval.get("reviewer") or "").strip():
            errors.append("human_approval.reviewer is required")
        if not str(approval.get("reviewed_at") or "").strip():
            errors.append("human_approval.reviewed_at is required")

    trajectory_reviews = _review_records(candidate, metadata, "trajectory", errors)
    decision_reviews = _review_records(candidate, metadata, "decision", errors)
    accepted_trajectories = {
        str(record.get("review_id") or "")
        for record in trajectory_reviews
        if (record.get("human_review") or {}).get("review_decision") == "accept"
    }
    accepted_decisions = [
        record for record in decision_reviews
        if (record.get("human_review") or {}).get("benchmark_eligible") == "accept"
    ]
    if not accepted_trajectories:
        errors.append("candidate requires at least one accepted trajectory review")
    if not accepted_decisions:
        errors.append("candidate requires at least one accepted decision review")
    accepted_decision_ids = {
        str(record.get("decision_id") or "") for record in accepted_decisions
    }
    for record in accepted_decisions:
        trajectory_id = str(record.get("trajectory_review_id") or "")
        if trajectory_id not in accepted_trajectories:
            errors.append(
                f"accepted decision {record.get('decision_id')!r} does not reference "
                "an accepted trajectory review"
            )

    design_binding = metadata.get("design_binding")
    if not isinstance(design_binding, dict):
        errors.append("candidate_metadata.design_binding must be an object")
        design_binding = {}
    bound_decisions = design_binding.get("accepted_decision_ids")
    if not isinstance(bound_decisions, list) or not bound_decisions:
        errors.append("design_binding.accepted_decision_ids must be a non-empty list")
        bound_decision_ids: set[str] = set()
    else:
        bound_decision_ids = {str(value) for value in bound_decisions}
        if len(bound_decision_ids) != len(bound_decisions):
            errors.append("design_binding.accepted_decision_ids must be unique")
        unknown_bound = sorted(bound_decision_ids - accepted_decision_ids)
        if unknown_bound:
            errors.append(
                f"design_binding references decisions that are not accepted: {unknown_bound}"
            )

    registry, registry_errors = load_case_registry(root)
    errors.extend(registry_errors)
    family = next(
        (
            item for item in (registry or {}).get("case_families", [])
            if item.get("case_id") == family_id
        ),
        None,
    )
    if family is None:
        errors.append(f"unknown target family: {family_id!r}")
    elif isinstance(instance_id, str):
        registered = {
            str(item.get("instance_id")) for item in family.get("instances") or []
        }
        if instance_id in registered:
            errors.append(f"instance is already registered: {family_id}/{instance_id}")
        target = root / "cases" / family_id / "instances" / instance_id
        if target.exists():
            errors.append(f"target instance path already exists: {target}")

    contract_path = candidate / "public_case.yaml"
    try:
        case = load_case(contract_path)
    except (OSError, ValueError, TypeError) as exc:
        errors.append(f"invalid candidate case contract: {exc}")
        return metadata, errors
    if case.case_id != family_id:
        errors.append("candidate contract case_id must match target family")
    try:
        expected_profile = difficulty_profile(case, load_dataset_policy(root))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"cannot compute candidate difficulty profile: {exc}")
    else:
        if metadata.get("difficulty_profile") != expected_profile:
            errors.append("candidate_metadata.difficulty_profile must match the structural rubric")
    classification = case.raw.get("classification") or {}
    if design_binding.get("primary_event_theme") != classification.get("primary_event_theme"):
        errors.append("design_binding.primary_event_theme must match private classification")
    if design_binding.get("async_scenario_class") != classification.get("async_scenario_class"):
        errors.append("design_binding.async_scenario_class must match private classification")
    bound_capabilities = design_binding.get("capabilities")
    if not isinstance(bound_capabilities, list) or set(map(str, bound_capabilities)) != set(
        map(str, case.raw.get("capabilities") or [])
    ):
        errors.append("design_binding.capabilities must exactly match private capabilities")
    dynamic_contract = design_binding.get("dynamic_decision_contract")
    if not isinstance(dynamic_contract, dict):
        errors.append("design_binding.dynamic_decision_contract must be an object")
    else:
        for field in ("prior_state", "late_event"):
            if not str(dynamic_contract.get(field) or "").strip():
                errors.append(f"dynamic_decision_contract.{field} is required")
        for field in (
            "affected_scope", "required_response", "forbidden_response", "observable_evidence",
        ):
            values = dynamic_contract.get(field)
            if not isinstance(values, list) or not values:
                errors.append(f"dynamic_decision_contract.{field} must be non-empty")
    control_payload: dict[str, Any] = {}
    try:
        loaded_control_payload = json.loads(
            (candidate / "task/tests/control_flow_checks.json").read_text(encoding="utf-8")
        )
        if not isinstance(loaded_control_payload, dict):
            raise ValueError("dynamic point registry must be an object")
        control_payload = loaded_control_payload
        raw_dynamic_points = control_payload.get("checks")
        if not isinstance(raw_dynamic_points, list):
            raise ValueError("dynamic point registry checks must be a list")
        dynamic_points = raw_dynamic_points
    except (OSError, ValueError, TypeError) as exc:
        errors.append(f"cannot load candidate dynamic point registry: {exc}")
        dynamic_points = []
    control_version = str(control_payload.get("version") or "")
    if control_version in {"5", "6", "7"}:
        event_contracts = list(control_payload.get("event_contracts") or [])
        if control_version in {"6", "7"}:
            errors.extend(
                f"candidate event contract: {error}"
                for error in validate_event_contracts(event_contracts)
            )
        point_errors = validate_dynamic_point_plan(
            dynamic_points, registry_version=control_version,
            event_contracts=event_contracts,
        )
        errors.extend(f"candidate dynamic point plan: {error}" for error in point_errors)
        if design_binding.get("dynamic_point_count") != len(dynamic_points):
            errors.append("design_binding.dynamic_point_count must match the control registry")
        if list(map(str, design_binding.get("dynamic_point_ids") or [])) != [
            str(point.get("id") or "") for point in dynamic_points if isinstance(point, dict)
        ]:
            errors.append("design_binding.dynamic_point_ids must match the control registry order")
        for hit in participant_leakage_hits(candidate, dynamic_points):
            errors.append(
                f"participant-visible hidden dynamic identifier {hit['hidden_identifier']!r} "
                f"in {hit['path']}"
            )
    score_unit = str(design_binding.get("score_unit") or "")
    if score_unit == "causal_decision_group":
        if control_version != "7":
            errors.append("causal score unit requires dynamic registry version '7'")
        case_ir_ref = design_binding.get("case_ir")
        score_plan_ref = design_binding.get("score_plan")
        case_ir_payload: dict[str, Any] | None = None
        score_plan_payload: dict[str, Any] | None = None
        if case_ir_ref != "private/case_ir.json":
            errors.append("causal score unit requires design_binding.case_ir='private/case_ir.json'")
        if score_plan_ref != "private/score_plan.json":
            errors.append(
                "causal score unit requires design_binding.score_plan='private/score_plan.json'"
            )
        try:
            case_ir_payload = json.loads(
                (candidate / "private/case_ir.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"cannot load candidate Case IR: {exc}")
        else:
            errors.extend(
                f"candidate Case IR: {error}" for error in validate_case_ir(case_ir_payload)
            )
            if case_ir_payload.get("case_id") != family_id:
                errors.append("candidate Case IR case_id must match --family")
            if case_ir_payload.get("instance_id") != instance_id:
                errors.append("candidate Case IR instance_id must match candidate metadata")
        try:
            score_plan_payload = json.loads(
                (candidate / "private/score_plan.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"cannot load candidate score plan: {exc}")
        else:
            errors.extend(
                f"candidate score plan: {error}"
                for error in validate_score_plan(score_plan_payload)
            )
            planned_points = score_plan_payload.get("points") or []
            if planned_points != dynamic_points:
                errors.append(
                    "candidate score plan points must exactly match the dynamic control registry"
                )
        if case_ir_payload is not None and score_plan_payload is not None and family is not None:
            try:
                expected_score_plan = compile_score_plan(
                    case_ir_payload, str(family.get("control_prefix") or family_id),
                )
            except ValueError as exc:
                errors.append(f"cannot compile candidate Case IR: {exc}")
            else:
                if score_plan_payload != expected_score_plan:
                    errors.append(
                        "candidate score plan must be the exact deterministic compilation of Case IR"
                    )
    registered_dimensions = {
        str(point.get("dimension") or "")
        for point in dynamic_points if isinstance(point, dict)
    }
    if set(map(str, design_binding.get("dynamic_control_dimensions") or [])) != registered_dimensions:
        errors.append(
            "design_binding.dynamic_control_dimensions must match the case-specific registry"
        )
    if design_binding.get("score_policy_version") != SCORE_POLICY_VERSION:
        errors.append("design_binding.score_policy_version is stale")
    errors.extend(validate_case(case))
    errors.extend(validate_case_quality(root, candidate, require_contract=True))
    errors.extend(validate_sources(root, [case]))
    if family is not None:
        errors.extend(validate_case_registries(
            {
                **case.raw,
                "_registry_path": str(candidate / "task/tests/semantic_checks.json"),
                "_control_path": str(candidate / "task/tests/control_flow_checks.json"),
            },
            str(family.get("control_prefix") or family_id),
        ))
    errors.extend(validate_candidate_mutation_suite(root, candidate, family_id))
    if require_execution_evidence and isinstance(instance_id, str):
        errors.extend(validate_release_evidence(candidate, metadata, family_id, instance_id))
    return metadata, errors


def audit_candidate_instances(root: Path) -> dict[str, Any]:
    """Inventory the isolated candidate area without changing benchmark state."""
    candidate_root = root / "candidate_instances"
    rows: list[dict[str, Any]] = []
    if candidate_root.is_dir():
        for family_dir in sorted(path for path in candidate_root.iterdir() if path.is_dir()):
            for candidate in sorted(path for path in family_dir.iterdir() if path.is_dir()):
                metadata, errors = validate_candidate_instance(
                    root, family_dir.name, candidate,
                )
                promotion_eligible, promotion_error = candidate_promotion_eligibility(
                    metadata or {},
                )
                rows.append({
                    "family_id": family_dir.name,
                    "instance_id": str((metadata or {}).get("instance_id") or candidate.name),
                    "stage": (metadata or {}).get("stage", "missing_metadata"),
                    "gate_passed": not errors,
                    "error_count": len(errors),
                    "errors": errors,
                    "promotion_eligible": promotion_eligible,
                    "promotion_ineligibility_reason": promotion_error,
                    "path": str(candidate.resolve()),
                })
    return {
        "schema_version": "1",
        "candidate_count": len(rows),
        "gate_passed_count": sum(row["gate_passed"] for row in rows),
        "stage_counts": dict(sorted(Counter(
            str(row["stage"]) for row in rows
        ).items())),
        "candidates": rows,
    }
