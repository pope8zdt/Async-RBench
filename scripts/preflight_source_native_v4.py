"""Audit source-native v4 bindings without claiming native task execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.source_native_v4 import file_hash  # noqa: E402
from async_rbench.native_runtime_registry import (  # noqa: E402
    RUNTIME_REPORT_FIELDS,
    qualification,
    read_registry,
    synchronize_runtime_metadata,
)
from async_rbench.unified_case_v3 import read_json, read_jsonl  # noqa: E402


FORBIDDEN_KEYS = {"expected_action_ids", "candidate_action_ids", "stale_action_ids", "closure_hash"}


def resolve_contained(base: Path, relative: Any, label: str) -> tuple[Path | None, str | None]:
    if not isinstance(relative, str) or not relative.strip():
        return None, f"{label}_missing"
    value = Path(relative)
    if value.is_absolute():
        return None, f"{label}_absolute"
    base = base.resolve()
    candidate = (base / value).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None, f"{label}_outside_root"
    return candidate, None


def expected_source_task_id(benchmark: str, binding: dict[str, Any]) -> str:
    if benchmark == "OSWorld":
        return f"osworld:{binding.get('domain', '')}:{binding.get('task_id', '')}"
    if benchmark == "SWE-bench":
        return str(binding.get("instance_id") or "")
    return str(binding.get("task_id") or "")


def audit_marble_source_record(source: Path, binding: dict[str, Any]) -> list[str]:
    line_number = binding.get("line_number")
    if not isinstance(line_number, int) or line_number < 1:
        return ["marble_source_line_number_invalid"]
    try:
        with source.open("r", encoding="utf-8") as handle:
            for current, raw_line in enumerate(handle, 1):
                if current == line_number:
                    payload = json.loads(raw_line)
                    break
            else:
                return ["marble_source_line_missing"]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"marble_source_record_unreadable:{type(exc).__name__}"]
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    errors: list[str] = []
    if digest != binding.get("record_sha256"):
        errors.append("marble_source_record_hash_mismatch")
    if str(payload.get("scenario") or "") != str(binding.get("scenario") or ""):
        errors.append("marble_source_record_scenario_mismatch")
    try:
        normalized_task_id = f"{payload['scenario']}:{int(payload['task_id']):03d}"
    except (KeyError, TypeError, ValueError):
        errors.append("marble_source_record_task_id_invalid")
    else:
        if normalized_task_id != str(binding.get("task_id") or ""):
            errors.append("marble_source_record_task_id_mismatch")
    return errors


def forbidden_paths(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_KEYS or key.endswith("action_ids"):
                found.append(child_path)
            found.extend(forbidden_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(forbidden_paths(child, f"{path}[{index}]"))
    return found


def audit_case(root: Path, row: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    case_dir, containment_error = resolve_contained(root, row.get("native_path"), "native_path")
    if containment_error:
        return [containment_error]
    assert case_dir is not None
    if case_dir.name != str(row.get("case_id") or ""):
        return ["native_path_case_id_mismatch"]
    spec_path = case_dir / "native_case.json"
    errors: list[str] = []
    try:
        spec = read_json(spec_path)
        jsonschema.validate(spec, schema)
    except Exception as exc:
        return [f"schema:{type(exc).__name__}:{exc}"]
    leaks = forbidden_paths(spec)
    if leaks:
        errors.append("answer_leak:" + ",".join(leaks))
    participant_path = case_dir / "participant_task.json"
    if not participant_path.is_file():
        errors.append("participant_task_missing")
    else:
        participant = read_json(participant_path)
        participant_leaks = forbidden_paths(participant)
        if participant_leaks:
            errors.append("participant_answer_leak:" + ",".join(participant_leaks))
        private_keys = {"native_evaluator", "FAIL_TO_PASS", "PASS_TO_PASS", "patch", "test_patch", "fix_patch"}
        if isinstance(participant, dict) and private_keys.intersection(participant):
            errors.append("participant_private_evaluator_material")
    benchmark = spec["benchmark"]
    binding = spec["source_binding"]
    if spec.get("case_id") != row.get("case_id"):
        errors.append("manifest_spec_case_id_mismatch")
    if benchmark != row.get("benchmark"):
        errors.append("manifest_spec_benchmark_mismatch")
    if expected_source_task_id(benchmark, binding) != str(row.get("source_task_id") or ""):
        errors.append("manifest_spec_source_task_id_mismatch")
    if benchmark == "OSWorld":
        source, source_error = resolve_contained(ROOT, binding.get("config_path"), "osworld_config_path")
        if source_error:
            errors.append(source_error)
        elif not source.is_file() or file_hash(source) != binding["config_sha256"]:
            errors.append("osworld_source_hash_mismatch")
        if not (case_dir / "task_meta.json").is_file():
            errors.append("osworld_task_meta_missing")
        if not spec["native_evaluator"].get("func"):
            errors.append("osworld_evaluator_missing")
    elif benchmark == "SWE-bench":
        evaluator = spec["native_evaluator"]
        if not evaluator.get("FAIL_TO_PASS"):
            errors.append("swe_fail_to_pass_empty")
        if not binding.get("repo") or not binding.get("base_commit"):
            errors.append("swe_checkout_binding_incomplete")
        if not (case_dir / "evaluation_binding.json").is_file():
            errors.append("swe_evaluation_binding_missing")
    else:
        source, source_error = resolve_contained(ROOT, binding.get("jsonl_path"), "marble_jsonl_path")
        if source_error:
            errors.append(source_error)
        elif not source.is_file():
            errors.append("marble_source_missing")
        else:
            errors.extend(audit_marble_source_record(source, binding))
        config_path = case_dir / "native_config.yaml"
        if not config_path.is_file():
            errors.append("marble_config_missing")
        else:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            for key in ("coordinate_mode", "llm", "environment", "agents", "task", "metrics", "output"):
                if not config.get(key):
                    errors.append(f"marble_config_empty:{key}")
            if not (config.get("environment") or {}).get("type"):
                errors.append("marble_environment_type_empty")
    if spec["quality_gates"].get("runtime_executed") is not False:
        errors.append("runtime_execution_claim_not_false")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="artifacts/source-native-v4")
    parser.add_argument("--runtime-registry", default="artifacts/native-runtime-v4/runtime_registry.jsonl")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    manifest = read_jsonl(root / "native_manifest.jsonl")
    registry = read_registry(Path(args.runtime_registry).resolve())
    production = read_json(root / "production_report.json")
    schema = read_json(ROOT / "schemas" / "source_native_case_v4.schema.json")
    failures = []
    for row in manifest:
        errors = audit_case(root, row, schema)
        qualified, blocker = qualification(
            registry.get(str(row["case_id"])),
            benchmark=str(row["benchmark"]),
            source_task_id=str(row["source_task_id"]),
        )
        if row.get("runtime_ready") is not qualified or row.get("runtime_blocker") != blocker:
            errors.append("runtime_registry_manifest_mismatch")
        if errors:
            failures.append({"case_id": row["case_id"], "benchmark": row["benchmark"], "errors": errors})
    collection_errors: list[str] = []
    expected_summary: dict[str, Any] | None = None
    try:
        _, expected_production, expected_summary = synchronize_runtime_metadata(
            manifest,
            production,
            registry,
            model_evidence_root=Path(args.runtime_registry).resolve().parent,
        )
    except ValueError as exc:
        collection_errors.append(f"runtime_registry_identity_error:{exc}")
    else:
        for field in RUNTIME_REPORT_FIELDS:
            if production.get(field) != expected_production[field]:
                collection_errors.append(f"runtime_production_report_mismatch:{field}")
    runtime_metadata_consistent = not any(
        "runtime_registry_manifest_mismatch" in failure["errors"] for failure in failures
    ) and not collection_errors
    runtime_executed_count = (
        int(expected_summary["runtime_executed_count"])
        if expected_summary is not None
        else 0
    )
    report = {
        "schema_version": "source-native-preflight-v4",
        "audited_count": len(manifest),
        "passed_count": len(manifest) - len(failures),
        "failed_count": len(failures),
        "runtime_qualified_count": sum(row.get("runtime_ready") is True for row in manifest),
        "registry_environment_smoke_qualified_count": (
            int(expected_summary["environment_smoke_ready_count"])
            if expected_summary is not None
            else None
        ),
        "registry_environment_smoke_qualified_by_benchmark": (
            expected_summary["environment_smoke_ready_benchmark_counts"]
            if expected_summary is not None
            else None
        ),
        "registry_native_environment_initialization_count": (
            int(expected_summary["native_environment_initialization_count"])
            if expected_summary is not None
            else None
        ),
        "registry_native_environment_initialization_by_benchmark": (
            expected_summary["native_environment_initialization_benchmark_counts"]
            if expected_summary is not None
            else None
        ),
        "registry_runtime_qualified_count": (
            int(expected_summary["runtime_ready_count"])
            if expected_summary is not None
            else None
        ),
        "passed_by_benchmark": dict(sorted(Counter(r["benchmark"] for r in manifest if not any(f["case_id"] == r["case_id"] for f in failures)).items())),
        "runtime_executed_count": runtime_executed_count,
        "research_claim": "spec_preflight_only",
        "gates": {
            "schema_and_source_binding": not failures,
            "participant_private_material_isolation": not failures,
            "native_state_change_contract": not failures,
            "case_specific_runtime_qualification_started": any(row.get("runtime_ready") is True for row in manifest),
            "runtime_metadata_consistent": runtime_metadata_consistent,
            "native_runtime_execution": runtime_executed_count == len(manifest) and len(manifest) > 0,
            "paired_linear_async_effect_validation": False,
            "formal_promotion": False,
        },
        "collection_errors": collection_errors,
        "failures": failures,
    }
    (root / "preflight_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failures or collection_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
