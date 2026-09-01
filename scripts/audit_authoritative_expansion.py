"""Audit selection, normalization, Codex screening, and annotation handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.trajectory_curation import read_jsonl  # noqa: E402
from async_rbench.human_review import validate_fixed_choice_review  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", required=True)
    parser.add_argument("--preflight-summary", required=True)
    parser.add_argument("--normalized-dir", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--annotation-index", required=True)
    parser.add_argument("--task-reviews")
    parser.add_argument("--run-reviews")
    parser.add_argument("--workspace")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    selection_path = Path(args.selection).resolve()
    summary_path = Path(args.preflight_summary).resolve()
    normalized_dir = Path(args.normalized_dir).resolve()
    labels_path = Path(args.labels).resolve()
    annotation_path = Path(args.annotation_index).resolve()
    selection, labels = read_jsonl(selection_path), read_jsonl(labels_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
    normalized = {}
    for path in normalized_dir.glob("*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        normalized[str(row.get("review_id") or "")] = row
    errors = []
    if annotation.get("review_contract") != "fixed-choice-v1":
        errors.append("annotation handoff is not fixed-choice-v1")
    if annotation.get("free_text_fields") != 0:
        errors.append("annotation handoff contains free-text fields")
    if annotation.get("computed_disposition") is not True:
        errors.append("annotation disposition is not deterministic")
    selection_ids = [str(row.get("traj_id") or "") for row in selection]
    label_ids = [str(row.get("review_id") or "") for row in labels]
    if len(selection_ids) != len(set(selection_ids)):
        errors.append("selection contains duplicate trajectory ids")
    if len(label_ids) != len(set(label_ids)):
        errors.append("labels contain duplicate review ids")
    if set(selection_ids) != set(label_ids):
        errors.append("selection and labels do not cover the same ids")
    empty = [review_id for review_id, row in normalized.items() if not (row.get("steps") or [])]
    if empty:
        errors.append(f"normalized trajectories with zero steps: {empty[:5]!r}")
    evidence_errors = []
    for row in labels:
        screen = row.get("codex_screen") or {}
        if screen.get("decision") != "promote_to_human":
            continue
        trace = normalized.get(str(row.get("review_id") or ""))
        valid = {int(step["step_id"]) for step in (trace or {}).get("steps") or []}
        evidence = {int(step_id) for step_id in screen.get("evidence_step_ids") or []}
        if not evidence or not evidence <= valid:
            evidence_errors.append(str(row.get("review_id") or ""))
    if evidence_errors:
        errors.append(f"promoted rows with invalid evidence ids: {evidence_errors[:5]!r}")
    decisions = Counter(str((row.get("codex_screen") or {}).get("decision") or "") for row in labels)
    source_failures = int(decisions.get("source_invalid", 0))
    if len(normalized) + source_failures != len(selection):
        errors.append("prepared plus explicit source failures does not equal selection count")
    if int(summary.get("total_model_tokens") or 0) != 0:
        errors.append("preflight unexpectedly used model tokens")
    if any((row.get("codex_screen") or {}).get("screening_mode") != "codex_direct_no_external_api" for row in labels):
        errors.append("labels contain a non-Codex or external-API screening mode")
    task_counts = Counter(str(row.get("task_name") or "") for row in selection)
    fixed_choice_errors = []
    task_reviews = read_jsonl(Path(args.task_reviews).resolve()) if args.task_reviews else []
    run_reviews = read_jsonl(Path(args.run_reviews).resolve()) if args.run_reviews else []
    for kind, rows in (("task", task_reviews), ("run", run_reviews)):
        for row in rows:
            review_errors = validate_fixed_choice_review(row.get("human_review") or {}, kind)
            if review_errors:
                fixed_choice_errors.append(f"{kind}:{row.get('task_name') or row.get('review_id')}: {review_errors}")
    if fixed_choice_errors:
        errors.append(f"invalid fixed-choice review rows: {fixed_choice_errors[:5]!r}")
    if task_reviews and len(task_reviews) != int(annotation.get("task_review_count") or -1):
        errors.append("task review queue count does not match annotation index")
    if run_reviews and len(run_reviews) != int(annotation.get("run_review_count") or -1):
        errors.append("run review queue count does not match annotation index")
    workspace_free_text = False
    if args.workspace:
        workspace_text = Path(args.workspace).resolve().read_text(encoding="utf-8").lower()
        workspace_free_text = any(token in workspace_text for token in (
            "<textarea", 'type="text"', "contenteditable",
        ))
        if workspace_free_text:
            errors.append("human review workspace contains a free-text control")
        if 'type="radio"' not in workspace_text:
            errors.append("human review workspace contains no fixed-choice radio controls")
    report = {
        "passed": not errors, "errors": errors,
        "selection_count": len(selection), "prepared_count": len(normalized),
        "source_failure_count": source_failures,
        "unique_task_count": len(task_counts), "max_runs_per_task": max(task_counts.values()),
        "decision_counts": dict(sorted(decisions.items())),
        "promoted_evidence_ids_valid": not evidence_errors,
        "zero_step_normalized_count": len(empty),
        "external_model_api_calls": 0,
        "preflight_model_tokens": int(summary.get("total_model_tokens") or 0),
        "annotation_task_count": annotation.get("task_review_count"),
        "annotation_run_count": annotation.get("run_review_count"),
        "fixed_choice_contract": annotation.get("review_contract"),
        "fixed_choice_rows_valid": not fixed_choice_errors,
        "workspace_free_text_controls": workspace_free_text,
        "hashes": {
            "selection_sha256": _sha(selection_path),
            "preflight_summary_sha256": _sha(summary_path),
            "codex_labels_sha256": _sha(labels_path),
            "annotation_index_sha256": _sha(annotation_path),
        },
        "lineage": [
            "authoritative public run manifest",
            "bounded run-level selection",
            "local archive normalization and rule evidence location",
            "Codex direct initial screening without external model APIs",
            "pending human task-level review",
            "pending human run-level evidence review",
        ],
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
