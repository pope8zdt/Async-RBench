from __future__ import annotations

import ast
import json
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .evaluation.case_contract import (
    CAPABILITY_CATEGORIES,
    MAX_INITIAL_WORKSTREAMS,
    assert_participant_safe,
    find_private_fields,
)
from .evaluation.event_taxonomy import (
    validate_case_classification,
    validate_scenario_events,
)
from .evaluation.weighting import CAPABILITY_TARGETS, RELEVANCE_WEIGHTS


REQUIRED_EXECUTION_MODES = {"linear", "async"}
CASE_INSTANCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class CaseSpec:
    path: Path
    raw: dict[str, Any]

    @property
    def case_id(self) -> str:
        return str(self.raw["case_id"])

    @property
    def case_dir(self) -> Path:
        return self.path.parent


@dataclass(frozen=True)
class CaseInstanceSpec:
    """One immutable instance of a registered case.

    A case family is one of the eight primary event-theme categories. The
    schema-v2 registry key ``case_families`` is retained only for compatibility;
    its entries are registered cases identified by ``case_id``.
    """

    case_id: str
    instance_id: str
    case_dir: Path
    benchmark: str
    control_prefix: str
    # ``split`` is the authoritative dataset split recorded in cases/registry.json
    # (one of calibration / development / test).  The execution layer must filter
    # and stamp it so a formal run cannot silently mix held-out test cases into a
    # headline aggregate or a calibration audit.
    split: str = "unassigned"

    @property
    def contract_path(self) -> Path:
        return self.case_dir / "public_case.yaml"

    def load(self) -> CaseSpec:
        return load_case(self.contract_path)


def case_instance_key(case_id: str, instance_id: str) -> str:
    """Stable JSON-map key for one family/instance pair."""
    return f"{case_id}::{instance_id}"


def load_case(path: Path) -> CaseSpec:
    if path.name != "public_case.yaml":
        raise ValueError(
            f"protocol 3 accepts only public_case.yaml contracts, got: {path}"
        )
    if path.name == "public_case.yaml":
        public = yaml.safe_load(path.read_text(encoding="utf-8"))
        private_path = path.parent / "private" / "private_case.yaml"
        if not private_path.is_file():
            raise FileNotFoundError(f"missing private case contract: {private_path}")
        private = yaml.safe_load(private_path.read_text(encoding="utf-8"))
        if not isinstance(public, dict) or not isinstance(private, dict):
            raise ValueError(f"case contracts must be mappings: {path.parent}")
        if public.get("case_id") != private.get("case_id"):
            raise ValueError(f"public/private case_id mismatch: {path.parent}")
        task_path = path.parent / str(public.get("task_instruction_path") or "task/task.yaml")
        task = yaml.safe_load(task_path.read_text(encoding="utf-8"))
        bindings = dict(private.get("workstream_bindings") or {})
        workstreams = []
        initial_wave = []
        event_assets: dict[str, Any] = {}
        for item in public.get("workstreams") or []:
            stream_id = str(item["id"])
            binding = dict(bindings.get(stream_id) or {})
            workstreams.append({
                "id": stream_id,
                "result_kind": binding.get("result_kind", stream_id),
                "required_evidence_fields": list(item.get("required_evidence_fields") or []),
                "evidence_schema": dict(binding.get("private_evidence_schema") or {}),
                "public_evidence_schema": dict(item.get("evidence_schema") or {}),
                "allowed_files": list(item.get("allowed_files") or []),
                "required_files": list(item.get("required_files") or []),
                "public_result_contract": dict(item.get("public_result_contract") or {}),
                "validator_command": str(binding.get("validator_command") or "true"),
                "validator_timeout_sec": int(binding.get("validator_timeout_sec") or 120),
            })
            initial_wave.append({
                "workstream_id": stream_id,
                "result_kind": binding.get("result_kind", stream_id),
                "task": str(item.get("task") or ""),
                "targets": list(item.get("targets") or []),
                "expected_output": str(item.get("expected_output") or ""),
                "priority": str(item.get("priority") or "normal"),
                "required_evidence_fields": list(item.get("required_evidence_fields") or []),
            })
            assets = binding.get("event_assets")
            if assets:
                event_assets[stream_id] = assets
        observers = dict(private.get("artifact_observers") or {})
        evaluator_injections: list[dict[str, Any]] = []
        private_root = (path.parent / "private").resolve()
        for index, configured in enumerate(private.get("evaluator_injections") or []):
            if not isinstance(configured, dict):
                raise ValueError(f"evaluator_injections[{index}] must be a mapping: {path.parent}")
            receipt_ref = str(configured.get("receipt_path") or "")
            receipt_path = (path.parent / receipt_ref).resolve()
            try:
                receipt_path.relative_to(private_root)
            except ValueError as exc:
                raise ValueError(
                    f"evaluator_injections[{index}].receipt_path must remain under private/: {path.parent}"
                ) from exc
            if receipt_path.suffix != ".json" or not receipt_path.is_file():
                raise FileNotFoundError(
                    f"missing private evaluator receipt for injection {configured.get('id')!r}: {receipt_path}"
                )
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            # This does not make the receipt public: it stays in the evaluator's
            # in-memory case spec until the scheduled gateway delivery.  Validate
            # it here so a private contract cannot accidentally encode a field the
            # public result projection must never reveal.
            assert_participant_safe(payload, surface=f"evaluator injection {configured.get('id')!r}")
            evaluator_injections.append({
                "id": str(configured.get("id") or ""),
                "result_kind": str(configured.get("result_kind") or ""),
                "payload": payload,
            })
        artifacts = []
        for item in public.get("artifacts") or []:
            artifact = dict(item)
            if item.get("id") in observers:
                artifact["observer_command"] = observers[item["id"]]
            artifacts.append(artifact)
        legacy_metadata = dict(private.get("legacy_metadata") or {})
        scenarios = dict(private.get("scenarios") or {})
        legacy_variants = dict(private.get("legacy_variants") or {})
        raw = {
            "format_version": int(public.get("format_version") or 2),
            "case_id": public["case_id"],
            "title": public.get("title", public["case_id"]),
            "source_tasks": public.get("source_tasks", []),
            "milestones": public.get("milestones", []),
            "artifacts": artifacts,
            "delegation_workstreams": workstreams,
            "initial_wave": initial_wave,
            "event_assets": event_assets,
            "evaluator_injections": evaluator_injections,
            "result_contract": private.get("result_contract", {}),
            "authoritative_result_kind": private.get("authoritative_result_kind"),
            "superseded_result_kind": private.get("superseded_result_kind"),
            "variants": legacy_variants,
            "scenarios": scenarios,
            "capabilities": list(private.get("capabilities") or []),
            "classification": dict(private.get("classification") or {}),
            "information_sufficiency": list(private.get("information_sufficiency") or []),
            "reverification_checks": list(public.get("public_checks") or []),
            "reverification_commands": {},
            "hidden_reverification_commands": dict(private.get("hidden_checks") or {}),
            "reverification_anchors": private.get("reverification_anchors", {}),
            "stale_predicate": private.get("stale_predicate"),
            "stale_revalidation": private.get("stale_revalidation", {}),
            "metrics": legacy_metadata.get("metrics", {}),
            "implementation": legacy_metadata.get("implementation", {}),
            "upstream_commit": legacy_metadata.get("upstream_commit"),
            "asset_copies": legacy_metadata.get("asset_copies", []),
            "instruction": str((task or {}).get("instruction") or ""),
        }
        return CaseSpec(path=path, raw=raw)
    raise AssertionError("unreachable")


def discover_cases(root: Path) -> list[CaseSpec]:
    public_paths = sorted((root / "cases").glob("*/public_case.yaml"))
    return [load_case(path) for path in public_paths]


SUPPORTED_CASE_BENCHMARKS = (
    "terminal-bench", "gaia2", "swe-bench", "gaia", "multiagentbench", "osworld",
)
REGISTRY_RELPATH = "cases/registry.json"


def normalize_case_benchmark(value: Any) -> str:
    """Return the canonical registry spelling for a supported source family."""
    compact = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "multi-agent-bench": "multiagentbench",
        "multiagent-bench": "multiagentbench",
        "os-world": "osworld",
        "swebench": "swe-bench",
    }
    return aliases.get(compact, compact)


def load_case_registry(root: Path) -> tuple[dict | None, list[str]]:
    """Load cases/registry.json. Returns (registry, errors)."""
    path = root / REGISTRY_RELPATH
    if not path.is_file():
        return None, [f"missing registered-case registry: {path}"]
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"invalid registered-case registry {path}: {exc}"]
    errors: list[str] = []
    if registry.get("schema_version") != "2":
        errors.append(f"{path}: schema_version must be '2'")
    families = registry.get("case_families")
    if not isinstance(families, list) or not families:
        errors.append(f"{path}: legacy case_families field must contain registered cases")
        return registry, errors
    seen: set[str] = set()
    for family in families:
        case_id = family.get("case_id")
        benchmark = family.get("benchmark")
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"{path}: registered case entry missing case_id: {family!r}")
            continue
        if case_id in seen:
            errors.append(f"{path}: duplicate case_id {case_id!r} in registry")
        seen.add(case_id)
        if normalize_case_benchmark(benchmark) not in SUPPORTED_CASE_BENCHMARKS:
            errors.append(f"{path}: case {case_id!r} has unsupported benchmark {benchmark!r}")
        instances = family.get("instances")
        if not isinstance(instances, list) or not instances:
            errors.append(f"{path}: case {case_id!r} must register a non-empty instances list")
            continue
        seen_instances: set[str] = set()
        family_dir = (root / "cases" / case_id).resolve()
        for instance in instances:
            if not isinstance(instance, dict):
                errors.append(f"{path}: case {case_id!r} has invalid instance entry {instance!r}")
                continue
            instance_id = instance.get("instance_id")
            relative_path = instance.get("path")
            split = instance.get("split")
            if not isinstance(instance_id, str) or not CASE_INSTANCE_ID_RE.fullmatch(instance_id):
                errors.append(
                    f"{path}: case {case_id!r} has invalid instance_id {instance_id!r}"
                )
                continue
            if instance_id in seen_instances:
                errors.append(
                    f"{path}: case {case_id!r} registers duplicate instance_id {instance_id!r}"
                )
            seen_instances.add(instance_id)
            if split not in {"calibration", "development", "test"}:
                errors.append(
                    f"{path}: {case_id!r}/{instance_id!r} must define a valid split"
                )
            if not isinstance(relative_path, str) or not relative_path:
                errors.append(
                    f"{path}: {case_id!r}/{instance_id!r} must define a relative path"
                )
                continue
            candidate = Path(relative_path)
            if candidate.is_absolute():
                errors.append(
                    f"{path}: {case_id!r}/{instance_id!r} path must be relative"
                )
                continue
            resolved = (family_dir / candidate).resolve()
            try:
                resolved.relative_to(family_dir)
            except ValueError:
                errors.append(
                    f"{path}: {case_id!r}/{instance_id!r} path escapes its family directory"
                )
    return registry, errors


def discover_case_instances(
    root: Path, case_ids: list[str] | None = None,
) -> list[CaseInstanceSpec]:
    """Return only explicitly registered instances, in registry order."""
    registry, errors = load_case_registry(root)
    if registry is None or errors:
        raise ValueError("; ".join(errors))
    requested = set(case_ids or [])
    families = list(registry.get("case_families") or [])
    known = {str(family["case_id"]) for family in families}
    unknown = sorted(requested - known)
    if unknown:
        raise ValueError(f"unknown registered case families: {unknown}")
    result: list[CaseInstanceSpec] = []
    for family in families:
        case_id = str(family["case_id"])
        if requested and case_id not in requested:
            continue
        family_dir = (root / "cases" / case_id).resolve()
        for instance in family["instances"]:
            case_dir = (family_dir / str(instance["path"])).resolve()
            contract = case_dir / "public_case.yaml"
            if not contract.is_file():
                raise FileNotFoundError(
                    f"registered instance {case_id!r}/{instance['instance_id']!r} "
                    f"has no public_case.yaml: {case_dir}"
                )
            loaded = load_case(contract)
            if loaded.case_id != case_id:
                raise ValueError(
                    f"registered family {case_id!r} points to contract case_id "
                    f"{loaded.case_id!r}: {contract}"
                )
            result.append(CaseInstanceSpec(
                case_id=case_id,
                instance_id=str(instance["instance_id"]),
                case_dir=case_dir,
                benchmark=str(family["benchmark"]),
                control_prefix=str(family.get("control_prefix") or ""),
                split=str(instance.get("split") or "unassigned"),
            ))
    return result


def resolve_case_instance(root: Path, case_id: str, instance_id: str) -> CaseInstanceSpec:
    matches = [
        instance for instance in discover_case_instances(root, [case_id])
        if instance.instance_id == instance_id
    ]
    if not matches:
        raise ValueError(f"unknown registered case instance: {case_id}/{instance_id}")
    return matches[0]


def validate_case_registry(root: Path, cases: list[CaseSpec]) -> list[str]:
    """Registry-backed integrity check replacing the former fixed case count.

    The registry is the source of truth for official case families: every
    registered family must be present and every discovered family must be
    registered. Candidate cases under candidate_cases/ are intentionally not
    discovered here; case-promote registers them.
    """
    registry, errors = load_case_registry(root)
    if registry is None:
        return errors
    expected = {family["case_id"] for family in registry.get("case_families", [])}
    actual = [case.case_id for case in cases]
    if len(actual) != len(set(actual)):
        duplicates = sorted({case_id for case_id in actual if actual.count(case_id) > 1})
        errors.append(f"duplicate case families discovered: {duplicates}")
    actual_set = set(actual)
    missing = sorted(expected - actual_set)
    if missing:
        errors.append(f"registered case families missing from cases/: {missing}")
    extra = sorted(actual_set - expected)
    if extra:
        errors.append(f"unregistered case families found in cases/: {extra}")
    if not errors:
        try:
            instances = discover_case_instances(root)
        except (ValueError, FileNotFoundError) as exc:
            errors.append(str(exc))
        else:
            keys = [case_instance_key(item.case_id, item.instance_id) for item in instances]
            if len(keys) != len(set(keys)):
                errors.append("registered family/instance keys must be globally unique")
    return errors


def validate_case(spec: CaseSpec) -> list[str]:
    errors: list[str] = []
    raw = spec.raw
    is_public_private_v2 = spec.path.name == "public_case.yaml"
    if not is_public_private_v2:
        return [f"{spec.path}: protocol 3 accepts only public_case.yaml contracts"]

    required_keys = [
        "case_id",
        "title",
        "source_tasks",
        "milestones",
        "artifacts",
        "result_contract",
        "authoritative_result_kind",
        "superseded_result_kind",
        "delegation_workstreams",
        "initial_wave",
        "event_assets",
        "reverification_checks",
        "reverification_commands",
    ]
    required_keys.extend([
        "scenarios", "capabilities", "classification", "information_sufficiency",
    ])
    for key in required_keys:
        if key not in raw:
            errors.append(f"{spec.path}: missing required key {key!r}")

    milestone_ids = [item.get("id") for item in raw.get("milestones", [])]
    if len(milestone_ids) != len(set(milestone_ids)):
        errors.append(f"{spec.path}: milestone ids must be unique")

    artifact_ids = [item.get("id") for item in raw.get("artifacts", [])]
    if len(artifact_ids) != len(set(artifact_ids)):
        errors.append(f"{spec.path}: artifact ids must be unique")
    for artifact in raw.get("artifacts", []):
        path = str(artifact.get("path") or "")
        if (not path.startswith("/") or path.startswith("runtime:") or ":" in path[1:]) \
                and not str(artifact.get("observer_command") or "").strip():
            errors.append(
                f"{spec.path}: non-filesystem artifact {artifact.get('id')!r} "
                "requires a private artifact_observer command"
            )

    scenario_map = raw.get("scenarios", {})
    if set(scenario_map) != REQUIRED_EXECUTION_MODES:
        errors.append(
            f"{spec.path}: scenarios must define exactly linear and async"
        )
    if list((scenario_map.get("linear") or {}).get("events") or []):
        errors.append(f"{spec.path}: linear scenario must not inject evaluator events")

    allowed_results = set(raw.get("result_contract", {}).get("allowed_result_kinds", []))
    if raw.get("authoritative_result_kind") not in allowed_results:
        errors.append(f"{spec.path}: authoritative_result_kind is not allowed")
    superseded_result_kind = raw.get("superseded_result_kind")
    if superseded_result_kind is not None and superseded_result_kind not in allowed_results:
        errors.append(f"{spec.path}: superseded_result_kind is not allowed")
    workstreams = raw.get("delegation_workstreams", [])
    workstream_ids = [item.get("id") for item in workstreams]
    if not workstream_ids or len(workstream_ids) != len(set(workstream_ids)):
        errors.append(f"{spec.path}: delegation_workstreams must be non-empty and unique")
    evaluator_injections = list(raw.get("evaluator_injections") or [])
    injection_ids = [str(item.get("id") or "") for item in evaluator_injections if isinstance(item, dict)]
    injection_kinds = [str(item.get("result_kind") or "") for item in evaluator_injections if isinstance(item, dict)]
    if len(injection_ids) != len(evaluator_injections) or not all(injection_ids) or len(injection_ids) != len(set(injection_ids)):
        errors.append(f"{spec.path}: evaluator_injections must have unique non-empty ids")
    if len(injection_kinds) != len(evaluator_injections) or not all(injection_kinds):
        errors.append(f"{spec.path}: evaluator_injections must have non-empty result kinds")
    if set(injection_kinds) - allowed_results:
        errors.append(f"{spec.path}: evaluator injection result kinds must be allowed")
    if len(injection_kinds) != len(set(injection_kinds)):
        errors.append(f"{spec.path}: evaluator injection result kinds must be unique")
    async_event_ids = {
        str(event.get("id") or "")
        for event in ((scenario_map.get("async") or {}).get("events") or [])
    }
    if set(injection_ids) - async_event_ids:
        errors.append(f"{spec.path}: evaluator injections must target declared async event ids")
    workstream_results = [item.get("result_kind") for item in workstreams]
    participant_result_kinds = allowed_results - set(injection_kinds)
    if set(workstream_results) != participant_result_kinds or len(workstream_results) != len(participant_result_kinds):
        errors.append(
            f"{spec.path}: delegation_workstreams must cover each non-evaluator result kind exactly once"
        )
    known_artifacts = set(artifact_ids)
    known_milestones = set(milestone_ids)
    for mode_name, scenario in scenario_map.items():
        for error in validate_scenario_events(
            (scenario or {}).get("events", []),
            execution_mode=str(mode_name),
            allowed_results=allowed_results,
            workstream_ids=workstream_ids,
            known_artifacts=known_artifacts,
            known_milestones=known_milestones,
        ):
            errors.append(f"{spec.path}: {error}")
    if is_public_private_v2:
        capabilities = set(raw.get("capabilities") or [])
        if not capabilities:
            errors.append(f"{spec.path}: capabilities must be non-empty")
        if capabilities - CAPABILITY_CATEGORIES:
            errors.append(
                f"{spec.path}: unknown capabilities "
                f"{sorted(capabilities - CAPABILITY_CATEGORIES)!r}"
            )
        for error in validate_case_classification(raw.get("classification")):
            errors.append(f"{spec.path}: {error}")
        sufficiency = list(raw.get("information_sufficiency") or [])
        sufficiency_ids = [str(item.get("workstream_id") or "") for item in sufficiency]
        if set(sufficiency_ids) != set(workstream_ids) or len(sufficiency_ids) != len(workstream_ids):
            errors.append(
                f"{spec.path}: information_sufficiency must cover every workstream exactly once"
            )
        for item in sufficiency:
            if item.get("review_status") != "reviewed":
                errors.append(
                    f"{spec.path}: information_sufficiency entry must be reviewed"
                )
            matching = next(
                (
                    stream for stream in workstreams
                    if str(stream.get("id")) == str(item.get("workstream_id"))
                ),
                None,
            )
            if matching is not None and set(item.get("required_output_fields") or []) != set(
                matching.get("required_evidence_fields") or []
            ):
                errors.append(
                    f"{spec.path}: information_sufficiency fields must exactly match "
                    f"public required evidence for {item.get('workstream_id')!r}"
                )
    for item in workstreams:
        evidence_fields = item.get("required_evidence_fields", [])
        if (
            not isinstance(evidence_fields, list)
            or any(not isinstance(field, str) or not field.strip() for field in evidence_fields)
            or len(evidence_fields) != len(set(evidence_fields))
        ):
            errors.append(
                f"{spec.path}: workstream {item.get('id')!r} required_evidence_fields "
                "must be a unique list of non-empty strings"
            )
        allowed_files = item.get("allowed_files")
        required_files = item.get("required_files")
        for field_name, values in (
            ("allowed_files", allowed_files), ("required_files", required_files),
        ):
            if (
                not isinstance(values, list)
                or any(not isinstance(path, str) or not path.strip() for path in values)
                or len(values) != len(set(values))
            ):
                errors.append(
                    f"{spec.path}: workstream {item.get('id')!r} {field_name} "
                    "must be a unique list of non-empty paths"
                )
        if isinstance(allowed_files, list) and isinstance(required_files, list):
            if set(required_files) - set(allowed_files):
                errors.append(
                    f"{spec.path}: workstream {item.get('id')!r} required_files "
                    "must be a subset of allowed_files"
                )
        evidence_schema = item.get("evidence_schema")
        public_evidence_schema = item.get("public_evidence_schema")
        if not isinstance(evidence_schema, dict):
            errors.append(
                f"{spec.path}: workstream {item.get('id')!r} evidence_schema must be an object"
            )
        else:
            if set(evidence_schema) - set(evidence_fields if isinstance(evidence_fields, list) else []):
                errors.append(
                    f"{spec.path}: workstream {item.get('id')!r} evidence_schema "
                    "may constrain only required_evidence_fields"
                )
            for evidence_name, field_spec in evidence_schema.items():
                if not isinstance(field_spec, dict):
                    errors.append(
                        f"{spec.path}: workstream {item.get('id')!r} evidence_schema."
                        f"{evidence_name} must be an object"
                    )
                    continue
                expected_type = field_spec.get("type")
                if expected_type not in {
                    "string", "integer", "number", "boolean", "array", "object",
                }:
                    errors.append(
                        f"{spec.path}: workstream {item.get('id')!r} evidence_schema."
                        f"{evidence_name} has unsupported type {expected_type!r}"
                    )
                if "enum" in field_spec and (
                    not isinstance(field_spec["enum"], list) or not field_spec["enum"]
                ):
                    errors.append(
                        f"{spec.path}: workstream {item.get('id')!r} evidence_schema."
                        f"{evidence_name}.enum must be a non-empty list"
                    )
                if "pattern" in field_spec and (
                    not isinstance(field_spec["pattern"], str)
                    or not field_spec["pattern"]
                ):
                    errors.append(
                        f"{spec.path}: workstream {item.get('id')!r} evidence_schema."
                        f"{evidence_name}.pattern must be a non-empty string"
                    )
                if "min_items" in field_spec and (
                    not isinstance(field_spec["min_items"], int)
                    or isinstance(field_spec["min_items"], bool)
                    or field_spec["min_items"] < 0
                ):
                    errors.append(
                        f"{spec.path}: workstream {item.get('id')!r} evidence_schema."
                        f"{evidence_name}.min_items must be a non-negative integer"
                    )
        if not isinstance(public_evidence_schema, dict):
            errors.append(
                f"{spec.path}: workstream {item.get('id')!r} public evidence_schema "
                "must be an object"
            )
        elif isinstance(evidence_schema, dict):
            required_set = set(evidence_fields if isinstance(evidence_fields, list) else [])
            if set(public_evidence_schema) != required_set or set(evidence_schema) != required_set:
                errors.append(
                    f"{spec.path}: workstream {item.get('id')!r} public/private evidence "
                    "schemas must cover every required evidence field exactly"
                )
            for evidence_name in required_set:
                public_type = (public_evidence_schema.get(evidence_name) or {}).get("type")
                private_type = (evidence_schema.get(evidence_name) or {}).get("type")
                if public_type != private_type:
                    errors.append(
                        f"{spec.path}: workstream {item.get('id')!r} evidence field "
                        f"{evidence_name!r} has different public/private types"
                    )
                public_field = dict(public_evidence_schema.get(evidence_name) or {})
                private_field = dict(evidence_schema.get(evidence_name) or {})
                public_enum = public_field.get("enum")
                if public_enum:
                    if "const" in private_field and private_field["const"] not in public_enum:
                        errors.append(
                            f"{spec.path}: workstream {item.get('id')!r} private const "
                            f"for {evidence_name!r} is absent from its public enum"
                        )
                    if "enum" in private_field and not set(private_field["enum"]) <= set(public_enum):
                        errors.append(
                            f"{spec.path}: workstream {item.get('id')!r} private enum "
                            f"for {evidence_name!r} exceeds its public enum"
                        )
                for structural_key in ("pattern", "min_items"):
                    if (
                        structural_key in private_field
                        and public_field.get(structural_key) != private_field[structural_key]
                    ):
                        errors.append(
                            f"{spec.path}: workstream {item.get('id')!r} private "
                            f"{structural_key} for {evidence_name!r} must be disclosed "
                            "identically in the public structural schema"
                        )
        if not isinstance(item.get("validator_command"), str) or not item["validator_command"].strip():
            errors.append(
                f"{spec.path}: workstream {item.get('id')!r} validator_command "
                "must be a non-empty string"
            )
        else:
            validator_command = str(item["validator_command"])
            referenced_fields = set(re.findall(
                r"\be\s*\[\s*['\"]([^'\"]+)['\"]\s*\]", validator_command,
            )) | set(re.findall(
                r"\be\.get\(\s*['\"]([^'\"]+)['\"]", validator_command,
            ))
            undeclared_fields = referenced_fields - set(
                evidence_fields if isinstance(evidence_fields, list) else []
            )
            if undeclared_fields:
                errors.append(
                    f"{spec.path}: workstream {item.get('id')!r} private validator "
                    f"references evidence fields absent from the public contract: "
                    f"{sorted(undeclared_fields)!r}"
                )
        validator_timeout = item.get("validator_timeout_sec", 120)
        if (
            not isinstance(validator_timeout, int)
            or isinstance(validator_timeout, bool)
            or not 1 <= validator_timeout <= 900
        ):
            errors.append(
                f"{spec.path}: workstream {item.get('id')!r} validator_timeout_sec "
                "must be an integer from 1 to 900"
            )
    initial_wave = raw.get("initial_wave")
    if not isinstance(initial_wave, list) or not initial_wave:
        errors.append(f"{spec.path}: initial_wave must be a non-empty list")
    else:
        wave_entries: list[dict[str, Any]] = []
        for index, item in enumerate(initial_wave):
            prefix = f"{spec.path}: initial_wave[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix} must be an object")
                continue
            wave_entries.append(item)
            if not isinstance(item.get("workstream_id"), str) or not item["workstream_id"].strip():
                errors.append(f"{prefix}: workstream_id must be a non-empty string")
            for field_name in ("task", "expected_output"):
                if not isinstance(item.get(field_name), str) or not item[field_name].strip():
                    errors.append(f"{prefix}: {field_name} must be a non-empty string")
            if item.get("priority") not in {"low", "normal", "high"}:
                errors.append(f"{prefix}: priority must be low, normal or high")
            targets = item.get("targets")
            if not isinstance(targets, list) or any(
                not isinstance(target, str) or not target for target in targets
            ):
                errors.append(f"{prefix}: targets must be a list of non-empty strings")
            elif set(targets) - known_artifacts:
                errors.append(
                    f"{prefix}: targets reference unknown artifacts "
                    f"{sorted(set(targets) - known_artifacts)!r}"
                )
        wave_ids = [item.get("workstream_id") for item in wave_entries]
        if wave_ids:
            if len(wave_ids) != len(set(wave_ids)):
                errors.append(f"{spec.path}: initial_wave workstream ids must be unique")
            if set(wave_ids) != set(workstream_ids):
                errors.append(
                    f"{spec.path}: initial_wave must map one-to-one to delegation_workstreams ids"
                )
            else:
                if len(wave_ids) < 2:
                    errors.append(
                        f"{spec.path}: initial_wave must cover at least two workstreams "
                        "so async execution can start at least two concurrently"
                    )
                if len(wave_ids) > MAX_INITIAL_WORKSTREAMS:
                    errors.append(
                        f"{spec.path}: initial_wave exceeds the fixed harness limit of "
                        f"{MAX_INITIAL_WORKSTREAMS} workstreams"
                    )
                workstream_by_id = {item.get("id"): item for item in workstreams}
                for index, item in enumerate(wave_entries):
                    prefix = f"{spec.path}: initial_wave[{index}]"
                    workstream = workstream_by_id.get(item.get("workstream_id"))
                    if workstream is None:
                        continue
                    if str(item.get("result_kind")) != str(workstream.get("result_kind")):
                        errors.append(
                            f"{prefix}: result_kind must match delegation_workstream "
                            f"{item.get('workstream_id')!r}"
                        )
                    if list(item.get("required_evidence_fields") or []) != list(
                        workstream.get("required_evidence_fields") or []
                    ):
                        errors.append(
                            f"{prefix}: required_evidence_fields must match delegation_workstream "
                            f"{item.get('workstream_id')!r}"
                        )
    unknown_event_asset_streams = set(raw.get("event_assets", {})) - set(workstream_ids)
    if unknown_event_asset_streams:
        errors.append(
            f"{spec.path}: event_assets reference unknown workstreams "
            f"{sorted(unknown_event_asset_streams)!r}"
        )
    authority_kind = str(raw.get("authoritative_result_kind") or "")
    authority_workstreams = [
        str(item.get("id")) for item in workstreams
        if str(item.get("result_kind")) == authority_kind
    ]
    authority_is_evaluator_injected = authority_kind in set(injection_kinds)
    if authority_is_evaluator_injected:
        if authority_workstreams:
            errors.append(
                f"{spec.path}: evaluator-injected authority must not also be a participant workstream"
            )
        if injection_kinds.count(authority_kind) != 1:
            errors.append(f"{spec.path}: authoritative evaluator injection must be unique")
    elif len(authority_workstreams) != 1:
        errors.append(
            f"{spec.path}: authoritative_result_kind must map to exactly one workstream"
        )
    elif not list((raw.get("event_assets") or {}).get(authority_workstreams[0]) or []):
        errors.append(
            f"{spec.path}: authoritative workstream {authority_workstreams[0]!r} "
            "must own at least one evaluator-scoped event asset"
        )
    scheduled_results = {
        event.get("result") for variant in scenario_map.values()
        for event in variant.get("events", []) if event.get("result") is not None
    }
    if scheduled_results - allowed_results:
        errors.append(f"{spec.path}: scheduled result kinds missing from result_contract")
    checks = raw.get("reverification_checks", [])
    hidden_checks = set(raw.get("hidden_reverification_commands", {}))
    if len(checks) != len(set(checks)):
        errors.append(f"{spec.path}: reverification_checks must be unique")
    if int(raw.get("format_version") or 1) < 2:
        if not checks:
            errors.append(f"{spec.path}: reverification_checks must be non-empty")
        if set(raw.get("reverification_commands", {})) != set(checks):
            errors.append(f"{spec.path}: reverification_commands must cover every check exactly")
    elif set(raw.get("reverification_commands", {})) != set(checks):
        errors.append(f"{spec.path}: public reverification commands must cover every public check")
    all_checks = set(checks) | hidden_checks
    anchors = raw.get("reverification_anchors", {})
    if set(anchors) - all_checks:
        errors.append(f"{spec.path}: reverification_anchors reference unknown checks")
    for check_id, result_kinds in anchors.items():
        if not result_kinds or set(result_kinds) - allowed_results:
            errors.append(
                f"{spec.path}: reverification anchor {check_id!r} has unknown or empty result kinds"
            )
    predicate = raw.get("stale_predicate")
    if predicate:
        if predicate.get("type") != "revision_mismatch":
            errors.append(f"{spec.path}: unsupported stale_predicate type")
        if (
            not predicate.get("authoritative_fields")
            or len(predicate.get("authoritative_fields", []))
            != len(predicate.get("superseded_fields", []))
        ):
            errors.append(f"{spec.path}: stale_predicate revision fields must be paired")
    revalidation = raw.get("stale_revalidation", {}).get("artifact_checks", {})
    candidate_checks = set(raw.get("stale_revalidation", {}).get("candidate_checks", []))
    if set(revalidation) - known_artifacts:
        errors.append(f"{spec.path}: stale_revalidation references unknown artifacts")
    if any(set(value) - all_checks for value in revalidation.values()):
        errors.append(f"{spec.path}: stale_revalidation references unknown checks")
    if candidate_checks - all_checks:
        errors.append(f"{spec.path}: stale_revalidation candidate_checks reference unknown checks")
    if is_public_private_v2:
        public_contract = yaml.safe_load(spec.path.read_text(encoding="utf-8"))
        task_path = spec.case_dir / str(
            public_contract.get("task_instruction_path") or "task/task.yaml"
        )
        task_contract = yaml.safe_load(task_path.read_text(encoding="utf-8"))
        for surface_name, surface in (
            ("public_case", public_contract),
            ("task_instruction", task_contract),
        ):
            for hit in find_private_fields(surface):
                errors.append(
                    f"{spec.path}: {surface_name} exposes evaluator-private field {hit}"
                )
        visible_text = yaml.safe_dump(
            {"public": public_contract, "task": task_contract},
            allow_unicode=True, sort_keys=True,
        )
        for result_role in allowed_results:
            if str(result_role) and str(result_role) in visible_text:
                errors.append(
                    f"{spec.path}: participant surface exposes private result role"
                )
        forbidden_policy_terms = (
            "authoritative_result_kind", "superseded_result_kind",
            "benchmark_event_id", "stale_visibility", "invalidates_artifacts",
            "reopens_milestones", "evaluator_stale",
        )
        lowered = visible_text.lower()
        for term in forbidden_policy_terms:
            if term in lowered:
                errors.append(
                    f"{spec.path}: participant surface exposes private policy term {term!r}"
                )

    for filename in ("instruction.md", "generate.py", "oracle.py", "verify.py", "PROVENANCE.md"):
        if not (spec.case_dir / filename).exists():
            errors.append(f"{spec.path}: missing {filename}")

    for filename in ("Dockerfile", "docker-compose.yaml", "task.yaml", "run-tests.sh", "oracle.sh"):
        if not (spec.case_dir / "task" / filename).exists():
            errors.append(f"{spec.path}: missing task/{filename}")

    if not any(
        (spec.case_dir / "task" / dirname).is_dir()
        for dirname in ("assets", "task_file")
    ):
        errors.append(
            f"{spec.path}: task must contain a public payload directory: assets/ or task_file/"
        )

    registry_path = spec.case_dir / "task/tests/semantic_checks.json"
    if not registry_path.is_file():
        errors.append(f"{spec.path}: missing task/tests/semantic_checks.json")
    else:
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            checks = list(registry.get("checks") or [])
            ids = [item.get("id") for item in checks]
            nodes = [item.get("pytest_node") for item in checks]
            categories = [item.get("category") for item in checks]
            descriptions = [item.get("description") for item in checks]
            critical_values = [item.get("critical") for item in checks]
            if not checks or len(ids) != len(set(ids)) or any(not item for item in ids):
                errors.append(f"{spec.path}: semantic check ids must be non-empty and unique")
            if len(nodes) != len(set(nodes)) or any(not item for item in nodes):
                errors.append(f"{spec.path}: semantic pytest nodes must be non-empty and unique")
            if not registry.get("version"):
                errors.append(f"{spec.path}: semantic registry version must be non-empty")
            if any(not item for item in categories):
                errors.append(f"{spec.path}: semantic check categories must be non-empty")
            expected_categories = {
                "authority_final_truth": 4,
                "stale_exclusion": 4,
                "downstream_rebuild": 5,
                "runtime_behavior": 4,
                "lineage_reverification": 4,
                "independent_preservation": 3,
            }
            actual_category_counts = {
                category: categories.count(category) for category in set(categories)
            }
            if str(registry.get("version")) == "2":
                if len(checks) != 24:
                    errors.append(
                        f"{spec.path}: semantic registry v2 must contain exactly 24 checks"
                    )
                if actual_category_counts != expected_categories:
                    errors.append(
                        f"{spec.path}: semantic registry v2 category counts must be "
                        f"{expected_categories!r}, got {actual_category_counts!r}"
                    )
                if any(not isinstance(item, str) or not item.strip() for item in descriptions):
                    errors.append(
                        f"{spec.path}: semantic registry v2 descriptions must be non-empty"
                    )
                if any(not isinstance(item, bool) for item in critical_values):
                    errors.append(
                        f"{spec.path}: semantic registry v2 critical flags must be boolean"
                    )
            semantic_version = str(registry.get("version"))
            if semantic_version == "3":
                if len(checks) != 24:
                    errors.append(
                        f"{spec.path}: semantic registry v3 must contain exactly 24 checks"
                    )
                for index, item in enumerate(checks):
                    if item.get("measurement_type") != "semantic":
                        errors.append(
                            f"{spec.path}: semantic registry v3 check {index} must have "
                            "measurement_type='semantic'"
                        )
            if semantic_version == "4":
                if len(checks) < 4:
                    errors.append(
                        f"{spec.path}: task-causal semantic registry v4 must contain at "
                        "least four independently evidenced checks"
                    )
            if semantic_version in {"3", "4"}:
                for index, item in enumerate(checks):
                    if item.get("measurement_type") != "semantic":
                        errors.append(
                            f"{spec.path}: semantic registry v{semantic_version} check {index} must have "
                            "measurement_type='semantic'"
                        )
                    if item.get("capability_target") not in CAPABILITY_TARGETS:
                        errors.append(
                            f"{spec.path}: semantic registry v{semantic_version} check {index} has invalid "
                            "capability_target"
                        )
                    if item.get("relevance_tier") not in RELEVANCE_WEIGHTS:
                        errors.append(
                            f"{spec.path}: semantic registry v{semantic_version} check {index} has invalid "
                            "relevance_tier"
                        )
            tests_root = (spec.case_dir / "task/tests").resolve()
            for node in nodes:
                if not node or "::" not in str(node):
                    errors.append(f"{spec.path}: invalid semantic pytest node {node!r}")
                    continue
                relative_file, *selectors = str(node).split("::")
                test_file = (tests_root / relative_file).resolve()
                if not test_file.is_relative_to(tests_root) or not test_file.is_file():
                    errors.append(f"{spec.path}: semantic pytest file does not exist: {relative_file!r}")
                    continue
                # Author test files are not ours: a non-raw regex in one of them
                # (e.g. '*/\.*') raises a SyntaxWarning during parse that would
                # otherwise spam every validate/run log.  This parse is only a
                # node-existence check, so the warning carries no signal here.
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", SyntaxWarning)
                    tree = ast.parse(test_file.read_text(encoding="utf-8"))
                function_names = {
                    item.name for item in ast.walk(tree)
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                if not selectors or selectors[-1] not in function_names:
                    errors.append(f"{spec.path}: semantic pytest target does not exist: {node!r}")
        except (OSError, ValueError, TypeError, SyntaxError) as exc:
            errors.append(f"{spec.path}: invalid semantic check registry: {exc}")

    return errors
