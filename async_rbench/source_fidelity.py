from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .spec import normalize_case_benchmark


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _active_text(candidate: Path) -> str:
    roots = [
        candidate / "task/oracle.sh", candidate / "task/upstream_solutions",
        candidate / "task/tests", candidate / "task/task_file/scripts/write_manifest.py",
        candidate / "private/runtime_contract.json", candidate / "PROVENANCE.md",
    ]
    parts: list[str] = []
    for root in roots:
        if root.is_file():
            parts.append(root.as_posix())
            parts.append(root.read_text(encoding="utf-8", errors="replace"))
        elif root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.suffix.lower() in {".py", ".sh", ".json", ".yaml", ".yml", ".md"}:
                    parts.append(path.relative_to(candidate).as_posix())
                    parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def validate_candidate_source_fidelity(candidate: Path) -> list[str]:
    """Reject runnable candidates whose active evaluator still measures a seed task."""
    errors: list[str] = []
    public = _load(candidate / "public_case.yaml")
    sources = list(public.get("source_tasks") or [])
    source_ids = [str(item.get("id") or "") for item in sources if item.get("id")]
    benchmarks = {
        normalize_case_benchmark(item.get("benchmark"))
        for item in sources if item.get("benchmark")
    }
    if not source_ids:
        return [f"{candidate}: source-fidelity audit requires at least one source task"]
    active = _active_text(candidate)
    merger_source = "multi-source-data-merger" in source_ids
    residues = {
        "multi-source-data-merger": "Terminal-Bench merger source identity",
        "test_merged_data_exact_values": "merger value test",
        "test_conflict_report_values": "merger conflict-report test",
        "/data/source_a/users": "merger source-A asset",
    }
    if not merger_source:
        for needle, label in residues.items():
            if needle in active:
                errors.append(f"{candidate}: active package retains foreign {label}: {needle!r}")

    registry_path = candidate / "task/tests/semantic_checks.json"
    registry = _load(registry_path)
    checks = list(registry.get("checks") or [])
    source_checks = [
        item for item in checks
        if str(item.get("category") or "") == "source_semantics"
    ]
    if benchmarks & {"multiagentbench", "osworld"} and len(source_checks) < 4:
        errors.append(
            f"{registry_path}: requires at least four task-native source_semantics checks; "
            f"found {len(source_checks)}"
        )
    if "swe-bench" in benchmarks:
        swe_native = [
            item for item in checks
            if str(item.get("category") or "") in {
                "source_semantics", "changed_behavior", "source_native_regression",
            }
            and "native" in (
                str(item.get("id") or "") + " "
                + str(item.get("description") or "") + " "
                + str(item.get("pytest_node") or "")
            ).lower()
        ]
        if not swe_native:
            errors.append(f"{registry_path}: SWE-bench case has no source-native regression point")

    if len(source_ids) == 1:
        manifest_path = candidate / "task/task_file/scripts/write_manifest.py"
        if manifest_path.is_file() and source_ids[0] not in manifest_path.read_text(encoding="utf-8"):
            errors.append(f"{manifest_path}: does not bind the declared source task {source_ids[0]!r}")
        provenance = candidate / "PROVENANCE.md"
        if provenance.is_file() and source_ids[0] not in provenance.read_text(encoding="utf-8"):
            errors.append(f"{provenance}: does not name the declared source task {source_ids[0]!r}")

    if benchmarks & {"multiagentbench", "osworld"}:
        leaked = candidate / "task/task_file/native_canonical_report.json"
        if leaked.exists():
            errors.append(f"{leaked}: evaluator-owned native truth is participant-visible")
        source_point_ids = {str(item.get("id") or "") for item in source_checks}
        quality = _load(candidate / "private/quality_contract.yaml")
        challenged = {
            str(point_id)
            for mutation in quality.get("negative_mutations") or []
            for point_id in mutation.get("must_fail") or []
        }
        if source_point_ids and not source_point_ids.intersection(challenged):
            errors.append(
                f"{candidate / 'private/quality_contract.yaml'}: no executable negative mutation "
                "directly challenges a task-native semantic point"
            )
    return errors
