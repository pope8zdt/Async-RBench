"""Create a fail-closed final audit for the source-native v4 candidate set."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "source-native-v4"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> int:
    production = read_json(ARTIFACT / "production_report.json")
    preflight = read_json(ARTIFACT / "preflight_audit.json")
    policy = read_json(ROOT / "configs" / "source_native_promotion_v4.json")
    ready = read_jsonl(ARTIFACT / "native_manifest.jsonl")
    blocked = read_jsonl(ARTIFACT / "blocked_manifest.jsonl")
    unique_sources = {(row["benchmark"], row["source_task_id"]) for row in ready}
    case_directories = [path for path in (ARTIFACT / "cases").glob("*/*") if path.is_dir()]
    static_pass = all((
        production["input_rebuild_count"] == len(ready) + len(blocked),
        production["spec_ready_count"] == len(ready),
        preflight["passed_count"] == len(ready),
        preflight["failed_count"] == 0,
        len(unique_sources) == len(ready),
        len(case_directories) == len(ready),
    ))
    runtime_pass = production["runtime_executed_count"] == len(ready) and len(ready) > 0
    effect_pass = bool(preflight["gates"]["paired_linear_async_effect_validation"])
    promotion = static_pass and runtime_pass and effect_pass
    report = {
        "schema_version": "source-native-final-audit-v4",
        "status": "promotion_ready" if promotion else "blocked_runtime_and_effect_validation",
        "counts": {
            "input": production["input_rebuild_count"],
            "static_candidate": len(ready),
            "source_or_quality_blocked": len(blocked),
            "environment_smoke_qualified": production.get("environment_smoke_ready_count", 0),
            "environment_smoke_qualified_by_benchmark": production.get(
                "environment_smoke_ready_benchmark_counts", {}
            ),
            "native_environment_initialization": production.get(
                "native_environment_initialization_count", 0
            ),
            "native_environment_initialization_by_benchmark": production.get(
                "native_environment_initialization_benchmark_counts", {}
            ),
            "infrastructure_qualified": production["runtime_ready_count"],
            "native_runtime_qualified": production["runtime_ready_count"],
            "native_runtime_executed": production["runtime_executed_count"],
            "formal_promotion_ready": len(ready) if promotion else 0,
        },
        "gates": {
            "static_integrity": static_pass,
            "environment_smoke_qualification": production.get("environment_smoke_ready_count", 0) > 0,
            "case_specific_infrastructure": production["runtime_ready_count"] > 0,
            "native_runtime_execution": runtime_pass,
            "paired_linear_async_effect": effect_pass,
            "formal_promotion": promotion,
        },
        "invalid_episode_policy": policy["invalid_episode_policy"],
        "research_claim_allowed": "native paired benchmark result" if promotion else "static source-native candidate construction only",
    }
    (ARTIFACT / "final_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if static_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
