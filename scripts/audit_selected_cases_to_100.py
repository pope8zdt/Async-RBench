from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any

from async_rbench.case_ir import validate_case_ir, validate_score_plan
import yaml

from async_rbench.evaluation.event_taxonomy import ASYNC_SCENARIO_CLASSES, EVENT_THEME_IDS


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "candidate_cases" / "rebuild-to-100" / "selection-manifest.json"
DEFAULT_CASES = ROOT / "artifacts" / "case-transformability-audit-v2" / "cases.jsonl"
DEFAULT_OUTPUT = ROOT / "candidate_cases" / "rebuild-to-100" / "selection-audit.json"
REQUIRED_RUNTIME_FIELDS = (
    "docker",
    "environment_strategy",
    "event_injection",
    "hidden_tests",
    "native_runtime_ref",
    "oracle",
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _score_plan(row: dict[str, Any]) -> dict[str, Any]:
    ir = row.get("case_ir_blueprint") or {}
    classification = row.get("async_classification_plan") or {}
    return {
        "schema_version": "1",
        "case_ir_version": "1",
        "event_policy_version": "1",
        "case_id": row.get("case_id"),
        "instance_id": ir.get("instance_id"),
        "primary_event_theme": classification.get("primary_event_theme"),
        "points": row.get("control_score_blueprint") or [],
        "negative_mutations": row.get("negative_mutation_blueprint") or [],
    }


def _registered_source_ids(root: Path) -> set[str]:
    registry_path = root / "cases" / "registry.json"
    if not registry_path.exists():
        return set()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for family in registry.get("case_families") or []:
        family_dir = root / "cases" / str(family.get("case_id") or "")
        for instance in family.get("instances") or []:
            relative = Path() if instance.get("path") == "." else Path(str(instance.get("path") or ""))
            public_path = family_dir / relative / "public_case.yaml"
            if not public_path.exists():
                continue
            public = yaml.safe_load(public_path.read_text(encoding="utf-8")) or {}
            result.update(
                str(source["id"])
                for source in public.get("source_tasks") or []
                if isinstance(source, dict) and source.get("id")
            )
    return result


def audit_selection(
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    root: Path = ROOT,
    registered_source_ids: set[str] | None = None,
) -> dict[str, Any]:
    selected = manifest.get("cases") or []
    row_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        row_groups[str(row.get("case_id") or "")].append(row)

    duplicate_source_ids = {
        source_id
        for source_id, count in Counter(str(item.get("source_task_id") or "") for item in selected).items()
        if source_id and count > 1
    }
    registered_source_ids = (
        _registered_source_ids(root) if registered_source_ids is None else registered_source_ids
    )
    semantic_owners: dict[str, list[str]] = defaultdict(list)
    control_owners: dict[str, list[str]] = defaultdict(list)
    case_results: list[dict[str, Any]] = []

    for item in selected:
        case_id = str(item.get("case_id") or "")
        errors: list[str] = []
        matches = row_groups.get(case_id, [])
        if len(matches) != 1:
            errors.append(f"selection must resolve to exactly one blueprint row; found {len(matches)}")
            row: dict[str, Any] = {}
        else:
            row = matches[0]

        if row:
            for field in ("source_task_id", "benchmark"):
                if str(item.get(field) or "") != str(row.get(field) or ""):
                    errors.append(f"manifest {field} does not match blueprint")

            errors.extend(f"case_ir: {error}" for error in validate_case_ir(row.get("case_ir_blueprint")))
            errors.extend(f"control_plan: {error}" for error in validate_score_plan(_score_plan(row)))

            semantic_digest = str(row.get("semantic_design_digest") or "")
            control_digest = str(row.get("control_design_digest") or "")
            if not semantic_digest:
                errors.append("semantic_design_digest is required")
            else:
                semantic_owners[semantic_digest].append(case_id)
            if not control_digest:
                errors.append("control_design_digest is required")
            else:
                control_owners[control_digest].append(case_id)

            classification = row.get("async_classification_plan") or {}
            theme = str(classification.get("primary_event_theme") or "")
            scenario = str(classification.get("async_scenario_class") or "")
            if theme not in EVENT_THEME_IDS:
                errors.append(f"invalid primary_event_theme: {theme!r}")
            if scenario not in ASYNC_SCENARIO_CLASSES:
                errors.append(f"invalid async_scenario_class: {scenario!r}")
            if not classification.get("classification_basis") or not classification.get("classification_rationale"):
                errors.append("classification basis and rationale are required")
            for field, value in (("primary_event_theme", theme), ("async_scenario_class", scenario)):
                if str(item.get(field) or "") != value:
                    errors.append(f"manifest {field} does not match blueprint")

            runtime = row.get("runtime_package_plan") or {}
            for field in REQUIRED_RUNTIME_FIELDS:
                if not runtime.get(field):
                    errors.append(f"runtime_package_plan.{field} is required")

            source_audit = row.get("source_audit") or {}
            source_files = list(source_audit.get("source_files") or [])
            source_hashes = source_audit.get("source_file_sha256") or {}
            if not source_files:
                errors.append("source_audit.source_files must be non-empty")
            if set(map(str, source_files)) != set(map(str, source_hashes)):
                errors.append("source file list and hash map must have identical paths")
            for relative in source_files:
                source_path = root / str(relative)
                if not source_path.is_file():
                    errors.append(f"source file does not exist: {relative}")
                elif _sha256(source_path) != str(source_hashes.get(str(relative)) or ""):
                    errors.append(f"source file hash mismatch: {relative}")

        source_id = str(item.get("source_task_id") or "")
        if not source_id:
            errors.append("source_task_id is required")
        if source_id in duplicate_source_ids:
            errors.append(f"duplicate selected source_task_id: {source_id}")
        if source_id in registered_source_ids:
            errors.append(f"source_task_id already registered: {source_id}")
        case_results.append({"case_id": case_id, "source_task_id": source_id, "passed": not errors, "errors": errors})

    duplicate_semantic = {key: owners for key, owners in semantic_owners.items() if len(owners) > 1}
    duplicate_control = {key: owners for key, owners in control_owners.items() if len(owners) > 1}
    for result in case_results:
        case_id = result["case_id"]
        row = row_groups.get(case_id, [{}])[0]
        if str(row.get("semantic_design_digest") or "") in duplicate_semantic:
            result["errors"].append("semantic_design_digest is not unique within selection")
        if str(row.get("control_design_digest") or "") in duplicate_control:
            result["errors"].append("control_design_digest is not unique within selection")
        result["passed"] = not result["errors"]

    failed = sum(not result["passed"] for result in case_results)
    expected = int(manifest.get("new_case_count") or len(selected))
    global_errors: list[str] = []
    if len(selected) != expected:
        global_errors.append(f"manifest case count is {len(selected)}, expected {expected}")
    if int(manifest.get("registered_task_count_before") or 0) + len(selected) != int(manifest.get("target_task_count") or 0):
        global_errors.append("registered plus selected count does not equal target_task_count")
    return {
        "schema_version": "async-rbench-selection-audit-v1",
        "passed": failed == 0 and not global_errors,
        "summary": {"selected_count": len(selected), "passed_count": len(selected) - failed, "failed_count": failed},
        "global_errors": global_errors,
        "duplicate_semantic_designs": duplicate_semantic,
        "duplicate_control_designs": duplicate_control,
        "cases": case_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the static quality of the to-100 selection.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = audit_selection(
        json.loads(args.manifest.read_text(encoding="utf-8")),
        _read_jsonl(args.cases),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"] | {"passed": report["passed"]}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
