"""Fail-closed audit for the normalized and fine-screened unified collection."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.unified_case_v3 import read_json, read_jsonl  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", default="artifacts/unified-case-set-v3/00-inventory/unified_inventory_repaired.jsonl")
    parser.add_argument("--source-repair-report", default="artifacts/unified-case-set-v3/00-inventory/source_repair_report.json")
    parser.add_argument("--causal-reviews", default="artifacts/unified-case-set-v3/01-fine-review-causal-repaired/reviews.jsonl")
    parser.add_argument("--engineering-reviews", default="artifacts/unified-case-set-v3/02-fine-review-engineering-repaired/reviews.jsonl")
    parser.add_argument("--production", default="artifacts/unified-case-set-v3/03-unified-production")
    parser.add_argument("--output", default="artifacts/unified-case-set-v3/final_audit.json")
    args = parser.parse_args()
    inventory_path = Path(args.inventory).resolve()
    causal_path = Path(args.causal_reviews).resolve()
    engineering_path = Path(args.engineering_reviews).resolve()
    production = Path(args.production).resolve()
    manifest_path = production / "case_manifest.jsonl"
    inventory = read_jsonl(inventory_path)
    causal = read_jsonl(causal_path)
    engineering = read_jsonl(engineering_path)
    manifest = read_jsonl(manifest_path)
    production_report = read_json(production / "production_report.json")
    repair_report = read_json(Path(args.source_repair_report).resolve())
    errors: list[str] = []
    if not (len(inventory) == len(causal) == len(engineering) == len(manifest) == 965):
        errors.append("inventory/review/production cardinalities are not all 965")
    inventory_ids = {str(row["unified_candidate_id"]) for row in inventory}
    if {str(row["unified_candidate_id"]) for row in causal} != inventory_ids:
        errors.append("causal review coverage mismatch")
    if {str(row["unified_candidate_id"]) for row in engineering} != inventory_ids:
        errors.append("engineering review coverage mismatch")
    if len({row["case_id"] for row in manifest}) != len(manifest):
        errors.append("materialized case IDs are not unique")
    if len({(row["benchmark"], row["source_task_id"]) for row in manifest}) != len(manifest):
        errors.append("materialized source tasks are duplicated")
    if production_report.get("status") != "passed":
        errors.append("production oracle/mutation gates failed")
    if production_report.get("mutation_escape_count") != 0:
        errors.append("at least one directed mutation escaped")
    causal_map = {str(row["unified_candidate_id"]): row for row in causal}
    engineering_map = {str(row["unified_candidate_id"]): row for row in engineering}
    inventory_by_origin = {
        (str(row["collection"]), str(row["original_case_id"])): row for row in inventory
    }
    normalized_errors = Counter()
    for row in manifest:
        case_dir = production / str(row["path"])
        public = read_json(case_dir / "case.json")
        if public.get("schema_version") != "async-rbench-unified-case-v3":
            normalized_errors["schema"] += 1
        points = public.get("score_points") or []
        if not points or abs(sum(float(point.get("weight") or 0) for point in points) - 1.0) > 1e-6:
            normalized_errors["weights"] += 1
        if any(not point.get("mode_neutral") for point in points):
            normalized_errors["mode_neutral"] += 1
        if any(point.get("id") in {"source_identity", "pre_event_work", "result_intake", "plan_revision", "selective_preservation", "stale_rejection", "affected_completion", "closure_reverification"} for point in points):
            normalized_errors["legacy_score_point"] += 1
        quality = public.get("quality_state") or {}
        origin_key = (str(row["origin_collection"]), str(row["original_case_id"]))
        source_inventory = inventory_by_origin[origin_key]
        candidate_id = str(source_inventory["unified_candidate_id"])
        both_keep = (
            causal_map[candidate_id]["decision"] == "keep_normalized"
            and engineering_map[candidate_id]["decision"] == "keep_normalized"
        )
        if row["fine_screen_status"] == "keep_normalized" and not both_keep:
            normalized_errors["invalid_keep_adjudication"] += 1
        if row["fine_screen_status"] == "keep_normalized" and source_inventory["fatal_issue_count"]:
            normalized_errors["fatal_case_kept"] += 1
        if quality.get("formal_promotion_ready"):
            normalized_errors["premature_formal_promotion"] += 1
    if normalized_errors:
        errors.append(f"normalized case invariants failed: {dict(normalized_errors)}")
    status_counts = Counter(row["fine_screen_status"] for row in manifest)
    issue_counts = Counter(
        issue["code"] for row in inventory for issue in row.get("deterministic_issues") or []
    )
    report = {
        "schema_version": "async-rbench-unified-final-audit-v3",
        "status": "passed" if not errors else "failed",
        "merge_status": "passed" if not errors else "failed",
        "research_promotion_status": "blocked",
        "errors": errors,
        "inventory_count": len(inventory),
        "normalized_case_count": len(manifest),
        "origin_counts": dict(sorted(Counter(row["origin_collection"] for row in manifest).items())),
        "benchmark_counts": dict(sorted(Counter(row["benchmark"] for row in manifest).items())),
        "fine_screen_status_counts": dict(sorted(status_counts.items())),
        "fine_screen_by_origin": production_report.get("fine_screen_by_origin"),
        "source_text_repair": repair_report,
        "remaining_issue_counts": dict(sorted(issue_counts.items())),
        "reviewer_agreement_count": production_report.get("reviewer_agreement_count"),
        "react_oracle_pass_count": production_report.get("react_oracle_pass_count"),
        "linear_oracle_pass_count": production_report.get("linear_oracle_pass_count"),
        "async_oracle_pass_count": production_report.get("async_oracle_pass_count"),
        "mutation_checks_run": production_report.get("mutation_checks_run"),
        "mutation_escape_count": production_report.get("mutation_escape_count"),
        "source_native_replay_ready_count": production_report.get("source_native_replay_ready_count"),
        "formal_promotion_ready_count": production_report.get("formal_promotion_ready_count"),
        "formal_promotion_blockers": [
            "source_native_replay_not_completed",
            "per_case_async_below_linear_not_empirically_validated",
            "formal_dev_test_split_not_frozen",
        ],
        "artifact_sha256": {
            "inventory": sha256(inventory_path),
            "causal_reviews": sha256(causal_path),
            "engineering_reviews": sha256(engineering_path),
            "case_manifest": sha256(manifest_path),
        },
    }
    write_json(Path(args.output).resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
