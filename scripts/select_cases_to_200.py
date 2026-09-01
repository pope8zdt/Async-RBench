#!/usr/bin/env python3
"""Freeze the next individualized rebuild queue at 200 formal case families.

The selector keeps the unregistered portion of the reviewed to-100 queue, then
fills the remaining slots from the 607-case transformability audit.  It excludes
registered case/source identities and solves benchmark/theme quotas as a small
integer max-flow problem before selecting task-specific rows.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "artifacts/case-transformability-audit-v2/cases.jsonl"
REGISTRY = ROOT / "cases/registry.json"
SEED = ROOT / "candidate_cases/rebuild-to-100/selection-manifest.json"
OUTPUT = ROOT / "candidate_cases/rebuild-to-200/selection-manifest.json"
TARGET = 200
THEME_TARGETS = {
    "delayed_authoritative_result": 25,
    "late_or_out_of_order_superseded_result": 25,
    "partial_then_complete_result": 25,
    "conflicting_valid_results": 25,
    "duplicate_or_replayed_completion": 25,
    "child_failure_or_implicit_error": 25,
    "task_scope_or_dependency_change": 25,
    "straggler_under_resource_pressure": 25,
}
# The six available Terminal-Bench source tasks are already represented by the
# official seed families, so the 200-family expansion adds source-diverse MAB,
# SWE-bench, and OSWorld tasks instead of manufacturing Terminal-Bench clones.
BENCHMARK_TARGETS = {
    "MultiAgentBench": 73,
    "SWE-bench": 68,
    "OSWorld": 47,
    "Terminal-Bench": 11,
    "GAIA2": 1,
}
BENCHMARK_NORMALIZATION = {
    "multiagentbench": "MultiAgentBench", "swe-bench": "SWE-bench",
    "terminal-bench": "Terminal-Bench", "osworld": "OSWorld", "gaia2": "GAIA2",
}


def read_rows() -> list[dict[str, Any]]:
    return [json.loads(line) for line in AUDIT.read_text(encoding="utf-8").splitlines() if line.strip()]


def registered_state() -> tuple[Counter[str], Counter[str], set[str], set[str]]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    themes: Counter[str] = Counter()
    benchmarks: Counter[str] = Counter()
    case_ids: set[str] = set()
    source_ids: set[str] = set()
    for family in registry.get("case_families") or []:
        case_id = str(family["case_id"])
        case_ids.add(case_id)
        benchmarks[BENCHMARK_NORMALIZATION[str(family["benchmark"]).lower()]] += 1
        private = yaml.safe_load((ROOT / "cases" / case_id / "private/private_case.yaml").read_text(encoding="utf-8"))
        public = yaml.safe_load((ROOT / "cases" / case_id / "public_case.yaml").read_text(encoding="utf-8"))
        themes[str((private.get("classification") or {}).get("primary_event_theme"))] += 1
        source_ids.update(str(item["id"]) for item in public.get("source_tasks") or [] if item.get("id"))
    return themes, benchmarks, case_ids, source_ids


def source_group(row: dict[str, Any]) -> str:
    source_id = str(row["source_task_id"])
    if row["benchmark"] == "MultiAgentBench":
        return source_id.split(":", 1)[0]
    if row["benchmark"] == "SWE-bench":
        return source_id.split("__", 1)[0]
    native = (row.get("runtime_package_plan") or {}).get("native_runtime_ref") or {}
    return str(native.get("snapshot") or source_id.split(":", 2)[1])


def priority(row: dict[str, Any], group_counts: Counter[str]) -> tuple[Any, ...]:
    return (
        group_counts[source_group(row)],
        -len(row.get("control_score_blueprint") or []),
        -len(row.get("semantic_score_blueprint") or []),
        str(row["case_id"]),
    )


def max_flow_cells(
    supplies: dict[str, int], demands: dict[str, int], capacities: dict[tuple[str, str], int],
) -> dict[tuple[str, str], int]:
    source, sink = "@source", "@sink"
    residual: dict[str, dict[str, int]] = defaultdict(dict)
    original: dict[tuple[str, str], int] = {}

    def edge(left: str, right: str, capacity: int) -> None:
        residual[left][right] = capacity
        residual[right].setdefault(left, 0)
        original[(left, right)] = capacity

    for benchmark, count in supplies.items():
        edge(source, f"b:{benchmark}", count)
    for (benchmark, theme), count in capacities.items():
        edge(f"b:{benchmark}", f"t:{theme}", count)
    for theme, count in demands.items():
        edge(f"t:{theme}", sink, count)

    total = 0
    while True:
        parent: dict[str, str | None] = {source: None}
        queue = deque([source])
        while queue and sink not in parent:
            left = queue.popleft()
            for right, capacity in residual[left].items():
                if capacity > 0 and right not in parent:
                    parent[right] = left
                    queue.append(right)
        if sink not in parent:
            break
        amount = 10**9
        node = sink
        while parent[node] is not None:
            amount = min(amount, residual[parent[node]][node])
            node = parent[node]
        node = sink
        while parent[node] is not None:
            left = parent[node]
            residual[left][node] -= amount
            residual[node][left] = residual[node].get(left, 0) + amount
            node = left
        total += amount
    required = sum(supplies.values())
    if total != required or total != sum(demands.values()):
        raise RuntimeError(f"quota flow infeasible: routed={total}, required={required}")
    return {
        (benchmark, theme): original[(f"b:{benchmark}", f"t:{theme}")] - residual[f"b:{benchmark}"][f"t:{theme}"]
        for benchmark, theme in capacities
        if original[(f"b:{benchmark}", f"t:{theme}")] - residual[f"b:{benchmark}"][f"t:{theme}"]
    }


def main() -> int:
    rows = read_rows()
    by_id = {str(row["case_id"]): row for row in rows}
    current_themes, current_benchmarks, registered_ids, used_sources = registered_state()
    seed_ids = [
        str(item["case_id"])
        for item in json.loads(SEED.read_text(encoding="utf-8"))["cases"]
        if str(item["case_id"]) not in registered_ids
        and str(item["case_id"]) in by_id
    ]
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for case_id in seed_ids:
        row = by_id[case_id]
        source_id = str(row["source_task_id"])
        if source_id in used_sources:
            continue
        selected.append(row); selected_ids.add(case_id); used_sources.add(source_id)
        current_themes[str(row["async_classification_plan"]["primary_event_theme"])] += 1
        current_benchmarks[str(row["benchmark"])] += 1

    supplies = {key: target - current_benchmarks[key] for key, target in BENCHMARK_TARGETS.items()}
    if any(value < 0 for value in supplies.values()):
        raise RuntimeError(f"seed queue exceeds benchmark targets: {supplies}")
    remaining_count = TARGET - sum(current_benchmarks.values())
    if sum(supplies.values()) != remaining_count:
        raise RuntimeError("target arithmetic mismatch")
    pool = [
        row for row in rows
        if row["transformability"]["can_be_formal_case_task"] is True
        and str(row["case_id"]) not in registered_ids | selected_ids
        and str(row["source_task_id"]) not in used_sources
        and row["benchmark"] in supplies
    ]
    group_counts: Counter[str] = Counter(source_group(row) for row in selected)
    additions: list[dict[str, Any]] = []
    for benchmark, count in sorted(supplies.items()):
        available = [row for row in pool if row["benchmark"] == benchmark]
        for _ in range(count):
            if not available:
                raise RuntimeError(f"source-diverse pool exhausted for {benchmark}")
            pick = min(
                available,
                key=lambda row: (
                    current_themes[str(row["async_classification_plan"]["primary_event_theme"])],
                    *priority(row, group_counts),
                ),
            )
            additions.append(pick)
            group_counts[source_group(pick)] += 1
            theme = str(pick["async_classification_plan"]["primary_event_theme"])
            current_themes[theme] += 1
            source_id = str(pick["source_task_id"])
            available = [row for row in available if str(row["source_task_id"]) != source_id]
    selected.extend(additions)
    if len(selected) != TARGET - len(registered_ids):
        raise RuntimeError(f"selected {len(selected)} candidates, expected {TARGET - len(registered_ids)}")
    items = []
    for index, row in enumerate(sorted(selected, key=lambda value: str(value["case_id"])), 1):
        items.append({
            "case_id": row["case_id"], "source_task_id": row["source_task_id"],
            "benchmark": row["benchmark"],
            "primary_event_theme": row["async_classification_plan"]["primary_event_theme"],
            "async_scenario_class": row["async_classification_plan"]["async_scenario_class"],
            "semantic_point_count": len(row.get("semantic_score_blueprint") or []),
            "control_point_count": len(row.get("control_score_blueprint") or []),
            "shard": 1 + ((index - 1) % 4),
            "carried_from_to_100": row["case_id"] in seed_ids,
            "requires_authored_private_oracle": bool(row.get("private_oracle_requirement")),
        })
    payload = {
        "schema_version": "async-rbench-to-200-selection-v1",
        "target_case_family_count": TARGET,
        "registered_case_family_count_before": len(registered_ids),
        "selected_rebuild_count": len(items),
        "carried_from_to_100_count": sum(item["carried_from_to_100"] for item in items),
        "new_from_607_audit_count": sum(not item["carried_from_to_100"] for item in items),
        "theme_balance_goal": THEME_TARGETS,
        "projected_final_theme_counts": dict(sorted(current_themes.items())),
        "final_benchmark_targets": BENCHMARK_TARGETS,
        "additional_cell_allocation": dict(sorted(Counter(
            f"{row['benchmark']}|{row['async_classification_plan']['primary_event_theme']}"
            for row in additions
        ).items())),
        "cases": items,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in (
        "target_case_family_count", "registered_case_family_count_before",
        "selected_rebuild_count", "carried_from_to_100_count", "new_from_607_audit_count",
    )}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
