"""Fail-closed end-to-end audit for the scalable expansion-v2 artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.expansion_v2 import read_jsonl, write_json  # noqa: E402


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_revision(path: Path) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--screen", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--production", required=True)
    parser.add_argument("--model-pilot")
    parser.add_argument("--min-pilot-cases", type=int, default=10)
    parser.add_argument("--min-linear-mean", type=float, default=0.80)
    parser.add_argument("--min-async-gap", type=float, default=0.03)
    parser.add_argument("--min-async-lower-rate", type=float, default=0.30)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source_dir = Path(args.source).resolve()
    screen_dir = Path(args.screen).resolve()
    review_dir = Path(args.review).resolve()
    production_dir = Path(args.production).resolve()
    output = Path(args.output).resolve()

    source_report = _json(source_dir / "source_report.json")
    screen_report = _json(screen_dir / "semantic_screen_report.json")
    review_report = _json(review_dir / "proxy_review_report.json")
    production_report = _json(production_dir / "production_report.json")
    pilot_report = _json(Path(args.model_pilot).resolve()) if args.model_pilot else None
    semantic_queue = read_jsonl(source_dir / "semantic_review_queue.jsonl")
    screen_queue = read_jsonl(screen_dir / "review_queue.jsonl")
    adjudicated = read_jsonl(review_dir / "adjudicated_reviews.jsonl")
    manifest = read_jsonl(production_dir / "case_manifest.jsonl")
    errors: list[str] = []
    challenge_errors: list[str] = []

    expected_benchmarks = {"OSWorld", "SWE-bench", "MultiAgentBench"}
    if set(source_report.get("task_benchmark_counts") or {}) != expected_benchmarks:
        errors.append("source registry does not contain all required benchmarks")
    if screen_report.get("input_count") != len(semantic_queue):
        errors.append("semantic screen did not cover the full structural review queue")
    if screen_report.get("output_count") != len(semantic_queue):
        errors.append("semantic screen output is incomplete")
    if review_report.get("candidate_count") != len(screen_queue):
        errors.append("proxy review did not cover every promoted semantic candidate")
    if review_report.get("review_count") != 3 * len(screen_queue):
        errors.append("each promoted candidate must have exactly three proxy reviews")
    eligible = [row for row in adjudicated if row.get("eligible_for_production")]
    if len(eligible) != len(manifest):
        errors.append("production did not compile every adjudicated eligible candidate")
    if len(manifest) != len({row.get("case_id") for row in manifest}):
        errors.append("case ids are not unique")
    if len(manifest) != len({(row.get("benchmark"), row.get("source_task_id")) for row in manifest}):
        errors.append("multiple produced cases derive from the same source task")
    produced_benchmarks = {str(row.get("benchmark")) for row in manifest}
    missing_benchmarks = sorted(expected_benchmarks - produced_benchmarks)
    if missing_benchmarks:
        errors.append(f"no production cases passed for benchmarks: {missing_benchmarks}")
    if production_report.get("status") != "passed":
        errors.append("production gates did not pass")
    if production_report.get("source_instruction_mismatch_count") != 0:
        errors.append("produced source instructions do not exactly match source payloads")
    if production_report.get("empty_source_instruction_count") != 0:
        errors.append("at least one produced case has an empty source instruction")
    if production_report.get("distinct_full_semantics_count") != len(manifest):
        errors.append("produced cases contain duplicate full scoring semantics")
    if production_report.get("duplicate_full_semantic_group_count") != 0:
        errors.append("produced cases contain duplicate full semantic groups")
    if any(float(row.get("linear_oracle_score") or 0) != 1.0 for row in manifest):
        errors.append("at least one Linear oracle failed")
    if any(float(row.get("react_oracle_score") or 0) != 1.0 for row in manifest):
        errors.append("at least one blocking ReAct oracle failed")
    if any(float(row.get("async_oracle_score") or 0) != 1.0 for row in manifest):
        errors.append("at least one Async oracle failed")
    if any(int(row.get("unscored_point_count") or 0) != 0 for row in manifest):
        errors.append("at least one case has unscored points")
    if production_report.get("mutation_failures"):
        errors.append("at least one directed mutation escaped its target point")
    for row in manifest:
        case_dir = production_dir / str(row["path"])
        required = (
            "case.json", "task.md", "source_record.json", "oracle.py", "verify.py", "react_oracle.py",
            "private/expected.json", "private/review_evidence.json",
            "private/preproduction_quality_contract.json",
        )
        for relative in required:
            if not (case_dir / relative).is_file():
                errors.append(f"{row['case_id']} missing {relative}")

    challenge_summary = None
    if pilot_report is not None:
        aggregates = pilot_report.get("aggregates") or {}
        linear = (aggregates.get("linear") or {}).get("main_macro_mean")
        async_score = (aggregates.get("async") or {}).get("main_macro_mean")
        by_case = pilot_report.get("by_case") or {}
        deltas = [
            float(row["async_minus_linear"])
            for row in by_case.values() if row.get("async_minus_linear") is not None
        ]
        challenge_summary = {
            "pilot_case_count": int((pilot_report.get("sample") or {}).get("size") or 0),
            "episode_count": pilot_report.get("episode_count"),
            "full_coverage": pilot_report.get("all_modes_full_coverage"),
            "react_main_macro_mean": (aggregates.get("react") or {}).get("main_macro_mean"),
            "linear_main_macro_mean": linear,
            "async_main_macro_mean": async_score,
            "async_minus_linear": (
                round(float(async_score) - float(linear), 8)
                if linear is not None and async_score is not None else None
            ),
            "async_lower_case_count": sum(delta < 0 for delta in deltas),
            "equal_case_count": sum(delta == 0 for delta in deltas),
            "async_higher_case_count": sum(delta > 0 for delta in deltas),
            "async_lower_case_rate": (
                round(sum(delta < 0 for delta in deltas) / len(deltas), 8)
                if deltas else None
            ),
            "gate_thresholds": {
                "min_pilot_cases": args.min_pilot_cases,
                "min_linear_mean": args.min_linear_mean,
                "min_async_gap": args.min_async_gap,
                "min_async_lower_rate": args.min_async_lower_rate,
            },
        }
        if challenge_summary["pilot_case_count"] < args.min_pilot_cases:
            challenge_errors.append(
                "challenge-validity gate failed: pilot case count is below the minimum"
            )
        if not pilot_report.get("all_modes_full_coverage"):
            challenge_errors.append("model pilot does not have full ReAct/Linear/Async coverage")
        if linear is None or async_score is None:
            challenge_errors.append("model pilot is missing Linear or Async main scores")
        else:
            if float(linear) < args.min_linear_mean:
                challenge_errors.append(
                    "challenge-validity gate failed: Linear feasibility mean is below the minimum"
                )
            if float(linear) - float(async_score) < args.min_async_gap:
                challenge_errors.append(
                    "challenge-validity gate failed: Async mean gap below the minimum"
                )
        lower_rate = challenge_summary["async_lower_case_rate"]
        if lower_rate is None or lower_rate < args.min_async_lower_rate:
            challenge_errors.append(
                "challenge-validity gate failed: too few sampled cases have Async lower than Linear"
            )
    else:
        challenge_errors.append("challenge-validity model pilot was not supplied")

    evidence_paths = {
        "osworld_source_records": ROOT / "artifacts" / "authoritative-case-300" / "00-source-collection" / "source_records.jsonl",
        "swe_dossiers": ROOT / "artifacts" / "authoritative-expansion-2700" / "02-codex-screening" / "dossiers.jsonl",
        "source_registry": source_dir / "source_artifacts.jsonl",
        "semantic_labels": screen_dir / "semantic_labels.jsonl",
        "adjudicated_reviews": review_dir / "adjudicated_reviews.jsonl",
        "case_manifest": production_dir / "case_manifest.jsonl",
    }
    report = {
        "schema_version": "expansion-v2-final-audit",
        "status": "passed" if not errors and not challenge_errors else "failed",
        "structural_quality_status": "passed" if not errors else "failed",
        "challenge_validity_status": "passed" if not challenge_errors else "failed",
        "errors": errors + challenge_errors,
        "source_artifact_count": source_report.get("artifact_count"),
        "source_task_count": source_report.get("semantic_task_count"),
        "semantic_screen_count": screen_report.get("input_count"),
        "three_review_candidate_count": review_report.get("candidate_count"),
        "proxy_review_count": review_report.get("review_count"),
        "produced_case_count": len(manifest),
        "produced_benchmark_counts": dict(sorted(Counter(row["benchmark"] for row in manifest).items())),
        "produced_family_counts": dict(sorted(Counter(row["family"] for row in manifest).items())),
        "score_point_count_distribution": dict(sorted(Counter(row["score_point_count"] for row in manifest).items())),
        "react_oracle_pass_count": production_report.get("react_oracle_pass_count"),
        "linear_oracle_pass_count": production_report.get("linear_oracle_pass_count"),
        "async_oracle_pass_count": production_report.get("async_oracle_pass_count"),
        "mutation_checks_run": production_report.get("mutation_checks_run"),
        "source_instruction_mismatch_count": production_report.get("source_instruction_mismatch_count"),
        "duplicate_full_semantic_group_count": production_report.get("duplicate_full_semantic_group_count"),
        "challenge_summary": challenge_summary,
        "upstream_revisions": {
            "MultiAgentBench_MARBLE": _git_revision(ROOT / "upstream" / "marble"),
            "public_MultiAgentBench_results": _git_revision(ROOT / "upstream" / "squad-marble-benchmark"),
        },
        "evidence_sha256": {
            name: _sha256(path) for name, path in evidence_paths.items() if path.is_file()
        },
        "formal_registry_promotion": False,
        "promotion_blockers": sorted(set(
            (["structural_audit_failed"] if errors else [])
            + (["challenge_validity_failed"] if challenge_errors else [])
            + ["formal_case_schema_not_authored"]
        )),
        "human_label_disclosure": "The review stage is a three-invocation Codex simulation, not human annotation.",
    }
    write_json(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors and not challenge_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
