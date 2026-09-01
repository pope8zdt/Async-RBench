#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "candidate_cases/rebuild-to-200/selection-manifest.json"
OUTPUT = ROOT / "artifacts/case-200-pipeline/progress.json"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    selection = read(SELECTION)
    registry = read(ROOT / "cases/registry.json")
    registered = {str(item["case_id"]) for item in registry.get("case_families") or []}
    selected = [str(item["case_id"]) for item in selection["cases"]]
    rows = []
    states: Counter[str] = Counter()
    for case_id in selected:
        if case_id in registered:
            state = "registered"
        else:
            candidate = ROOT / "candidate_cases" / case_id
            blueprint = next((path for path in (
                ROOT / "candidate_cases/rebuild-to-100/blueprints" / case_id,
                ROOT / "candidate_cases/rebuild-to-200/blueprints" / case_id,
            ) if path.is_dir()), None)
            if candidate.is_dir():
                status_path = candidate / "STATUS.json"
                status = read(status_path) if status_path.is_file() else {}
                if status.get("quality_execution_passed") is True:
                    state = "quality_passed_pending_promotion"
                elif status.get("v9_1_design_rebound") is True:
                    state = "runtime_rebuilt_pending_quality"
                else:
                    state = "runtime_package_pending_rebuild"
            elif blueprint:
                state = "blueprint_pending_runtime"
            else:
                state = "missing_blueprint"
        states[state] += 1
        rows.append({"case_id": case_id, "state": state})
    payload = {
        "schema_version": "async-rbench-case-200-progress-v1",
        "target_case_family_count": 200,
        "registered_case_family_count": len(registered),
        "registered_instance_count": sum(len(item.get("instances") or []) for item in registry.get("case_families") or []),
        "selected_rebuild_count": len(selected),
        "state_counts": dict(sorted(states.items())),
        "remaining_to_register": 200 - len(registered),
        "rows": rows,
        "counting_rule": "Only cases present in cases/registry.json count as formal; blueprints, runnable packages, and quality-passed candidates are reported separately.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in (
        "target_case_family_count", "registered_case_family_count",
        "registered_instance_count", "remaining_to_register", "state_counts",
    )}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
