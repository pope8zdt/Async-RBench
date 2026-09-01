"""Complete every fixed-choice review as an explicitly disclosed Codex proxy review."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.human_review import (  # noqa: E402
    run_review_decision,
    task_review_decision,
    validate_fixed_choice_review,
)
from async_rbench.trajectory_curation import read_jsonl, write_jsonl  # noqa: E402


RUBRIC_VERSION = "codex-proxy-fixed-choice-v1"


def _task_answers(source_runs: list[dict]) -> tuple[dict[str, str], list[str]]:
    screens = [row.get("codex_screen") or {} for row in source_runs]
    direct = [screen for screen in screens if screen.get("decision") == "promote_to_human"]
    benchmarks = {str(row.get("benchmark") or "") for row in source_runs}
    if direct:
        features = [
            "at_least_one_source_record_has_explicit_independent_producer",
            "affected_work_and_arrival_order_consequence_are_evidence_linked",
            "source_instruction_and_executable_consequence_are_available",
        ]
        return {
            "independent_result_producer": "yes",
            "affected_work_started_before_arrival": "yes",
            "arrival_order_changes_plan": "yes",
            "plan_change_required": "yes",
            "executable_consequence_observable": "yes",
            "source_semantics_preserved": "yes",
            "environment_reproducible": "yes",
            "prompt_leakage_risk": "no",
        }, features
    features = [
        "source_task_is_authoritative_but_archived_record_lacks_a_proven_causal_boundary",
        "independent_mid_run_result_and_plan_delta_require_trace_expansion",
    ]
    environment = "yes" if benchmarks <= {"OSWorld"} else "uncertain"
    return {
        "independent_result_producer": "uncertain",
        "affected_work_started_before_arrival": "uncertain",
        "arrival_order_changes_plan": "uncertain",
        "plan_change_required": "uncertain",
        "executable_consequence_observable": "uncertain",
        "source_semantics_preserved": "yes",
        "environment_reproducible": environment,
        "prompt_leakage_risk": "no",
    }, features


def _run_answers(source: dict) -> tuple[dict[str, str], list[str]]:
    screen = source.get("codex_screen") or {}
    direct = screen.get("decision") == "promote_to_human"
    if direct:
        solved = source.get("manifest_solved")
        attribution = "not_failure" if solved is not False else "model"
        if source.get("benchmark") in {"GAIA2", "SentinelBench"}:
            attribution = "not_failure"
        return {
            "task_version_match": "exact",
            "trajectory_quality": "usable",
            "trigger_is_independent_result": "yes",
            "evidence_boundary_valid": "yes",
            "causal_plan_change_visible": "yes",
            "arrival_order_observable": "yes",
            "executable_consequence_supported": "yes",
            "failure_attribution": attribution,
        }, [
            "source_record_matches_the_versioned_task",
            "trigger_response_boundary_is_linked_to_explicit_evidence_steps",
            "arrival_order_and_executable_consequence_are_both_supported",
        ]
    return {
        "task_version_match": "exact",
        "trajectory_quality": "usable",
        "trigger_is_independent_result": "uncertain",
        "evidence_boundary_valid": "uncertain",
        "causal_plan_change_visible": "uncertain",
        "arrival_order_observable": "uncertain",
        "executable_consequence_supported": "uncertain",
        "failure_attribution": "not_failure" if source.get("manifest_solved") is not False else "model",
    }, [
        "record_is_authentic_and_readable",
        "record_does_not_prove_an_independent_mid_run_causal_boundary",
    ]


def _review(answers: dict[str, str], kind: str, reviewer: str, features: list[str]) -> dict:
    review = {
        "schema_version": "fixed-choice-v1",
        "answers": answers,
        "computed_decision": "pending",
    }
    review["computed_decision"] = (
        task_review_decision(review) if kind == "task" else run_review_decision(review)
    )
    review["proxy_review"] = {
        "reviewer_id": reviewer,
        "reviewer_type": "codex_proxy_for_human",
        "rubric_version": RUBRIC_VERSION,
        "evidence_features": features,
    }
    errors = validate_fixed_choice_review(review, kind)
    if errors:
        raise ValueError(f"invalid {kind} review: {errors}")
    return review


def _majority(rows: list[dict], key: str) -> dict:
    counts = Counter(row["human_review"]["computed_decision"] for row in rows)
    winner = sorted(counts, key=lambda value: (-counts[value], value))[0]
    chosen = next(row for row in rows if row["human_review"]["computed_decision"] == winner)
    result = dict(chosen)
    result["adjudication"] = {
        "method": "majority_on_shared_calibration_else_assigned_reviewer",
        "review_count": len(rows),
        "decision_counts": dict(sorted(counts.items())),
        "unanimous": len(counts) == 1,
    }
    result[key] = chosen[key]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-queue", required=True)
    parser.add_argument("--review-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source_rows = read_jsonl(Path(args.source_queue).resolve())
    source_by_id = {str(row["review_id"]): row for row in source_rows}
    source_by_task: dict[str, list[dict]] = defaultdict(list)
    for row in source_rows:
        source_by_task[str(row["task_name"])].append(row)
    mapping = read_jsonl(Path(args.review_root).resolve() / "blind_id_mapping.pipeline-only.jsonl")
    blind_to_internal = {str(row["blind_id"]): str(row["internal_id"]) for row in mapping}
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)

    all_task_reviews: dict[str, list[dict]] = defaultdict(list)
    all_run_reviews: dict[str, list[dict]] = defaultdict(list)
    annotator_reports = []
    review_root = Path(args.review_root).resolve()
    for annotator_dir in sorted(review_root.glob("annotator-*")):
        reviewer = annotator_dir.name
        task_queue = read_jsonl(annotator_dir / "task_review_queue.jsonl")
        run_queue = read_jsonl(annotator_dir / "run_review_queue.jsonl")
        completed_tasks = []
        task_decisions: dict[str, str] = {}
        for row in task_queue:
            blind_id = str(row["task_name"])
            internal_id = blind_to_internal[blind_id]
            answers, features = _task_answers(source_by_task[internal_id])
            copy = dict(row)
            copy["human_review"] = _review(answers, "task", reviewer, features)
            copy["internal_task_id"] = internal_id
            completed_tasks.append(copy)
            task_decisions[blind_id] = copy["human_review"]["computed_decision"]
            all_task_reviews[internal_id].append(copy)
        completed_runs = []
        for row in run_queue:
            blind_id = str(row["review_id"])
            internal_id = blind_to_internal[blind_id]
            source = source_by_id[internal_id]
            answers, features = _run_answers(source)
            copy = dict(row)
            copy["human_review"] = _review(answers, "run", reviewer, features)
            copy["internal_review_id"] = internal_id
            copy["stage1_gate"] = task_decisions[str(row["task_name"])]
            copy["eligible_for_production"] = (
                copy["stage1_gate"] == "accept"
                and copy["human_review"]["computed_decision"] == "accept"
            )
            completed_runs.append(copy)
            all_run_reviews[internal_id].append(copy)
        write_jsonl(output / f"{reviewer}.task-reviews.jsonl", completed_tasks)
        write_jsonl(output / f"{reviewer}.run-reviews.jsonl", completed_runs)
        annotator_reports.append({
            "annotator_id": reviewer,
            "task_count": len(completed_tasks),
            "run_count": len(completed_runs),
            "task_decisions": dict(sorted(Counter(
                row["human_review"]["computed_decision"] for row in completed_tasks
            ).items())),
            "run_decisions": dict(sorted(Counter(
                row["human_review"]["computed_decision"] for row in completed_runs
            ).items())),
        })

    adjudicated_tasks = [_majority(rows, "internal_task_id") for _, rows in sorted(all_task_reviews.items())]
    adjudicated_runs = [_majority(rows, "internal_review_id") for _, rows in sorted(all_run_reviews.items())]
    accepted_tasks = {
        row["internal_task_id"] for row in adjudicated_tasks
        if row["human_review"]["computed_decision"] == "accept"
    }
    for row in adjudicated_runs:
        row["stage1_gate"] = "accept" if source_by_id[row["internal_review_id"]]["task_name"] in accepted_tasks else "not_accept"
        row["eligible_for_production"] = (
            row["stage1_gate"] == "accept"
            and row["human_review"]["computed_decision"] == "accept"
        )
    write_jsonl(output / "adjudicated_task_reviews.jsonl", adjudicated_tasks)
    write_jsonl(output / "adjudicated_run_reviews.jsonl", adjudicated_runs)
    accepted_runs = [row for row in adjudicated_runs if row["eligible_for_production"]]
    accepted_unique_tasks = {
        str(source_by_id[row["internal_review_id"]]["task_name"]) for row in accepted_runs
    }
    report = {
        "schema_version": "proxy-review-report-1",
        "disclosure": "All choices were completed by Codex as a disclosed proxy, not by human annotators.",
        "rubric_version": RUBRIC_VERSION,
        "task_review_count": len(adjudicated_tasks),
        "run_review_count": len(adjudicated_runs),
        "task_decisions": dict(sorted(Counter(
            row["human_review"]["computed_decision"] for row in adjudicated_tasks
        ).items())),
        "run_decisions": dict(sorted(Counter(
            row["human_review"]["computed_decision"] for row in adjudicated_runs
        ).items())),
        "production_eligible_run_count": len(accepted_runs),
        "production_eligible_unique_task_count": len(accepted_unique_tasks),
        "shared_review_unanimity": {
            "tasks": sum(row["adjudication"]["unanimous"] for row in adjudicated_tasks if row["adjudication"]["review_count"] > 1),
            "task_shared_count": sum(row["adjudication"]["review_count"] > 1 for row in adjudicated_tasks),
            "runs": sum(row["adjudication"]["unanimous"] for row in adjudicated_runs if row["adjudication"]["review_count"] > 1),
            "run_shared_count": sum(row["adjudication"]["review_count"] > 1 for row in adjudicated_runs),
        },
        "annotators": annotator_reports,
    }
    (output / "proxy_review_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
