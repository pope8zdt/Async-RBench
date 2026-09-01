from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from async_rbench.cli import _execute_declared_quality_variants


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "candidate_cases" / "rebuild-to-100" / "runtime-swe-next"
RUNTIME = ROOT / "artifacts" / "runtime-swe-next"
QUALITY = ROOT / "artifacts" / "runtime-swe-next-quality"


def _result_from_summary(case_id: str, summary: dict, *, reused: bool = False) -> dict:
    result = {
        "case_id": case_id,
        "passed": summary.get("passed") is True,
        "equivalence_passed": all(
            row.get("success") is True for row in summary["equivalence_solutions"]
        ),
        "negative_mutations_killed": sum(
            row.get("killed") is True for row in summary["negative_mutations"]
        ),
        "negative_mutations_total": len(summary["negative_mutations"]),
        "same_verifier_bundle": summary.get("same_verifier_bundle") is True,
    }
    if reused:
        result["reused"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--rerun", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    selected = set(args.case_id or [])
    manifest = json.loads((BATCH / "batch-manifest.json").read_text(encoding="utf-8"))
    QUALITY.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for item in manifest["cases"]:
        case_id = str(item["case_id"])
        if selected and case_id not in selected:
            continue
        candidate = BATCH / case_id
        case_output = QUALITY / case_id
        summary_path = case_output / "summary.json"
        if summary_path.is_file() and not args.rerun:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if summary.get("passed") is True:
                results.append(_result_from_summary(case_id, summary, reused=True))
                print(json.dumps(results[-1]), flush=True)
                continue
        if case_output.exists():
            shutil.rmtree(case_output)
        canonical_report_path = RUNTIME / f"{case_id}-verifier.json"
        if not canonical_report_path.is_file():
            results.append({"case_id": case_id, "passed": False, "error": "missing canonical verifier report"})
            continue
        canonical_report = json.loads(canonical_report_path.read_text(encoding="utf-8"))
        canonical_digest = str(canonical_report.get("verifier_bundle_sha256") or "")
        if canonical_report.get("success") is not True or not canonical_digest:
            results.append({"case_id": case_id, "passed": False, "error": "canonical verifier did not pass"})
            continue
        summary = _execute_declared_quality_variants(
            candidate,
            case_id,
            case_output / "instances",
            case_output / "reports",
            seed=args.seed,
            canonical_verifier_digest=canonical_digest,
        )
        case_output.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = _result_from_summary(case_id, summary)
        results.append(result)
        status_path = candidate / "STATUS.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status.update({
            "quality_execution_passed": result["passed"],
            "equivalence_solution_executed": True,
            "equivalence_solution_passed": result["equivalence_passed"],
            "negative_mutations_executed": result["negative_mutations_total"],
            "negative_mutations_killed": result["negative_mutations_killed"],
            "quality_report": str(summary_path.relative_to(ROOT)).replace("\\", "/"),
            "status": (
                "release_gates_passed_pending_registry_promotion"
                if result["passed"] else "quality_failed_requires_repair"
            ),
        })
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result), flush=True)
    batch = {
        "schema_version": "1",
        "results": results,
        "passed": sum(row.get("passed") is True for row in results),
        "total": len(results),
    }
    (QUALITY / "quality-summary.json").write_text(
        json.dumps(batch, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(batch, indent=2), flush=True)
    return 0 if batch["passed"] == batch["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
