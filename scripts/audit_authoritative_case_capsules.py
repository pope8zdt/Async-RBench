"""Fail-closed audit for the reviewed authoritative capsule batch."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.authoritative_capsule import (  # noqa: E402
    POINT_WEIGHTS, canonical_sha256, oracle_submission, score_submission,
)
from async_rbench.human_review import validate_fixed_choice_review  # noqa: E402
from async_rbench.trajectory_curation import read_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", required=True)
    parser.add_argument("--task-reviews", required=True)
    parser.add_argument("--run-reviews", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    production = Path(args.production).resolve()
    manifest = read_jsonl(production / "case_manifest.jsonl")
    task_reviews = read_jsonl(Path(args.task_reviews).resolve())
    run_reviews = read_jsonl(Path(args.run_reviews).resolve())
    errors = []
    if len(manifest) != 300:
        errors.append(f"expected 300 cases, found {len(manifest)}")
    for kind, rows in (("task", task_reviews), ("run", run_reviews)):
        for row in rows:
            review_errors = validate_fixed_choice_review(row.get("human_review") or {}, kind)
            if review_errors:
                errors.append(f"{kind} review invalid: {review_errors}")
    case_ids = [str(row["case_id"]) for row in manifest]
    source_tasks = [str(row["source_task_id"]) for row in manifest]
    source_ids = [str(row["source_id"]) for row in manifest]
    for label, values in (("case ids", case_ids), ("source tasks", source_tasks), ("source records", source_ids)):
        if len(values) != len(set(values)):
            errors.append(f"duplicate {label}")
    deterministic_failures = []
    file_failures = []
    for row in manifest:
        case_dir = production / str(row["path"])
        required = (
            "case.json", "source_record.json", "task.md", "oracle.py", "verify.py",
            "private/expected.json",
        )
        missing = [name for name in required if not (case_dir / name).is_file()]
        if missing:
            file_failures.append(f"{row['case_id']}: missing {missing}")
            continue
        public = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
        if canonical_sha256(public) != row["capsule_sha256"]:
            file_failures.append(f"{row['case_id']}: capsule hash mismatch")
        if abs(sum(float(point["weight"]) for point in public["score_points"]) - 1.0) > 1e-9:
            file_failures.append(f"{row['case_id']}: weights do not sum to 1")
        if {point["id"] for point in public["score_points"]} != set(POINT_WEIGHTS):
            file_failures.append(f"{row['case_id']}: score point registry mismatch")
        hashes = []
        for _ in range(3):
            oracle = oracle_submission(case_dir, "async")
            result = score_submission(case_dir, oracle, "async")
            hashes.append(canonical_sha256({"oracle": oracle, "result": result}))
        if len(set(hashes)) != 1:
            deterministic_failures.append(str(row["case_id"]))
    errors.extend(file_failures)
    if deterministic_failures:
        errors.append(f"async nondeterminism: {deterministic_failures}")
    family_counts = Counter(str(row["family"]) for row in manifest)
    max_family_fraction = max(family_counts.values(), default=0) / max(len(manifest), 1)
    if max_family_fraction > 0.2:
        errors.append(f"family concentration {max_family_fraction:.3f} exceeds 0.2")
    report = {
        "schema_version": "authoritative-capsule-final-audit-1",
        "status": "passed" if not errors else "failed",
        "case_count": len(manifest),
        "unique_case_count": len(set(case_ids)),
        "unique_source_task_count": len(set(source_tasks)),
        "unique_source_record_count": len(set(source_ids)),
        "family_counts": dict(sorted(family_counts.items())),
        "max_family_fraction": max_family_fraction,
        "task_review_count": len(task_reviews),
        "run_review_count": len(run_reviews),
        "async_determinism_repeats_per_case": 3,
        "async_determinism_pass_count": len(manifest) - len(deterministic_failures),
        "file_contract_pass_count": len(manifest) - len(file_failures),
        "scored_points_per_case": len(POINT_WEIGHTS),
        "unscored_point_count": 0,
        "errors": errors,
        "release_class": "runnable_preproduction_capsule",
        "formal_registry_promotion": False,
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
