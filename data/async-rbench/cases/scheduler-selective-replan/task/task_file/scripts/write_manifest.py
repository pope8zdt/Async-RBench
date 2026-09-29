#!/usr/bin/env python3
"""Build the scheduler manifest from plans, snapshots and validator reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

OUT = Path("/app/task_file/output_data")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    plans = {n: OUT / f"plan_b{n}.jsonl" for n in (1, 2)}
    first = {n: OUT / "first_pass" / f"plan_b{n}.jsonl" for n in (1, 2)}
    reports = {
        n: _load(OUT / "validator_reports" / f"bucket{n}.json") for n in (1, 2)
    }
    changed = [n for n in (1, 2) if _sha256(plans[n]) != _sha256(first[n])]
    preserved = [n for n in (1, 2) if n not in changed]
    if len(changed) != 1 or len(preserved) != 1:
        raise SystemExit("expected exactly one changed plan and one preserved plan")
    replanned_n, preserved_n = changed[0], preserved[0]
    global_plan = _load(OUT / "global_shape_plan.json")
    validator_results = {
        f"bucket{n}": "pass" if reports[n].get("passes") is True else "fail"
        for n in (1, 2)
    }
    manifest = {
        "preserved_bucket": f"bucket{preserved_n}",
        "replanned_bucket": f"bucket{replanned_n}",
        "authority_receipt": reports[replanned_n].get("authority_receipt"),
        "preserved_bucket_first_pass_sha256": _sha256(first[preserved_n]),
        "preserved_bucket_final_sha256": _sha256(plans[preserved_n]),
        "replanned_bucket_first_pass_sha256": _sha256(first[replanned_n]),
        "replanned_bucket_final_sha256": _sha256(plans[replanned_n]),
        "global_shape_set": global_plan.get("global_shape_set", []),
        "combined_unique_shapes": global_plan.get("combined_unique_shapes"),
        "wait_for_all_validators": len(reports) == 2,
        "validator_results": validator_results,
        "closure_verified": (
            all(value == "pass" for value in validator_results.values())
            and int(global_plan.get("combined_unique_shapes", 999999)) <= 8
        ),
    }
    (OUT / "decision_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
