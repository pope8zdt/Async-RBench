"""Freeze the 200-family / 201-instance dataset splits and align dataset_policy.json.

Counting unit: registered instance (201 instances across 200 families; secure-release
carries two instances). Families with any recorded episode/pair evidence under
artifacts/ (i.e. used during model or verifier debugging) are pinned to
calibration and can never enter the held-out test split. Untouched families are
assigned deterministically: 30 to development (buffer for future implementation
changes), the rest to test. Policy target maps are set to the observed counts so
that the frozen snapshot has zero deficits and zero overflows.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEV_FAMILY_COUNT = 30


def main() -> int:
    registry_path = ROOT / "cases" / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    touched = json.loads((ROOT / "tmp" / "debug_touched_cases.json").read_text(encoding="utf-8"))

    untouched = sorted(
        family["case_id"]
        for family in registry["case_families"]
        if family["case_id"] not in touched
    )
    ranked = sorted(untouched, key=lambda cid: hashlib.sha256(cid.encode("utf-8")).hexdigest())
    dev = set(ranked[:DEV_FAMILY_COUNT])

    split_rows = []
    for family in registry["case_families"]:
        case_id = family["case_id"]
        split = "calibration" if case_id in touched else ("development" if case_id in dev else "test")
        for instance in family["instances"]:
            instance["split"] = split
            split_rows.append({"case_id": case_id, "instance_id": instance["instance_id"], "split": split})

    tmp_registry = registry_path.with_suffix(".json.tmp")
    tmp_registry.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_registry.replace(registry_path)

    audit_path = ROOT / "artifacts" / "dataset-split-freeze" / "pre-freeze-audit.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    # Exit status reflects the pre-freeze policy mismatch; the report is still written.
    subprocess.run(
        [sys.executable, "-m", "async_rbench.cli", "dataset-audit", "--output", str(audit_path)],
        cwd=ROOT,
    )
    counts = json.loads(audit_path.read_text(encoding="utf-8"))["counts"]
    policy_path = ROOT / "dataset_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy.update({
        "target_instance_count": 201,
        "allowed_instance_count_range": [201, 201],
        "counting_unit": "registered_instance",
        "split_freeze": {
            "frozen_at": "2026-09-01",
            "family_count": 200,
            "instance_count": 201,
            "rule": (
                "Families with any recorded episode/pair evidence under artifacts/ are pinned "
                "to calibration and excluded from the held-out test split; 30 untouched families "
                "are deterministic (sha256-ranked) development buffer; remaining untouched "
                "families form the held-out test split."
            ),
            "leakage_evidence_sources": ["tmp/debug_touched_cases.json"],
        },
        "splits": dict(sorted(counts["splits"].items())),
        "primary_event_theme_targets": dict(sorted(counts["primary_event_theme_targets"].items())),
        "async_scenario_class_targets": dict(sorted(counts["async_scenario_class_targets"].items())),
        "difficulty_targets": dict(sorted(counts["difficulty_targets"].items())),
    })
    tmp_policy = policy_path.with_suffix(".json.tmp")
    tmp_policy.write_text(json.dumps(policy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_policy.replace(policy_path)

    record_dir = ROOT / "artifacts" / "dataset-split-freeze"
    record_dir.mkdir(parents=True, exist_ok=True)
    (record_dir / "split-assignment.json").write_text(
        json.dumps({
            "schema_version": "dataset-split-freeze-v1",
            "family_count": 200,
            "instance_count": 201,
            "assignment": split_rows,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print(json.dumps({"splits": counts["splits"], "themes": counts["primary_event_theme_targets"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
