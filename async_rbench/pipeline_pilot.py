"""Auditable, simulation-only end-to-end case-production pilot.

The pilot consumes an already completed strict trajectory screen, renders the
same blind review material that would be sent to annotators, creates explicitly
synthetic answers to exercise routing, and scaffolds one non-promotable case.
It is a mechanics test, never evidence of annotation accuracy or case validity.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .case_factory import (
    build_transformation_spec, candidate_promotion_eligibility,
    scaffold_candidate_instance,
    validate_candidate_instance,
)
from .simple_review import (
    render_simple_review_html,
    route_simple_review,
    validate_simple_review_record,
)
from .evaluation.weighting import SCORE_POLICY_VERSION


SIMULATION_ORIGIN = "simulated_pipeline_validation"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values),
        encoding="utf-8",
    )


def validate_screening_report(report: dict[str, Any]) -> list[str]:
    """Validate conservation and minimum audit fields of a strict screen."""
    errors: list[str] = []
    source = report.get("source") or {}
    normalization = report.get("normalization") or {}
    screen = report.get("strict_screen") or {}
    human = report.get("human_review") or {}
    source_count = source.get("trajectory_count")
    if source_count is None:
        subset = str(source.get("authoritative_subset") or "")
        digits = "".join(ch if ch.isdigit() else " " for ch in subset).split()
        source_count = int(digits[0]) if digits else None
    prepared = normalization.get("prepared_count")
    normalization_failures = normalization.get(
        "normalization_failure_count", normalization.get("failure_count")
    )
    screened = screen.get("screened_trajectory_count", screen.get("screened_count"))
    screening_failures = screen.get("screening_failure_count", 0)
    if not all(isinstance(value, int) for value in (source_count, prepared, normalization_failures)):
        errors.append("screening report lacks integer source/normalization conservation counts")
    elif source_count != prepared + normalization_failures:
        errors.append("source count does not equal prepared plus normalization failures")
    if not all(isinstance(value, int) for value in (prepared, screened, screening_failures)):
        errors.append("screening report lacks integer prepared/screened/failure counts")
    elif prepared != screened + screening_failures:
        errors.append("prepared count does not equal screened plus screening failures")
    for field in ("candidate_decision_count", "reject_reason_counts"):
        if field not in screen:
            errors.append(f"strict_screen.{field} is required")
    for field in ("main_count", "boundary_count"):
        if not isinstance(human.get(field), int):
            errors.append(f"human_review.{field} must be an integer")
    validation = report.get("validation") or {}
    for field in ("count_conservation", "step_ids_exist", "step_order_valid", "review_pages_blind"):
        if validation and validation.get(field) is not True:
            errors.append(f"screening validation {field} must pass")
    return errors


def simulate_review_annotations(
    records: Iterable[dict[str, Any]], confirmed_ids: set[str], reviewer_id: str,
) -> list[dict[str, Any]]:
    """Create disclosed synthetic answers for routing/integration tests only."""
    annotations: list[dict[str, Any]] = []
    for record in records:
        review_id = str(record.get("review_id") or "")
        errors = validate_simple_review_record(record)
        if errors:
            raise ValueError(f"invalid review record {review_id!r}: {errors}")
        answers = {
            "late_after_work_started": "yes",
            "requires_plan_change": "yes" if review_id in confirmed_ids else "no",
            "evidence_is_faithful": "yes",
        }
        route = route_simple_review(answers, [])
        annotations.append({
            "schema_version": "2",
            "review_id": review_id,
            "reviewer_id": reviewer_id,
            "review_origin": SIMULATION_ORIGIN,
            "answers": answers,
            **route,
            "review_seconds": None,
            "simulation_disclosure": (
                "Synthetic choices used only to exercise pipeline routing; "
                "not a human judgment and not benchmark evidence."
            ),
        })
    return annotations


promotion_eligibility = candidate_promotion_eligibility


def run_pipeline_pilot(root: Path, config_path: Path, output: Path) -> dict[str, Any]:
    """Run screen-ingest -> review simulation -> case scaffold and static gate."""
    root = root.resolve()
    output = output.resolve()
    if output.exists():
        raise ValueError(f"pilot output already exists: {output}")
    config = _read_json(config_path.resolve())
    if config.get("schema_version") != "1.0":
        raise ValueError("pipeline pilot config must use schema_version 1.0")

    report_path = root / str(config["screening_report"])
    screening_report = _read_json(report_path)
    screening_errors = validate_screening_report(screening_report)
    if screening_errors:
        raise ValueError(f"strict screening report failed audit: {screening_errors}")

    records: list[dict[str, Any]] = []
    for relative in config.get("review_inputs") or []:
        value = _read_json(root / str(relative))
        if not isinstance(value, list):
            raise ValueError(f"review input must be a list: {relative}")
        records.extend(value)
    review_ids = [str(record.get("review_id") or "") for record in records]
    if len(set(review_ids)) != len(review_ids):
        raise ValueError("review inputs contain duplicate review_id values")

    confirmed_ids = {str(value) for value in config.get("simulated_confirmed_ids") or []}
    unknown_confirmed = sorted(confirmed_ids - set(review_ids))
    if unknown_confirmed:
        raise ValueError(f"simulation references unknown review ids: {unknown_confirmed}")
    annotations = simulate_review_annotations(
        records, confirmed_ids, str(config.get("simulated_reviewer_id") or "SIM-01"),
    )

    review_dir = output / "02-simulated-human-review"
    render_simple_review_html(records, review_dir / "review.html")
    _write_json(review_dir / "review-records.json", records)
    _write_jsonl(review_dir / "simulated-annotations.jsonl", annotations)
    _write_json(review_dir / "SIMULATION-NOTICE.json", {
        "simulation_only": True,
        "not_human_annotation": True,
        "may_not_be_used_for_release": True,
        "purpose": "exercise review routing and downstream case-production mechanics",
    })

    selected_id = str(config.get("selected_review_id") or "")
    selected = next((record for record in records if record["review_id"] == selected_id), None)
    selected_annotation = next(
        (annotation for annotation in annotations if annotation["review_id"] == selected_id), None,
    )
    if selected is None or selected_annotation is None:
        raise ValueError("selected_review_id is not present in the review batch")
    if selected_annotation["route"] != "candidate_confirmed":
        raise ValueError("selected review did not route to candidate_confirmed")

    plan = dict(config.get("transformation_plan") or {})
    plan["review_id"] = selected_id
    approval = dict(plan.get("human_approval") or {})
    approval.update({
        "status": "approved",
        "origin": SIMULATION_ORIGIN,
        "scope": "mechanics-only pilot; independent human technical approval still required",
    })
    plan["human_approval"] = approval
    spec = build_transformation_spec(selected, [selected_annotation], plan)
    spec["policy"].update({
        "simulation_only": True,
        "promotion_eligible": False,
        "requires_independent_human_rereview": True,
    })

    transformation_dir = output / "03-transformation"
    _write_json(transformation_dir / "selected-review-record.json", selected)
    _write_jsonl(transformation_dir / "selected-simulated-annotation.jsonl", [selected_annotation])
    _write_json(transformation_dir / "transformation-plan.json", plan)
    _write_json(transformation_dir / "transformation-spec.json", spec)

    candidate = scaffold_candidate_instance(root, spec)
    metadata_path = candidate / "candidate_metadata.json"
    metadata = _read_json(metadata_path)
    metadata["pilot_validation"] = {
        "simulated_review": True,
        "promotion_eligible": False,
        "requires_independent_human_rereview": True,
        "pipeline_artifact": str(output.relative_to(root)).replace("\\", "/"),
    }
    _write_json(metadata_path, metadata)
    _, static_errors = validate_candidate_instance(
        root, str(plan["target_family"]), candidate, require_execution_evidence=False,
    )

    route_counts = dict(sorted(Counter(annotation["route"] for annotation in annotations).items()))
    source = screening_report.get("source") or {}
    screen = screening_report.get("strict_screen") or {}
    result = {
        "schema_version": "1.0",
        "status": "static_gate_pass" if not static_errors else "static_gate_fail",
        "scope": "simulation-only pipeline mechanics validation",
        "claims": {
            "strict_screen_reused": True,
            "human_accuracy_validated": False,
            "case_scaffolded": True,
            "case_promotable": False,
            "oracle_and_hidden_verifier_executed": False,
        },
        "screening": {
            "source": source,
            "screened_count": screen.get("screened_trajectory_count", screen.get("screened_count")),
            "candidate_decision_count": screen.get("candidate_decision_count"),
            "audit_errors": [],
        },
        "review_simulation": {
            "record_count": len(records),
            "route_counts": route_counts,
            "confirmed_ids": sorted(confirmed_ids),
            "selected_review_id": selected_id,
        },
        "case_production": {
            "family_id": plan["target_family"],
            "instance_id": plan["instance_id"],
            "candidate_path": str(candidate),
            "static_gate_passed": not static_errors,
            "static_gate_errors": static_errors,
            "promotion_eligible": False,
            "score_policy_version": SCORE_POLICY_VERSION,
            "primary_metric": "dynamic_control_score",
            "required_dynamic_dimensions": [
                "event_intake", "state_revision", "plan_revision", "closure",
            ],
        },
        "next_required_step": "execute instance-preflight, then retain candidate as pilot-only",
    }
    _write_json(output / "pipeline-report.json", result)
    return result
