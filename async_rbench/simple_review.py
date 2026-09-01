"""Choice-only human verification of trajectory screening."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSIONS = {"2", "3"}
LEGACY_QUESTION_IDS = (
    "late_after_work_started",
    "requires_plan_change",
    "evidence_is_faithful",
)
QUESTION_IDS = (
    "independent_async_source",
    *LEGACY_QUESTION_IDS,
)
ANSWER_VALUES = frozenset({"yes", "no", "uncertain"})
EVIDENCE_PARTS = frozenset({"prior_work", "late_information", "affected_action"})


def build_blind_calibration_batch(
    candidates: Iterable[dict[str, Any]],
    audit_controls: Iterable[dict[str, Any]],
    *,
    candidate_limit: int = 42,
    audit_limit: int = 8,
    seed: str = "dtbench-calibration-v1",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Mix candidate and hard-control cards without exposing their source stratum."""
    selected: list[tuple[str, dict[str, Any]]] = []
    for stratum, values, limit in (
        ("candidate", list(candidates), candidate_limit),
        ("hard_negative_control", list(audit_controls), audit_limit),
    ):
        if limit < 0:
            raise ValueError("calibration limits must be non-negative")
        for record in values[:limit]:
            errors = validate_simple_review_record(record)
            if errors:
                raise ValueError(f"invalid {stratum} review record: {errors}")
            selected.append((stratum, record))
    selected.sort(key=lambda item: hashlib.sha256(
        f"{seed}:{item[0]}:{item[1]['review_id']}".encode("utf-8")
    ).hexdigest())
    public_records: list[dict[str, Any]] = []
    source_map: list[dict[str, Any]] = []
    for ordinal, (stratum, source_record) in enumerate(selected, 1):
        record = json.loads(json.dumps(source_record, ensure_ascii=False))
        original_id = str(record["review_id"])
        blind_id = f"pilot-review-{ordinal:03d}"
        record["review_id"] = blind_id
        record["review_round"] = 1
        record["source"] = {
            "benchmark": "blinded-source",
            "task_id": blind_id,
            "trajectory_id": blind_id,
        }
        public_records.append(record)
        source_map.append({
            "blind_review_id": blind_id,
            "source_review_id": original_id,
            "stratum": stratum,
        })
    return public_records, source_map


def validate_simple_review_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if str(record.get("schema_version")) not in SCHEMA_VERSIONS:
        errors.append("schema_version must be '2' or '3'")
    for field in ("review_id", "task_goal"):
        if not str(record.get(field) or "").strip():
            errors.append(f"{field} must be a non-empty string")
    source = record.get("source")
    if not isinstance(source, dict):
        errors.append("source must be an object")
    else:
        for field in ("benchmark", "task_id", "trajectory_id"):
            if not str(source.get(field) or "").strip():
                errors.append(f"source.{field} must be a non-empty string")
    evidence = record.get("evidence_card")
    if not isinstance(evidence, dict):
        errors.append("evidence_card must be an object")
        return errors
    for field in ("prior_work", "late_information", "affected_action"):
        item = evidence.get(field)
        if not isinstance(item, dict):
            errors.append(f"evidence_card.{field} must be an object")
            continue
        if not str(item.get("summary") or "").strip():
            errors.append(f"evidence_card.{field}.summary is required")
        excerpts = item.get("excerpts")
        if not isinstance(excerpts, list) or not excerpts:
            errors.append(f"evidence_card.{field}.excerpts must be non-empty")
            continue
        for index, excerpt in enumerate(excerpts):
            if not isinstance(excerpt, dict):
                errors.append(f"evidence_card.{field}.excerpts[{index}] must be an object")
                continue
            for excerpt_field in ("step_id", "actor", "text"):
                if not str(excerpt.get(excerpt_field) or "").strip():
                    errors.append(
                        f"evidence_card.{field}.excerpts[{index}].{excerpt_field} is required"
                    )
    context = evidence.get("expanded_context")
    if context is not None:
        if not isinstance(context, list):
            errors.append("evidence_card.expanded_context must be a list")
        else:
            for index, excerpt in enumerate(context):
                if not isinstance(excerpt, dict):
                    errors.append(f"evidence_card.expanded_context[{index}] must be an object")
                    continue
                for excerpt_field in ("step_id", "actor", "text"):
                    if not str(excerpt.get(excerpt_field) or "").strip():
                        errors.append(
                            f"evidence_card.expanded_context[{index}].{excerpt_field} is required"
                        )
    return errors


def route_simple_review(
    answers: dict[str, str], evidence_problem_parts: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Route one completed screening-verification review by failure type."""
    question_ids = QUESTION_IDS if "independent_async_source" in answers else LEGACY_QUESTION_IDS
    missing = [question for question in question_ids if question not in answers]
    invalid = {
        question: value for question, value in answers.items()
        if question in question_ids and value not in ANSWER_VALUES
    }
    if missing or invalid:
        raise ValueError(f"incomplete or invalid review answers: missing={missing}, invalid={invalid}")
    unknown = sorted(set(answers) - set(question_ids))
    if unknown:
        raise ValueError(f"unknown review questions: {unknown}")
    problem_parts = sorted(set(evidence_problem_parts or []))
    invalid_parts = sorted(set(problem_parts) - EVIDENCE_PARTS)
    if invalid_parts:
        raise ValueError(f"invalid evidence problem parts: {invalid_parts}")
    uncertainty_questions = [
        question for question in question_ids if answers[question] == "uncertain"
    ]
    if uncertainty_questions:
        route = "uncertain_pool"
        reason_codes = [f"uncertain:{question}" for question in uncertainty_questions]
    elif answers["evidence_is_faithful"] == "no":
        if not problem_parts:
            raise ValueError("evidence_problem_parts is required when evidence_is_faithful is no")
        route = "needs_reextraction"
        reason_codes = [f"evidence_mismatch:{part}" for part in problem_parts]
    elif answers.get("independent_async_source") == "no":
        route = "ordinary_sequential_observation"
        reason_codes = ["not_independent_async_source"]
    elif answers["late_after_work_started"] == "no":
        route = "not_late_event"
        reason_codes = ["not_late_event"]
    elif answers["requires_plan_change"] == "no":
        route = "no_replanning_need"
        reason_codes = ["no_replanning_need"]
    else:
        route = "candidate_confirmed"
        reason_codes = []
    return {
        "route": route,
        "uncertainty_questions": uncertainty_questions,
        "evidence_problem_parts": problem_parts,
        "reason_codes": reason_codes,
    }


def collect_uncertain_records(
    records: Iterable[dict[str, Any]], annotations: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a blind second-round queue from verified uncertain annotations."""
    records_by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        errors = validate_simple_review_record(record)
        if errors:
            raise ValueError(f"invalid simple review record {record.get('review_id')!r}: {errors}")
        review_id = str(record["review_id"])
        if review_id in records_by_id:
            raise ValueError(f"duplicate review_id in source records: {review_id!r}")
        records_by_id[review_id] = record
    queued: list[dict[str, Any]] = []
    seen_annotations: set[str] = set()
    for annotation in annotations:
        review_id = str(annotation.get("review_id") or "")
        if not review_id or review_id in seen_annotations:
            raise ValueError(f"annotation review_id must be non-empty and unique: {review_id!r}")
        seen_annotations.add(review_id)
        if review_id not in records_by_id:
            raise ValueError(f"annotation references unknown review_id: {review_id!r}")
        answers = annotation.get("answers")
        if not isinstance(answers, dict):
            raise ValueError(f"annotation {review_id!r} answers must be an object")
        problem_parts = annotation.get("evidence_problem_parts")
        if problem_parts is not None and not isinstance(problem_parts, list):
            raise ValueError(f"annotation {review_id!r} evidence_problem_parts must be a list")
        computed = route_simple_review(
            {str(key): str(value) for key, value in answers.items()},
            [str(value) for value in problem_parts or []],
        )
        claimed_route = annotation.get("route")
        if claimed_route is not None and claimed_route != computed["route"]:
            raise ValueError(f"annotation {review_id!r} route does not match its answers")
        if computed["route"] != "uncertain_pool":
            continue
        copy = json.loads(json.dumps(records_by_id[review_id]))
        copy["review_round"] = int(copy.get("review_round") or 1) + 1
        copy["rereview"] = {
            "blind": True,
            "show_expanded_context": True,
            "source_annotation_retained_separately": True,
        }
        queued.append(copy)
    return queued


def audit_paired_reviews(
    records: Iterable[dict[str, Any]],
    annotations: Iterable[dict[str, Any]],
    source_map: Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate a two-reviewer blind batch and prepare its adjudication queue."""
    record_list = list(records)
    records_by_id = {str(item.get("review_id") or ""): item for item in record_list}
    if len(records_by_id) != len(record_list) or "" in records_by_id:
        raise ValueError("review records must have unique non-empty review_id values")
    for review_id, record in records_by_id.items():
        errors = validate_simple_review_record(record)
        if errors:
            raise ValueError(f"invalid review record {review_id!r}: {errors}")
    strata = {
        str(item.get("blind_review_id") or ""): str(item.get("stratum") or "")
        for item in source_map
    }
    if set(strata) != set(records_by_id):
        raise ValueError("source map must cover every blind review id exactly once")

    annotations_by_record: dict[str, list[dict[str, Any]]] = {
        review_id: [] for review_id in records_by_id
    }
    reviewer_ids: set[str] = set()
    validation_errors: list[str] = []
    for annotation in annotations:
        review_id = str(annotation.get("review_id") or "")
        reviewer_id = str(annotation.get("reviewer_id") or "").strip()
        if review_id not in annotations_by_record:
            validation_errors.append(f"unknown review_id:{review_id}")
            continue
        if not reviewer_id:
            validation_errors.append(f"missing reviewer_id:{review_id}")
            continue
        reviewer_ids.add(reviewer_id)
        answers = annotation.get("answers")
        if not isinstance(answers, dict):
            validation_errors.append(f"invalid answers:{review_id}:{reviewer_id}")
            continue
        try:
            computed = route_simple_review(
                {str(key): str(value) for key, value in answers.items()},
                [str(value) for value in annotation.get("evidence_problem_parts") or []],
            )
        except ValueError as exc:
            validation_errors.append(f"invalid annotation:{review_id}:{reviewer_id}:{exc}")
            continue
        if annotation.get("route") not in {None, computed["route"]}:
            validation_errors.append(f"route mismatch:{review_id}:{reviewer_id}")
            continue
        annotations_by_record[review_id].append({**annotation, **computed})

    duplicate_pairs: list[str] = []
    incomplete_records: list[str] = []
    disagreements: list[str] = []
    uncertainty_records: list[str] = []
    evidence_problem_records: list[str] = []
    unanimously_confirmed: list[str] = []
    matching_answers = 0
    answer_comparisons = 0
    for review_id, pair in annotations_by_record.items():
        pair_reviewers = [str(item["reviewer_id"]).strip() for item in pair]
        if len(pair_reviewers) != len(set(pair_reviewers)):
            duplicate_pairs.append(review_id)
        if len(pair) != 2 or len(set(pair_reviewers)) != 2:
            incomplete_records.append(review_id)
            continue
        pair_disagrees = False
        for question in QUESTION_IDS:
            answer_comparisons += 1
            values = [str(item["answers"].get(question) or "") for item in pair]
            if values[0] == values[1]:
                matching_answers += 1
            else:
                pair_disagrees = True
            if "uncertain" in values:
                uncertainty_records.append(review_id)
        if pair_disagrees:
            disagreements.append(review_id)
        if any(item["route"] == "needs_reextraction" for item in pair):
            evidence_problem_records.append(review_id)
        if all(item["route"] == "candidate_confirmed" for item in pair):
            unanimously_confirmed.append(review_id)

    rereview_ids = sorted(set(
        disagreements + uncertainty_records + evidence_problem_records
    ))
    rereview_records: list[dict[str, Any]] = []
    for review_id in rereview_ids:
        record = json.loads(json.dumps(records_by_id[review_id], ensure_ascii=False))
        record["review_round"] = 2
        record["rereview"] = {
            "blind": True,
            "show_expanded_context": True,
            "source_annotation_retained_separately": True,
        }
        rereview_records.append(record)
    agreement = matching_answers / answer_comparisons if answer_comparisons else 0.0
    control_ids = {review_id for review_id, stratum in strata.items()
                   if stratum == "hard_negative_control"}
    control_false_positives = sorted(control_ids.intersection(unanimously_confirmed))
    complete = (
        len(reviewer_ids) == 2
        and not validation_errors
        and not duplicate_pairs
        and not incomplete_records
    )
    report = {
        "schema_version": "1.0",
        "record_count": len(record_list),
        "reviewer_ids": sorted(reviewer_ids),
        "complete_two_reviewer_batch": complete,
        "validation_errors": validation_errors,
        "duplicate_reviewer_records": sorted(duplicate_pairs),
        "incomplete_records": sorted(incomplete_records),
        "raw_question_agreement": round(agreement, 6),
        "disagreement_records": sorted(set(disagreements)),
        "uncertainty_records": sorted(set(uncertainty_records)),
        "evidence_problem_records": sorted(set(evidence_problem_records)),
        "rereview_record_count": len(rereview_ids),
        "unanimously_confirmed_count": len(unanimously_confirmed),
        "hidden_control_count": len(control_ids),
        "hidden_control_false_positive_count": len(control_false_positives),
        "hidden_control_false_positive_ids": control_false_positives,
        "pilot_gates": {
            "complete": complete,
            "agreement_at_least_0_85": agreement >= 0.85,
            "control_false_positives_at_most_1": len(control_false_positives) <= 1,
            "adjudication_queue_empty": not rereview_ids,
        },
    }
    report["ready_for_case_design"] = all(report["pilot_gates"].values())
    return report, rereview_records


def simulate_paired_calibration_reviews(
    records: Iterable[dict[str, Any]],
    source_map: Iterable[dict[str, Any]],
    *,
    reviewer_ids: tuple[str, str] = ("SIM-A", "SIM-B"),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Generate disclosed synthetic choices for an integration test, never release evidence."""
    if len(set(reviewer_ids)) != 2 or any(not value.strip() for value in reviewer_ids):
        raise ValueError("simulation requires two distinct non-empty reviewer ids")
    strata = {
        str(item.get("blind_review_id") or ""): str(item.get("stratum") or "")
        for item in source_map
    }
    record_list = list(records)
    if set(strata) != {str(item.get("review_id") or "") for item in record_list}:
        raise ValueError("source map must cover every simulated review record")
    batches: list[list[dict[str, Any]]] = []
    for reviewer_id in reviewer_ids:
        batch: list[dict[str, Any]] = []
        for record in record_list:
            review_id = str(record.get("review_id") or "")
            errors = validate_simple_review_record(record)
            if errors:
                raise ValueError(f"invalid review record {review_id!r}: {errors}")
            is_control = strata[review_id] == "hard_negative_control"
            answers = {
                "independent_async_source": "no" if is_control else "yes",
                "late_after_work_started": "yes",
                "requires_plan_change": "yes",
                "evidence_is_faithful": "yes",
            }
            routed = route_simple_review(answers, [])
            batch.append({
                "schema_version": "3",
                "review_id": review_id,
                "reviewer_id": reviewer_id,
                "review_origin": "simulated_pipeline_validation",
                "answers": answers,
                **routed,
                "review_seconds": None,
                "simulation_disclosure": (
                    "Synthetic choices used only to exercise the production pipeline; "
                    "not a human judgment and not valid benchmark evidence."
                ),
            })
        batches.append(batch)
    return batches[0], batches[1]


_BLIND_MARKERS = re.compile(
    r"(?i)(openhands(?:-venv)?|mini[- ]?swe[- ]?agent|terminus2|"
    r"anthropic|claude|openai|gpt[- ]?5|deepseek|qwen|moonshot|kimi)"
)


def _blind_text(value: Any, limit: int = 520) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = _BLIND_MARKERS.sub("执行环境", text)
    return text[:limit] + ("…" if len(text) > limit else "")


def _step_excerpt(step: dict[str, Any]) -> dict[str, str]:
    text = next(
        (
            cleaned for value in (
                step.get("command"), step.get("content"), step.get("source_ref"),
            ) if (cleaned := _blind_text(value))
        ),
        f"轨迹记录了一次{step.get('kind') or '操作'}步骤",
    )
    return {
        "step_id": str(step["step_id"]),
        "actor": _blind_text(step.get("role") or step.get("kind") or "轨迹记录", 40),
        "text": text,
    }


def build_simple_review_batch(
    normalized_trajectories: Iterable[dict[str, Any]],
    decision_candidates: Iterable[dict[str, Any]],
    *,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Build one neutral near-miss evidence card per trajectory.

    The source/model identity is retained only in the returned internal mapping.
    Review records use stable blind IDs and never expose the screening verdict.
    """
    normalized = {
        str(row.get("review_id") or ""): row for row in normalized_trajectories
        if str(row.get("review_id") or "")
    }
    by_trajectory: dict[str, list[dict[str, Any]]] = {}
    for decision in decision_candidates:
        review_id = str(decision.get("trajectory_review_id") or "")
        if review_id in normalized:
            by_trajectory.setdefault(review_id, []).append(decision)
    priority = {
        "conflicting_results": 0, "stale_result_risk": 1, "cancellation": 2,
        "downstream_invalidation": 3, "late_authoritative_result": 4,
        "reverification": 5,
    }
    selected: list[tuple[str, dict[str, Any]]] = []
    for review_id, decisions in sorted(by_trajectory.items()):
        best = sorted(
            decisions,
            key=lambda row: (
                priority.get(str((row.get("agent_proposal") or {}).get("event_type")), 99),
                str(row.get("decision_id") or ""),
            ),
        )[0]
        selected.append((review_id, best))
    records: list[dict[str, Any]] = []
    source_map: list[dict[str, str]] = []
    for ordinal, (review_id, decision) in enumerate(selected[:limit], 1):
        trajectory = normalized[review_id]
        steps = {
            int(step["step_id"]): step for step in trajectory.get("steps") or []
            if isinstance(step, dict) and isinstance(step.get("step_id"), int)
        }
        proposal = decision.get("agent_proposal") or {}
        trigger_ids = list(map(int, proposal.get("trigger_step_ids") or []))
        response_ids = list(map(int, proposal.get("response_step_ids") or []))
        if not trigger_ids or not response_ids or trigger_ids[0] not in steps or response_ids[0] not in steps:
            continue
        trigger_id, response_id = trigger_ids[0], response_ids[0]
        prior_ids = [
            int(value) for value in proposal.get("precondition_step_ids") or []
            if int(value) in steps and int(value) < trigger_id
        ]
        if not prior_ids:
            prior_ids = [
                step_id for step_id, step in steps.items()
                if step_id < trigger_id and step.get("kind") in {"action", "task", "final"}
            ]
        if not prior_ids:
            prior_ids = [step_id for step_id in steps if step_id < trigger_id]
        if not prior_ids:
            continue
        prior_id = max(prior_ids)
        context_ids = sorted({
            step_id for step_id in steps
            if max(1, trigger_id - 2) <= step_id <= response_id + 2
        })[:6]
        blind_id = f"calibration-b001-{ordinal:03d}"
        result = trajectory.get("result") or {}
        task_goal = _blind_text(
            result.get("instruction") or trajectory.get("task_name") or "完成给定任务", 700
        )
        records.append({
            "schema_version": "3",
            "review_id": blind_id,
            "review_round": 1,
            "source": {
                "benchmark": "terminal-bench",
                "task_id": str(trajectory.get("task_name") or "task"),
                "trajectory_id": blind_id,
            },
            "task_goal": task_goal,
            "evidence_card": {
                "prior_work": {
                    "summary": f"步骤 {prior_id} 记录了此前已执行或正在进行的工作。",
                    "excerpts": [_step_excerpt(steps[prior_id])],
                },
                "late_information": {
                    "summary": f"步骤 {trigger_id} 随后返回了新的观察结果。",
                    "excerpts": [_step_excerpt(steps[trigger_id])],
                },
                "affected_action": {
                    "summary": f"步骤 {response_id} 记录了观察结果之后采取的动作。",
                    "excerpts": [_step_excerpt(steps[response_id])],
                },
                "expanded_context": [_step_excerpt(steps[value]) for value in context_ids],
            },
        })
        source = trajectory.get("source") or {}
        source_map.append({
            "blind_review_id": blind_id,
            "source_review_id": review_id,
            "decision_id": str(decision.get("decision_id") or ""),
            "source_agent": str(trajectory.get("source_agent") or source.get("agent") or ""),
            "source_model": str(trajectory.get("source_model") or source.get("model") or ""),
        })
    return records, source_map


def _json_for_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def render_simple_review_html(records: Iterable[dict[str, Any]], output: Path) -> None:
    rows = list(records)
    failures = [
        {"index": index, "errors": validate_simple_review_record(record)}
        for index, record in enumerate(rows, 1)
        if validate_simple_review_record(record)
    ]
    if failures:
        raise ValueError(f"invalid simple review records: {failures}")
    if not rows:
        raise ValueError("simple review input must contain at least one record")
    template = _HTML_TEMPLATE.replace("__REVIEW_RECORDS__", _json_for_script(rows))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template, encoding="utf-8")


_HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Async-RBench 关键轨迹复核</title>
<style>
:root { color-scheme: light dark; font-family: Inter, "Microsoft YaHei", system-ui, sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; color: light-dark(#182235, #edf3ff); background: light-dark(#f3f6fa, #111827); }
.shell { max-width: 1120px; margin: 20px auto; background: light-dark(#fff, #1c2738); border: 1px solid light-dark(#d9e1ec, #39475c); border-radius: 14px; overflow: hidden; }
.top, .bottom { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 18px; background: light-dark(#fafcff, #222e42); }
.top { border-bottom: 1px solid light-dark(#e4e9f1, #39475c); }
.bottom { border-top: 1px solid light-dark(#e4e9f1, #39475c); }
.title { font-weight: 600; }
.muted, .refs { color: light-dark(#667085, #bbc7d9); }
.body { padding: 18px; }
.goal { padding: 11px 13px; margin-bottom: 12px; background: light-dark(#f5f7fb, #263247); border-radius: 8px; }
.evidence-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 16px 0 18px; }
.evidence-item { min-width: 0; padding: 13px; border: 1px solid light-dark(#d9e1ec, #39475c); border-radius: 10px; }
.evidence-title { margin-bottom: 8px; color: light-dark(#5268ad, #aab9f3); font-weight: 600; }
.summary-text { margin: 0 0 9px; }
.excerpt { margin: 0; padding-top: 9px; border-top: 1px solid light-dark(#edf0f5, #344055); color: light-dark(#667085, #bbc7d9); }
.excerpt + .excerpt { margin-top: 8px; }
details { margin-bottom: 14px; }
summary { cursor: pointer; color: light-dark(#5268ad, #aab9f3); }
.expanded-list { padding-left: 22px; color: light-dark(#667085, #bbc7d9); }
.question { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 14px; align-items: center; padding: 13px 0; border-top: 1px solid light-dark(#edf0f5, #344055); }
.question p { margin: 0; }
.choices { display: grid; grid-template-columns: repeat(3, minmax(78px, 1fr)); gap: 6px; }
button { min-height: 42px; border: 1px solid light-dark(#ccd5e2, #4a5870); border-radius: 8px; color: inherit; background: light-dark(#fff, #28354b); cursor: pointer; }
button[aria-pressed="true"] { background: light-dark(#e8edff, #364d7e); border-color: light-dark(#6078d0, #9aacf2); }
button.primary { padding: 0 18px; color: light-dark(#fff, #111827); background: light-dark(#314fba, #a9b9f8); border-color: transparent; }
button:disabled { opacity: .45; cursor: not-allowed; }
.followup { display: none; margin: 0 0 12px; padding: 11px 13px; background: light-dark(#f5f7fb, #263247); border-radius: 8px; }
.followup.visible { display: block; }
.part-choices { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 9px; }
.status-warning { color: light-dark(#6b4b00, #ffd994); }
.actions { display: flex; gap: 8px; }
.reviewer { display: flex; align-items: center; gap: 7px; }
.reviewer input { width: 150px; padding: 7px 9px; border: 1px solid light-dark(#ccd5e2, #4a5870); border-radius: 7px; color: inherit; background: light-dark(#fff, #28354b); }
@media (max-width: 700px) {
  .shell { margin: 8px; }
  .evidence-grid { grid-template-columns: 1fr; }
  .question { grid-template-columns: 1fr; }
  .choices { grid-template-columns: repeat(3, 1fr); }
  button { min-height: 44px; }
  .bottom { flex-direction: column; align-items: stretch; }
  .actions { display: grid; grid-template-columns: 1fr 1fr; }
}
</style>
</head>
<body>
<section class="shell">
  <header class="top">
    <div class="title" id="page-title">关键轨迹复核</div>
    <div class="muted"><span id="position"></span> · <span id="answered">0 / 3</span></div>
  </header>
  <main class="body">
    <div class="goal"><strong>任务目标：</strong><span id="task-goal"></span></div>
    <div class="evidence-grid">
      <article class="evidence-item">
        <div class="evidence-title">① 此前计划或正在进行的工作</div>
        <p class="summary-text" id="prior-summary"></p>
        <div id="prior-excerpts"></div>
      </article>
      <article class="evidence-item">
        <div class="evidence-title">② 后来出现的关键新信息</div>
        <p class="summary-text" id="information-summary"></p>
        <div id="information-excerpts"></div>
      </article>
      <article class="evidence-item">
        <div class="evidence-title">③ 可能受影响的动作</div>
        <p class="summary-text" id="affected-summary"></p>
        <div id="affected-excerpts"></div>
      </article>
    </div>
    <details id="context-details"><summary>二次复核补充上下文</summary><ol class="expanded-list" id="expanded-context"></ol></details>

    <div class="question" data-question="independent_async_source"><p>1. 这条新信息是否可能由独立任务或外部环境产生，并在其他工作继续时单独到达？</p><div class="choices"><button data-value="yes">是，独立到达</button><button data-value="no">否，顺序返回</button><button data-value="uncertain">不确定</button></div></div>
    <div class="question" data-question="late_after_work_started"><p>2. 关键新信息是否在相关计划已经形成或工作已经开始之后才出现？</p><div class="choices"><button data-value="yes">是，后到信息</button><button data-value="no">否，之前已知</button><button data-value="uncertain">不确定</button></div></div>
    <div class="question" data-question="requires_plan_change"><p>3. 收到新信息后，是否至少需要改变、取消、补做或重新确认一个动作？</p><div class="choices"><button data-value="yes">是，需要调整</button><button data-value="no">否，可以照旧</button><button data-value="uncertain">不确定</button></div></div>
    <div class="question" data-question="evidence_is_faithful"><p>4. 上面三段简述是否都能从引用的原始轨迹中直接得到？</p><div class="choices"><button data-value="yes">是，证据支持</button><button data-value="no">否，描述不符</button><button data-value="uncertain">不确定</button></div></div>
    <div class="followup" id="evidence-parts"><div>哪一部分存在问题？（可多选）</div><div class="part-choices"><button data-part="prior_work">此前计划</button><button data-part="late_information">关键新信息</button><button data-part="affected_action">受影响动作</button></div></div>
  </main>
  <footer class="bottom">
    <div><label class="reviewer">标注员编号 <input id="reviewer-id" autocomplete="off"></label><div class="muted" id="review-status" aria-live="polite"></div></div>
    <div class="actions"><button id="download">下载标注结果</button><button class="primary" id="submit" disabled>提交并看下一条</button></div>
  </footer>
</section>
<script>
const records = __REVIEW_RECORDS__;
const legacyQuestionIds = ['late_after_work_started', 'requires_plan_change', 'evidence_is_faithful'];
const currentQuestionIds = () => String(records[index].schema_version) === '3' ? ['independent_async_source', ...legacyQuestionIds] : legacyQuestionIds;
let index = 0;
let startedAt = Date.now();
const answers = {};
const evidenceProblems = {};
const annotations = [];
const byId = (id) => document.getElementById(id);

function setText(id, text) { byId(id).textContent = text || ''; }
function currentAnswers() { return answers[records[index].review_id] || (answers[records[index].review_id] = {}); }
function currentProblems() { return evidenceProblems[records[index].review_id] || (evidenceProblems[records[index].review_id] = []); }
function route(values, problemParts) {
  const questionIds = currentQuestionIds();
  const uncertain = questionIds.filter((id) => values[id] === 'uncertain');
  if (uncertain.length) return {route: 'uncertain_pool', uncertainty_questions: uncertain, evidence_problem_parts: problemParts, reason_codes: uncertain.map((id) => `uncertain:${id}`)};
  if (values.evidence_is_faithful === 'no') return {route: 'needs_reextraction', uncertainty_questions: [], evidence_problem_parts: problemParts, reason_codes: problemParts.map((part) => `evidence_mismatch:${part}`)};
  if (values.independent_async_source === 'no') return {route: 'ordinary_sequential_observation', uncertainty_questions: [], evidence_problem_parts: [], reason_codes: ['not_independent_async_source']};
  if (values.late_after_work_started === 'no') return {route: 'not_late_event', uncertainty_questions: [], evidence_problem_parts: [], reason_codes: ['not_late_event']};
  if (values.requires_plan_change === 'no') return {route: 'no_replanning_need', uncertainty_questions: [], evidence_problem_parts: [], reason_codes: ['no_replanning_need']};
  return {route: 'candidate_confirmed', uncertainty_questions: [], evidence_problem_parts: [], reason_codes: []};
}
function renderExcerpts(id, excerpts) {
  const container = byId(id);
  container.replaceChildren(...excerpts.map((excerpt) => {
    const paragraph = document.createElement('p');
    paragraph.className = 'excerpt';
    paragraph.textContent = `步骤 ${excerpt.step_id} · ${excerpt.actor}：“${excerpt.text}”`;
    return paragraph;
  }));
}
function updateState() {
  const values = currentAnswers();
  const questionIds = currentQuestionIds();
  const count = questionIds.filter((id) => values[id]).length;
  const reviewerReady = byId('reviewer-id').value.trim().length > 0;
  const needsParts = values.evidence_is_faithful === 'no';
  const partsComplete = !needsParts || currentProblems().length > 0;
  setText('answered', `${count} / ${questionIds.length}`);
  byId('submit').disabled = count !== questionIds.length || !partsComplete || !reviewerReady;
  byId('evidence-parts').classList.toggle('visible', needsParts);
  const uncertain = Object.values(values).includes('uncertain');
  byId('review-status').classList.toggle('status-warning', uncertain);
  if (!reviewerReady) setText('review-status', '');
  else if (count !== questionIds.length) setText('review-status', `已回答 ${count} / ${questionIds.length} 题。`);
  else if (!partsComplete) setText('review-status', '请指出描述不符的位置。');
  else if (uncertain) setText('review-status', '提交后将进入扩展上下文复核。');
  else setText('review-status', '选择题已完成，可以提交。');
}
function render() {
  const record = records[index];
  const evidence = record.evidence_card;
  setText('position', `第 ${index + 1} / ${records.length} 条`);
  setText('page-title', Number(record.review_round || 1) > 1 ? '关键轨迹二次复核' : '关键轨迹复核');
  setText('task-goal', record.task_goal);
  setText('prior-summary', evidence.prior_work.summary);
  setText('information-summary', evidence.late_information.summary);
  setText('affected-summary', evidence.affected_action.summary);
  renderExcerpts('prior-excerpts', evidence.prior_work.excerpts);
  renderExcerpts('information-excerpts', evidence.late_information.excerpts);
  renderExcerpts('affected-excerpts', evidence.affected_action.excerpts);
  const expanded = evidence.expanded_context || [];
  byId('expanded-context').replaceChildren(...expanded.map((excerpt) => {
    const item = document.createElement('li');
    item.textContent = `步骤 ${excerpt.step_id} · ${excerpt.actor}：“${excerpt.text}”`;
    return item;
  }));
  byId('context-details').hidden = !(record.rereview && record.rereview.show_expanded_context);
  byId('context-details').open = !byId('context-details').hidden;
  document.querySelectorAll('[data-question]').forEach((row) => {
    row.hidden = !currentQuestionIds().includes(row.dataset.question);
    const value = currentAnswers()[row.dataset.question];
    row.querySelectorAll('button').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.value === value)));
  });
  document.querySelectorAll('[data-part]').forEach((button) => button.setAttribute('aria-pressed', String(currentProblems().includes(button.dataset.part))));
  startedAt = Date.now();
  updateState();
}
document.querySelectorAll('[data-question] button').forEach((button) => {
  button.addEventListener('click', () => {
    const row = button.closest('[data-question]');
    currentAnswers()[row.dataset.question] = button.dataset.value;
    row.querySelectorAll('button').forEach((peer) => peer.setAttribute('aria-pressed', String(peer === button)));
    if (row.dataset.question === 'evidence_is_faithful' && button.dataset.value !== 'no') evidenceProblems[records[index].review_id] = [];
    updateState();
  });
});
document.querySelectorAll('[data-part]').forEach((button) => {
  button.addEventListener('click', () => {
    const parts = currentProblems();
    const position = parts.indexOf(button.dataset.part);
    if (position >= 0) parts.splice(position, 1); else parts.push(button.dataset.part);
    button.setAttribute('aria-pressed', String(position < 0));
    updateState();
  });
});
byId('submit').addEventListener('click', () => {
  const record = records[index];
  const values = {...currentAnswers()};
  const outcome = route(values, [...currentProblems()]);
  const existing = annotations.findIndex((item) => item.review_id === record.review_id);
  const annotation = {schema_version: String(record.schema_version), review_id: record.review_id, reviewer_id: byId('reviewer-id').value.trim(), review_origin: 'offline_review_page', answers: values, ...outcome, review_seconds: Math.max(1, Math.round((Date.now() - startedAt) / 1000))};
  if (existing >= 0) annotations[existing] = annotation; else annotations.push(annotation);
  if (index < records.length - 1) { index += 1; render(); }
  else { setText('review-status', `已记录 ${annotations.length} 条。审核页面不显示通过或淘汰结论。`); byId('submit').disabled = true; byId('submit').textContent = '已提交'; }
});
byId('download').addEventListener('click', () => {
  const text = annotations.map((item) => JSON.stringify(item)).join('\n') + (annotations.length ? '\n' : '');
  const url = URL.createObjectURL(new Blob([text], {type: 'application/x-ndjson'}));
  const reviewer = byId('reviewer-id').value.trim().replace(/[^0-9A-Za-z_-]+/g, '_') || 'unknown';
  const link = document.createElement('a'); link.href = url; link.download = `simple-review-annotations-${reviewer}.jsonl`; link.click(); URL.revokeObjectURL(url);
});
byId('reviewer-id').addEventListener('input', updateState);
render();
</script>
</body>
</html>
'''
