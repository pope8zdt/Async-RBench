from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "candidate_cases" / "rebuild-to-100" / "selection-manifest.json"
BLUEPRINTS = ROOT / "candidate_cases" / "rebuild-to-100" / "blueprints"
OUTPUT = ROOT / "candidate_cases" / "rebuild-to-100" / "progress.json"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _registered_count() -> int:
    registry = _json(ROOT / "cases" / "registry.json")
    return sum(len(family["instances"]) for family in registry["case_families"])


def _qualified(status: dict[str, Any]) -> bool:
    return all(
        (
            status.get("docker_oracle_executed") is True,
            status.get("hidden_verifier_executed") is True,
            status.get("quality_execution_passed") is True,
            status.get("equivalence_solution_passed") is True,
            int(status.get("negative_mutations_killed") or 0) >= 2,
        )
    )


def build_report() -> dict[str, Any]:
    selection = _json(SELECTION)
    selected = {str(item["case_id"]): item for item in selection["cases"]}
    materialized = {path.name for path in BLUEPRINTS.iterdir() if path.is_dir()} if BLUEPRINTS.is_dir() else set()
    statuses: dict[str, dict[str, Any]] = {}
    runtime_roots = sorted((ROOT / "candidate_cases" / "rebuild-to-100").glob("runtime-*"))
    for runtime_root in runtime_roots:
        for status_path in runtime_root.rglob("STATUS.json"):
            try:
                status = _json(status_path)
            except (OSError, json.JSONDecodeError):
                continue
            case_id = str(status.get("case_id") or status_path.parent.name)
            if case_id in selected:
                statuses[case_id] = status
    qualified = sorted(case_id for case_id, status in statuses.items() if _qualified(status))
    registered = _registered_count()
    report = {
        "schema_version": "async-rbench-case-100-progress-v1",
        "target_task_count": 100,
        "registered_task_count": registered,
        "selected_new_count": len(selected),
        "materialized_blueprint_count": len(materialized & set(selected)),
        "runtime_status_count": len(statuses),
        "fully_qualified_new_count": len(qualified),
        "qualified_total_if_promoted": registered + len(qualified),
        "remaining_until_100": 100 - registered - len(qualified),
        "selection_theme_counts": dict(sorted(Counter(item["primary_event_theme"] for item in selected.values()).items())),
        "qualified_case_ids": qualified,
        "counting_rule": "A new case counts only after Oracle, hidden verifier, equivalent solution, quality execution, and at least two killed directed mutations are recorded true.",
    }
    return report


def main() -> int:
    report = build_report()
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
