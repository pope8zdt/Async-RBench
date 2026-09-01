from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "artifacts" / "case-transformability-audit-v2" / "cases.jsonl"
REGISTRY = ROOT / "cases" / "registry.json"
DEFAULT_OUTPUT = ROOT / "candidate_cases" / "rebuild-to-100" / "selection-manifest.json"

# Four themes receive 13 cases and four receive 12.  Extra slots go to the
# least-covered themes in the registered 18; the conflict/late tie is resolved
# lexicographically, so conflicting_valid_results receives the fourth slot.
FINAL_THEME_TARGETS = {
    "delayed_authoritative_result": 13,
    "late_or_out_of_order_superseded_result": 12,
    "partial_then_complete_result": 12,
    "conflicting_valid_results": 13,
    "duplicate_or_replayed_completion": 13,
    "child_failure_or_implicit_error": 13,
    "task_scope_or_dependency_change": 12,
    "straggler_under_resource_pressure": 12,
}

NEW_BENCHMARK_TARGETS = {
    "MultiAgentBench": 34,
    "OSWorld": 15,
    "SWE-bench": 33,
}

NEW_SCENARIO_TARGETS = {
    "live_eventful": 26,
    "resource_eventful": 15,
    "result_eventful": 41,
}

# Cell order is intentional.  Source-group counts carry across cells within a
# benchmark, which makes later choices fill source gaps left by earlier cells.
# The quotas also make the final 100-task scenario mix exactly 50/30/20 after
# adding the registered 18-task mix of 9/4/5.
CELL_QUOTAS: tuple[dict[str, Any], ...] = (
    # MultiAgentBench: cover all four native task domains.
    {
        "benchmark": "MultiAgentBench",
        "theme": "child_failure_or_implicit_error",
        "scenario": "resource_eventful",
        "source_group": "coding",
        "count": 8,
    },
    {
        "benchmark": "MultiAgentBench",
        "theme": "child_failure_or_implicit_error",
        "scenario": "result_eventful",
        "source_group": "coding",
        "count": 4,
    },
    {
        "benchmark": "MultiAgentBench",
        "theme": "conflicting_valid_results",
        "scenario": "live_eventful",
        "source_group": "database",
        "count": 11,
    },
    {
        "benchmark": "MultiAgentBench",
        "theme": "delayed_authoritative_result",
        "scenario": "result_eventful",
        "source_group": "research",
        "count": 2,
    },
    {
        "benchmark": "MultiAgentBench",
        "theme": "late_or_out_of_order_superseded_result",
        "scenario": "result_eventful",
        "source_group": "bargaining",
        "count": 9,
    },
    # SWE-bench: take the two unique theme anchors first, then balance repos.
    {
        "benchmark": "SWE-bench",
        "theme": "child_failure_or_implicit_error",
        "scenario": "result_eventful",
        "count": 1,
    },
    {
        "benchmark": "SWE-bench",
        "theme": "late_or_out_of_order_superseded_result",
        "scenario": "result_eventful",
        "count": 1,
    },
    {
        "benchmark": "SWE-bench",
        "theme": "duplicate_or_replayed_completion",
        "scenario": "result_eventful",
        "count": 11,
    },
    {
        "benchmark": "SWE-bench",
        "theme": "partial_then_complete_result",
        "scenario": "result_eventful",
        "count": 7,
    },
    {
        "benchmark": "SWE-bench",
        "theme": "straggler_under_resource_pressure",
        "scenario": "resource_eventful",
        "count": 7,
    },
    {
        "benchmark": "SWE-bench",
        "theme": "task_scope_or_dependency_change",
        "scenario": "result_eventful",
        "count": 6,
    },
    # OSWorld: all delayed candidates are needed; the remaining cells diversify
    # snapshots/apps against that already-selected set.
    {
        "benchmark": "OSWorld",
        "theme": "delayed_authoritative_result",
        "scenario": "live_eventful",
        "count": 10,
    },
    {
        "benchmark": "OSWorld",
        "theme": "partial_then_complete_result",
        "scenario": "live_eventful",
        "count": 1,
    },
    {
        "benchmark": "OSWorld",
        "theme": "duplicate_or_replayed_completion",
        "scenario": "live_eventful",
        "count": 2,
    },
    {
        "benchmark": "OSWorld",
        "theme": "task_scope_or_dependency_change",
        "scenario": "live_eventful",
        "count": 2,
    },
)


def _load_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _registered_tasks() -> tuple[list[dict[str, Any]], set[str], set[str]]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    tasks: list[dict[str, Any]] = []
    case_ids: set[str] = set()
    source_ids: set[str] = set()
    for family in registry["case_families"]:
        case_id = str(family["case_id"])
        for instance in family["instances"]:
            relative = "" if instance["path"] == "." else str(instance["path"])
            case_dir = ROOT / "cases" / case_id / relative
            private = yaml.safe_load(
                (case_dir / "private" / "private_case.yaml").read_text(encoding="utf-8")
            )
            public = yaml.safe_load((case_dir / "public_case.yaml").read_text(encoding="utf-8"))
            classification = dict(private.get("classification") or {})
            tasks.append(
                {
                    "case_id": case_id,
                    "instance_id": str(instance["instance_id"]),
                    "primary_event_theme": classification.get("primary_event_theme"),
                    "async_scenario_class": classification.get("async_scenario_class"),
                }
            )
            case_ids.add(case_id)
            for source in public.get("source_tasks") or []:
                source_id = source.get("id")
                if source_id:
                    source_ids.add(str(source_id))
    return tasks, case_ids, source_ids


def _source_group(row: dict[str, Any]) -> str:
    """Return the benchmark-native grouping used for diversity rotation."""
    benchmark = str(row["benchmark"])
    source_task_id = str(row["source_task_id"])
    if benchmark == "MultiAgentBench":
        return source_task_id.split(":", 1)[0]
    if benchmark == "SWE-bench":
        return source_task_id.split("__", 1)[0]
    if benchmark == "OSWorld":
        runtime = row.get("runtime_package_plan") or {}
        native = runtime.get("native_runtime_ref") or {}
        snapshot = native.get("snapshot")
        if not snapshot:
            raise RuntimeError(f"OSWorld candidate lacks native snapshot: {row['case_id']}")
        return str(snapshot)
    return benchmark


def _quality_priority(row: dict[str, Any]) -> tuple[Any, ...]:
    """Prefer deeper causal/semantic blueprints, then use a stable ID tie-break."""
    return (
        -len(row.get("control_score_blueprint") or []),
        -len(row.get("semantic_score_blueprint") or []),
        str(row["case_id"]),
    )


def _select_diverse(
    candidates: list[dict[str, Any]],
    count: int,
    source_group_counts: Counter[str],
) -> list[dict[str, Any]]:
    """Select a cell deterministically while balancing native source groups.

    Each round considers the highest-quality remaining row from every source
    group, then picks from the group used least often in earlier cells of the
    same benchmark.  The global counter is mutated deliberately.
    """
    remaining = sorted(candidates, key=_quality_priority)
    chosen: list[dict[str, Any]] = []
    while len(chosen) < count:
        if not remaining:
            raise RuntimeError(f"candidate pool exhausted after {len(chosen)} of {count}")
        heads: dict[str, dict[str, Any]] = {}
        for row in remaining:
            heads.setdefault(_source_group(row), row)
        pick = min(
            heads.values(),
            key=lambda row: (
                source_group_counts[_source_group(row)],
                *_quality_priority(row),
            ),
        )
        chosen.append(pick)
        source_group_counts[_source_group(pick)] += 1
        remaining = [row for row in remaining if row["case_id"] != pick["case_id"]]
    return chosen


def build_selection() -> dict[str, Any]:
    registered, registered_case_ids, registered_source_ids = _registered_tasks()
    current_counts = Counter(item["primary_event_theme"] for item in registered)
    deficits = {
        theme: target - current_counts.get(theme, 0)
        for theme, target in FINAL_THEME_TARGETS.items()
    }
    if any(value < 0 for value in deficits.values()):
        raise RuntimeError(f"registered distribution exceeds fixed target: {deficits}")
    if sum(deficits.values()) != 100 - len(registered):
        raise RuntimeError(
            f"target arithmetic mismatch: registered={len(registered)} deficits={sum(deficits.values())}"
        )

    rows = _load_rows(AUDIT)
    eligible = [
        row
        for row in rows
        if row["transformability"]["can_be_formal_case_task"] is True
        and row["case_id"] not in registered_case_ids
        and row["source_task_id"] not in registered_source_ids
    ]
    cell_theme_counts = Counter(
        {
            theme: sum(
                int(cell["count"])
                for cell in CELL_QUOTAS
                if cell["theme"] == theme
            )
            for theme in FINAL_THEME_TARGETS
        }
    )
    if dict(cell_theme_counts) != deficits:
        raise RuntimeError(
            f"cell quotas do not match registered theme deficits: "
            f"cells={dict(cell_theme_counts)} deficits={deficits}"
        )

    selected: list[dict[str, Any]] = []
    source_group_counts: dict[str, Counter[str]] = {
        benchmark: Counter() for benchmark in NEW_BENCHMARK_TARGETS
    }
    for cell in CELL_QUOTAS:
        benchmark = str(cell["benchmark"])
        theme = str(cell["theme"])
        scenario = str(cell["scenario"])
        required_group = cell.get("source_group")
        pool = [
            row
            for row in eligible
            if row["benchmark"] == benchmark
            and row["async_classification_plan"]["primary_event_theme"] == theme
            and row["async_classification_plan"]["async_scenario_class"] == scenario
            and (required_group is None or _source_group(row) == required_group)
        ]
        chosen = _select_diverse(
            pool,
            int(cell["count"]),
            source_group_counts[benchmark],
        )
        selected.extend(chosen)
        chosen_ids = {row["case_id"] for row in chosen}
        eligible = [row for row in eligible if row["case_id"] not in chosen_ids]

    compact = []
    for index, row in enumerate(selected):
        compact.append(
            {
                "case_id": row["case_id"],
                "source_task_id": row["source_task_id"],
                "benchmark": row["benchmark"],
                "primary_event_theme": row["async_classification_plan"]["primary_event_theme"],
                "async_scenario_class": row["async_classification_plan"]["async_scenario_class"],
                "capabilities": row["async_classification_plan"]["capabilities"],
                "requires_authored_private_oracle": bool(
                    row["runtime_package_plan"].get("requires_authored_private_oracle")
                ),
                "shard": (index % 3) + 1,
            }
        )
    final_counts = current_counts + Counter(item["primary_event_theme"] for item in compact)
    if dict(final_counts) != FINAL_THEME_TARGETS:
        raise RuntimeError(f"final distribution mismatch: {dict(final_counts)}")
    if len({item["case_id"] for item in compact}) != len(compact):
        raise RuntimeError("duplicate case ids in selection")
    if len({item["source_task_id"] for item in compact}) != len(compact):
        raise RuntimeError("duplicate source task ids in selection")
    benchmark_counts = Counter(item["benchmark"] for item in compact)
    if dict(benchmark_counts) != NEW_BENCHMARK_TARGETS:
        raise RuntimeError(f"new benchmark distribution mismatch: {dict(benchmark_counts)}")
    scenario_counts = Counter(item["async_scenario_class"] for item in compact)
    if dict(scenario_counts) != NEW_SCENARIO_TARGETS:
        raise RuntimeError(f"new scenario distribution mismatch: {dict(scenario_counts)}")
    return {
        "schema_version": "async-rbench-to-100-selection-v1",
        "registered_task_count_before": len(registered),
        "new_case_count": len(compact),
        "target_task_count": 100,
        "current_theme_counts": dict(sorted(current_counts.items())),
        "new_theme_counts": dict(sorted(Counter(item["primary_event_theme"] for item in compact).items())),
        "final_theme_counts": dict(sorted(final_counts.items())),
        "new_benchmark_counts": dict(sorted(benchmark_counts.items())),
        "new_scenario_counts": dict(sorted(scenario_counts.items())),
        "cases": compact,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build_selection()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "cases"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
