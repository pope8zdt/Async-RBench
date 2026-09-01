from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from ..spec import case_instance_key, discover_case_instances
from .control_flow_gates import GATE_EXECUTION_MODES, GATE_NAMES
from .weighting import (
    CAPABILITY_TARGETS, DYNAMIC_CONTROL_DIMENSIONS, GATE_DYNAMIC_DIMENSIONS,
    RELEVANCE_WEIGHTS,
)
from ..dynamic_points import (
    DYNAMIC_REGISTRY_VERSION,
    participant_leakage_hits, participant_strategy_leakage_hits,
    validate_dynamic_point_plan, validate_event_contracts,
)


MIN_TASK_CAUSAL_SEMANTIC_POINTS = 4
REQUIRED_CHECK_FIELDS = (
    "id", "pytest_node", "category", "description", "critical",
    "measurement_type", "capability_target", "relevance_tier",
)
LEGACY_CONTROL_FLOW_POINTS_PER_CASE = 4


def _registered_families(root: Path) -> tuple[list[dict], list[str]]:
    """Load registered cases and their per-case control prefixes.

    ``case_families`` is the legacy schema-v2 list name. Its entries are
    registered cases, while the benchmark's eight case families are the eight
    primary event themes.
    """
    registry_path = root / "cases" / "registry.json"
    errors: list[str] = []
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return [], [f"cannot load registered-case registry {registry_path}: {exc}"]
    families = list(registry.get("case_families") or []) if isinstance(registry, dict) else []
    seen: set[str] = set()
    for family in families:
        case_id = str(family.get("case_id") or "")
        if not case_id:
            errors.append(f"{registry_path}: registered case entry missing case_id: {family!r}")
            continue
        if case_id in seen:
            errors.append(f"{registry_path}: duplicate family case_id {case_id!r}")
        seen.add(case_id)
        if not str(family.get("control_prefix") or "").strip():
            errors.append(f"{registry_path}: family {case_id!r} is missing control_prefix")
    return families, errors


def _function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _registry_errors(path: Path) -> tuple[list[str], dict[str, Any] | None]:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return [f"invalid semantic registry {path}: {exc}"], None
    if not isinstance(registry, dict):
        return [f"semantic registry must be an object: {path}"], None

    errors: list[str] = []
    version = registry.get("version")
    if not isinstance(version, str) or not version.strip():
        errors.append(f"{path}: version must be a non-empty string")
    checks = registry.get("checks")
    if not isinstance(checks, list):
        return errors + [f"{path}: checks must be a list"], registry
    if str(version) in {"2", "3"} and len(checks) != 24:
        errors.append(
            f"{path}: frozen semantic registry v{version} expects 24 points, found {len(checks)}"
        )
    if str(version) == "4" and len(checks) < MIN_TASK_CAUSAL_SEMANTIC_POINTS:
        errors.append(
            f"{path}: task-causal semantic registry v4 requires at least "
            f"{MIN_TASK_CAUSAL_SEMANTIC_POINTS} independently evidenced points, "
            f"found {len(checks)}"
        )
    if str(version) not in {"2", "3", "4"}:
        errors.append(f"{path}: unsupported semantic registry version {version!r}")

    source_cache: dict[Path, set[str]] = {}

    ids: set[str] = set()
    nodes: set[str] = set()
    for index, item in enumerate(checks):
        prefix = f"{path}: checks[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        missing = [field for field in REQUIRED_CHECK_FIELDS if field not in item]
        if missing:
            errors.append(f"{prefix} missing fields {missing!r}")
            continue
        check_id = item["id"]
        node = item["pytest_node"]
        for field in ("id", "pytest_node", "category", "description"):
            if not isinstance(item[field], str) or not item[field].strip():
                errors.append(f"{prefix}.{field} must be a non-empty string")
        if not isinstance(item["critical"], bool):
            errors.append(f"{prefix}.critical must be boolean")
        if item.get("measurement_type") != "semantic":
            errors.append(f"{prefix}.measurement_type must be 'semantic'")
        capability = str(item.get("capability_target", ""))
        relevance = str(item.get("relevance_tier", ""))
        if capability not in CAPABILITY_TARGETS:
            errors.append(
                f"{prefix}.capability_target must be one of {sorted(CAPABILITY_TARGETS)!r}"
            )
        if relevance not in RELEVANCE_WEIGHTS:
            errors.append(
                f"{prefix}.relevance_tier must be one of {sorted(RELEVANCE_WEIGHTS)!r}"
            )
        if capability == "base_task_completion" and relevance != "base":
            errors.append(f"{prefix}: base task completion must use relevance_tier 'base'")
        if capability and capability != "base_task_completion" and relevance == "base":
            errors.append(f"{prefix}: async capability must score above the base tier")
        if isinstance(check_id, str) and check_id:
            if check_id in ids:
                errors.append(f"{path}: duplicate semantic check id {check_id!r}")
            ids.add(check_id)
        if isinstance(node, str) and node:
            if node in nodes:
                errors.append(f"{path}: duplicate semantic pytest node {node!r}")
            nodes.add(node)
            if "::" not in node:
                errors.append(f"{prefix}.pytest_node must contain a function selector")
                continue
            source_name, function_name = node.rsplit("::", 1)
            source = (path.parent / source_name).resolve()
            try:
                source.relative_to(path.parent.resolve())
            except ValueError:
                errors.append(f"{prefix}.pytest_node escapes the private test directory")
                continue
            if source not in source_cache:
                if not source.is_file():
                    errors.append(f"{prefix}.pytest_node targets missing file {source_name!r}")
                    source_cache[source] = set()
                else:
                    try:
                        source_cache[source] = _function_names(source)
                    except (OSError, SyntaxError) as exc:
                        errors.append(f"{path}: cannot parse semantic test source {source}: {exc}")
                        source_cache[source] = set()
            if function_name not in source_cache[source]:
                errors.append(f"{prefix}.pytest_node references missing function {function_name!r}")
    return errors, registry


def validate_case_registries(case_spec: dict[str, Any], expected_prefix: str) -> list[str]:
    """Frozen per-case registry audit shared by the official audit and by
    case-promote pre-checks.

    Verifies a content-derived semantic registry plus a supported dynamic
    registry. V2/V3 remain frozen at 24 points for reproducibility. V4 uses
    independently evidenced task-causal checks and therefore has no padded
    target count. V5 remains frozen for control-flow reproducibility, while
    V7 compiles task-causal decision units from Case IR.
    """
    errors: list[str] = []
    case_id = str(case_spec.get("case_id", ""))
    registry_path = case_spec.get("_registry_path")
    if registry_path is not None and not Path(registry_path).is_file():
        errors.append(f"{case_id}: missing semantic registry {registry_path}")
        return errors
    registry_errors, registry = _registry_errors(Path(registry_path))
    errors.extend(registry_errors)
    if registry is None:
        return errors
    semantic_ids = {
        str(item.get("id")) for item in registry.get("checks", []) if isinstance(item, dict)
    }

    control_path = case_spec.get("_control_path")
    if control_path is None or not Path(control_path).is_file():
        errors.append(f"{case_id}: missing control-flow registry {control_path}")
        return errors
    try:
        control = json.loads(Path(control_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        errors.append(f"invalid control-flow registry {control_path}: {exc}")
        return errors
    control_version = str(control.get("version") or "") if isinstance(control, dict) else ""
    checks = control.get("checks") if isinstance(control, dict) else None
    if not isinstance(checks, list):
        errors.append(f"{control_path}: checks must be a list")
        return errors
    if control_version == "4" and len(checks) != LEGACY_CONTROL_FLOW_POINTS_PER_CASE:
        errors.append(
            f"{control_path}: legacy v4 expects {LEGACY_CONTROL_FLOW_POINTS_PER_CASE} "
            "control-flow points"
        )
        return errors
    if control_version in {"5", DYNAMIC_REGISTRY_VERSION}:
        private_case = Path(control_path).parents[2] / "private" / "private_case.yaml"
        private: dict[str, Any] = {}
        events: list[dict[str, Any]] = []
        try:
            import yaml
            private = yaml.safe_load(private_case.read_text(encoding="utf-8")) or {}
            events = (((private.get("scenarios") or {}).get("async") or {}).get("events") or [])
            event_ids = {str(event.get("id")) for event in events if isinstance(event, dict)}
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"cannot load private event contract {private_case}: {exc}")
            event_ids = set()
        event_contracts = list(control.get("event_contracts") or [])
        if control_version == DYNAMIC_REGISTRY_VERSION:
            errors.extend(
                f"{control_path}: {error}"
                for error in validate_event_contracts(
                    event_contracts, event_ids=event_ids,
                )
            )
            schedule_by_id = {
                str(event.get("id") or ""): event
                for event in events if isinstance(event, dict)
            }
            for contract in event_contracts:
                if contract.get("observation_mode") != "gateway_only":
                    continue
                event_id = str(contract.get("event_id") or "")
                scheduled = schedule_by_id.get(event_id) or {}
                arrival = contract.get("arrival_contract") or {}
                expected_results = {
                    str(value) for value in arrival.get("after_results", [])
                }
                if expected_results:
                    observed_results = {
                        str(value) for value in scheduled.get("after_results", [])
                    }
                    if scheduled.get("trigger") != "after_results_delivered":
                        errors.append(
                            f"{private_case}: event {event_id!r} must bind gateway delivery "
                            "to after_results_delivered"
                        )
                    if observed_results != expected_results:
                        errors.append(
                            f"{private_case}: event {event_id!r} after_results does not match "
                            "the V7 arrival contract"
                        )
                    continue
                expected_after = {
                    str(value)
                    for value in arrival.get("after_artifacts", [])
                }
                observed_after = {
                    str(value) for value in scheduled.get("after_artifacts", [])
                }
                if scheduled.get("trigger") != "after_artifacts_committed":
                    errors.append(
                        f"{private_case}: event {event_id!r} must bind its gateway delivery "
                        "to after_artifacts_committed"
                    )
                if observed_after != expected_after:
                    errors.append(
                        f"{private_case}: event {event_id!r} after_artifacts does not match "
                        "the legacy arrival contract"
                    )
        errors.extend(
            f"{control_path}: {error}"
            for error in validate_dynamic_point_plan(
                checks, event_ids=event_ids, expected_prefix=expected_prefix,
                registry_version=control_version,
                event_contracts=event_contracts,
            )
        )
        private_plan = Path(control_path).parents[2] / "private" / "dynamic_point_plan.json"
        try:
            ledger = json.loads(private_plan.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"missing or invalid private dynamic point ledger {private_plan}: {exc}")
        else:
            if ledger != control:
                errors.append(f"{private_plan}: private design ledger must exactly match evaluator registry")
        case_dir = Path(control_path).parents[2]
        for hit in participant_leakage_hits(case_dir, checks):
            errors.append(
                f"{hit['path']}: participant-visible hidden dynamic identifier "
                f"{hit['hidden_identifier']!r}"
            )
        for hit in participant_strategy_leakage_hits(case_dir):
            errors.append(
                f"{hit['path']}: participant-visible procedural control hint "
                f"{hit['procedural_hint']!r}"
            )
        dockerignore = case_dir / "task" / ".dockerignore"
        try:
            ignored = {
                line.strip().lstrip("/").rstrip("/")
                for line in dockerignore.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            }
        except OSError as exc:
            errors.append(f"{dockerignore}: cannot verify participant-image secrecy: {exc}")
        else:
            required_private_paths = {
                "tests", "upstream_solutions", "oracle.sh", "run-tests.sh",
            }
            missing_private_paths = sorted(required_private_paths - ignored)
            if missing_private_paths:
                errors.append(
                    f"{dockerignore}: participant image may expose evaluator assets "
                    f"{missing_private_paths!r}"
                )
    elif control_version != "4":
        errors.append(f"{control_path}: unsupported control-flow registry version {control_version!r}")
    artifact_ids = {str(item.get("id")) for item in case_spec.get("artifacts", [])}
    workstream_ids = {str(item.get("id")) for item in case_spec.get("delegation_workstreams", [])}
    seen_control_ids: set[str] = set()
    observed_dimensions: set[str] = set()
    critical_dynamic_count = 0
    for index, item in enumerate(checks):
        prefix = f"{control_path}: checks[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        check_id = str(item.get("id", ""))
        gate = str(item.get("gate", ""))
        execution_modes = {
            str(value) for value in (item.get("execution_modes") or [])
        }
        dimension = str(item.get("dimension") or "")
        if not check_id.startswith(f"{expected_prefix}.cf.") or check_id in seen_control_ids:
            errors.append(f"{prefix}: id must be unique and start with {expected_prefix}.cf.")
        seen_control_ids.add(check_id)
        if (
            gate not in GATE_NAMES
            or execution_modes != set(GATE_EXECUTION_MODES.get(gate, ()))
        ):
            errors.append(f"{prefix}: gate/execution-mode matrix is not frozen")
        expected_dimension = GATE_DYNAMIC_DIMENSIONS.get(gate)
        if dimension != expected_dimension or dimension not in DYNAMIC_CONTROL_DIMENSIONS:
            errors.append(
                f"{prefix}: dimension must be {expected_dimension!r} for gate {gate!r}"
            )
        observed_dimensions.add(dimension)
        if item.get("measurement_type") != "control":
            errors.append(f"{prefix}.measurement_type must be 'control'")
        capability = str(item.get("capability_target", ""))
        relevance = str(item.get("relevance_tier", ""))
        if capability not in CAPABILITY_TARGETS:
            errors.append(f"{prefix}: invalid capability_target {capability!r}")
        if relevance not in RELEVANCE_WEIGHTS:
            errors.append(f"{prefix}: invalid relevance_tier {relevance!r}")
        if capability == "base_task_completion" or relevance == "base":
            errors.append(f"{prefix}: control-flow points must score above base completion")
        if not isinstance(item.get("critical"), bool):
            errors.append(f"{prefix}.critical must be boolean")
        elif item.get("critical") is True:
            critical_dynamic_count += 1
        if any(str(anchor) not in semantic_ids for anchor in (item.get("outcome_anchors") or [])):
            errors.append(f"{prefix}: outcome anchor is not in semantic registry")
        args = item.get("gate_args") or {}
        if gate == "timely_cancellation":
            if any(str(value) not in workstream_ids for value in args.get("workstreams") or []):
                errors.append(f"{prefix}: unknown workstream in gate_args")
        else:
            referenced_artifacts = [
                *list(args.get("artifacts") or []),
                *list(args.get("preserve_artifacts") or []),
            ]
            if any(str(value) not in artifact_ids for value in referenced_artifacts):
                errors.append(f"{prefix}: unknown artifact in gate_args")

    if control_version in {"4", "5"} and observed_dimensions != set(DYNAMIC_CONTROL_DIMENSIONS):
        errors.append(
            f"{case_id}: control-flow registry must cover every dynamic dimension; "
            f"found {sorted(observed_dimensions)!r}"
        )
    if control_version == DYNAMIC_REGISTRY_VERSION and not observed_dimensions:
        errors.append(f"{case_id}: v6 registry must cover at least one dynamic dimension")
    if critical_dynamic_count < 1:
        errors.append(f"{case_id}: at least one dynamic control point must be critical")
    return errors


def validate_semantic_registries(root: Path) -> list[str]:
    """Validate the frozen semantic-point registries before evaluation runs.

    Official registered cases are taken from cases/registry.json; a registry
    entry is the only way a case joins the audit (candidate_cases/ is not
    auto-discovered). Every registered case must exist under cases/ and carry
    a validated content-derived semantic registry and supported dynamic points.
    """
    families, family_errors = _registered_families(root)
    errors: list[str] = list(family_errors)
    registered = {str(family.get("case_id")) for family in families if family.get("case_id")}
    control_prefixes = {
        str(family.get("case_id")): str(family.get("control_prefix") or "")
        for family in families if family.get("case_id")
    }
    if not registered:
        errors.append("registered-case registry lists no cases")
        return errors

    try:
        instances = discover_case_instances(root)
    except (ValueError, FileNotFoundError) as exc:
        return errors + [str(exc)]
    found_ids = {instance.case_id for instance in instances}
    missing = sorted(registered - found_ids)
    if missing:
        errors.append(f"registered case families missing from cases/: {missing}")
    extra = sorted(found_ids - registered)
    if extra:
        errors.append(f"unregistered case families found in cases/: {extra}")

    instance_keys: set[str] = set()
    for instance in instances:
        case_path = instance.contract_path
        try:
            case = instance.load().raw
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"invalid case spec {case_path}: {exc}")
            continue
        case_id = str(case.get("case_id", ""))
        if not case_id:
            errors.append(f"{case_path}: case_id must be non-empty")
            continue
        instance_key = case_instance_key(case_id, instance.instance_id)
        if instance_key in instance_keys:
            errors.append(f"duplicate instance in semantic registry audit: {instance_key!r}")
        instance_keys.add(instance_key)
        expected_prefix = control_prefixes.get(case_id) or case_id
        registry_path = case_path.parent / "task" / "tests" / "semantic_checks.json"
        control_path = case_path.parent / "task" / "tests" / "control_flow_checks.json"
        case_spec = {**case, "_registry_path": str(registry_path), "_control_path": str(control_path)}
        errors.extend(validate_case_registries(case_spec, expected_prefix))
    return errors
