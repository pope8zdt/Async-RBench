from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import yaml

from .case_quality import validate_case_quality
from .evaluation.event_taxonomy import ASYNC_SCENARIO_CLASSES, EVENT_THEME_IDS
from .evaluation.weighting import (
    DYNAMIC_COMPONENT_MASS, DYNAMIC_CONTROL_DIMENSIONS,
    DYNAMIC_SUCCESS_THRESHOLD, SCORE_POLICY_VERSION, SEMANTIC_COMPONENT_MASS,
)


POLICY_PATH = "dataset_policy.json"
DATASET_SPLITS = {"calibration", "development", "test"}
DIFFICULTIES = {"easy", "medium", "hard"}
DATASET_POLICY_STATUSES = {
    "pre_calibration_locked",
    "post_calibration_locked",
    "frozen",
    "publication_locked",
}
REQUIRED_ACCEPTANCE_GATES = {
    "requires_human_review": bool,
    "requires_public_private_contract_validation": bool,
    "requires_source_instruction_fidelity": bool,
    "requires_scored_claim_public_traceability": bool,
    "requires_oracle_pass": bool,
    "requires_hidden_verifier_pass": bool,
    "minimum_equivalence_solutions": int,
    "minimum_executed_negative_mutations": int,
    "requires_identical_verifier_bundle_across_quality_variants": bool,
    "requires_nonfilesystem_artifact_observers": bool,
    "requires_mutation_design_coverage": bool,
    "requires_provenance_validation": bool,
    "requires_dynamic_decision_contract": bool,
    "minimum_critical_dynamic_points": int,
}


def load_dataset_policy(root: Path) -> dict[str, Any]:
    path = root / POLICY_PATH
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def validate_dataset_policy(root: Path) -> list[str]:
    path = root / POLICY_PATH
    try:
        policy = load_dataset_policy(root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid dataset policy {path}: {exc}"]
    errors: list[str] = []
    if policy.get("schema_version") != "1.0":
        errors.append(f"{path}: schema_version must be '1.0'")
    if policy.get("status") not in DATASET_POLICY_STATUSES:
        errors.append(
            f"{path}: status must be one of {sorted(DATASET_POLICY_STATUSES)}"
        )
    target = policy.get("target_instance_count")
    allowed = policy.get("allowed_instance_count_range")
    if not isinstance(target, int) or target <= 0:
        errors.append(f"{path}: target_instance_count must be a positive integer")
        target = 0
    if (
        not isinstance(allowed, list) or len(allowed) != 2
        or any(not isinstance(value, int) for value in allowed)
        or (len(allowed) == 2 and allowed[0] > allowed[1])
    ):
        errors.append(f"{path}: allowed_instance_count_range must be [minimum, maximum]")
    elif target and not allowed[0] <= target <= allowed[1]:
        errors.append(f"{path}: target_instance_count is outside the allowed range")

    exact_maps = {
        "splits": DATASET_SPLITS,
        "primary_event_theme_targets": EVENT_THEME_IDS,
        "async_scenario_class_targets": ASYNC_SCENARIO_CLASSES,
        "difficulty_targets": DIFFICULTIES,
    }
    for field, expected_keys in exact_maps.items():
        values = policy.get(field)
        if not isinstance(values, dict) or set(values) != set(expected_keys):
            errors.append(f"{path}: {field} must define exactly {sorted(expected_keys)}")
            continue
        if any(not isinstance(value, int) or value < 0 for value in values.values()):
            errors.append(f"{path}: {field} values must be non-negative integers")
        elif target and sum(values.values()) != target:
            errors.append(f"{path}: {field} values must sum to {target}")

    rubric = policy.get("difficulty_rubric")
    if not isinstance(rubric, dict):
        errors.append(f"{path}: difficulty_rubric must be an object")
    else:
        easy_max = rubric.get("easy_max")
        medium_max = rubric.get("medium_max")
        if not isinstance(easy_max, int) or not isinstance(medium_max, int) or easy_max >= medium_max:
            errors.append(f"{path}: difficulty thresholds must be increasing integers")

    case_id_policy = policy.get("case_id_policy") or {}
    for field in ("maximum_single_case_fraction", "maximum_near_duplicate_fraction"):
        value = case_id_policy.get(field)
        if not isinstance(value, (int, float)) or not 0 < value <= 1:
            errors.append(f"{path}: {field} must be in (0, 1]")
    acceptance = policy.get("acceptance")
    if not isinstance(acceptance, dict):
        errors.append(f"{path}: acceptance must be an object")
    else:
        for gate, expected_type in REQUIRED_ACCEPTANCE_GATES.items():
            value = acceptance.get(gate)
            if expected_type is bool and value is not True:
                errors.append(f"{path}: acceptance.{gate} must be true")
            elif expected_type is int and (
                not isinstance(value, int) or isinstance(value, bool) or value < 1
            ):
                errors.append(f"{path}: acceptance.{gate} must be a positive integer")
        if set(map(str, acceptance.get("required_dynamic_control_dimensions") or [])) != set(
            DYNAMIC_CONTROL_DIMENSIONS
        ):
            errors.append(f"{path}: acceptance dynamic dimensions differ from executable policy")
        if acceptance.get("score_policy_version") != SCORE_POLICY_VERSION:
            errors.append(f"{path}: acceptance score_policy_version is stale")
        if acceptance.get("primary_metric") != "dynamic_control_score":
            errors.append(f"{path}: acceptance.primary_metric must be dynamic_control_score")
        if acceptance.get("dynamic_component_mass") != DYNAMIC_COMPONENT_MASS:
            errors.append(f"{path}: acceptance.dynamic_component_mass differs from executable policy")
        if acceptance.get("semantic_component_mass") != SEMANTIC_COMPONENT_MASS:
            errors.append(f"{path}: acceptance.semantic_component_mass differs from executable policy")
        if acceptance.get("dynamic_success_threshold") != DYNAMIC_SUCCESS_THRESHOLD:
            errors.append(f"{path}: acceptance.dynamic_success_threshold differs from executable policy")
    return errors


def difficulty_profile(case: Any, policy: dict[str, Any]) -> dict[str, Any]:
    """Compute a deterministic structural difficulty label from the case contract."""
    raw = case.raw if hasattr(case, "raw") else case
    milestones = list(raw.get("milestones") or [])
    async_events = list(((raw.get("scenarios") or {}).get("async") or {}).get("events") or [])
    components = {
        "workstreams": len(raw.get("delegation_workstreams") or []),
        "milestones": len(milestones),
        "dependency_edges": sum(len(item.get("depends_on") or []) for item in milestones),
        "artifacts": len(raw.get("artifacts") or []),
        "async_events_x2": 2 * len(async_events),
        "invalidated_artifact_refs": sum(
            len(item.get("invalidates_artifacts") or []) for item in async_events
        ),
        "reopened_milestone_refs": sum(
            len(item.get("reopens_milestones") or []) for item in async_events
        ),
        "instruction_blocks": math.ceil(len(str(raw.get("instruction") or "")) / 4000),
    }
    score = sum(components.values())
    rubric = policy["difficulty_rubric"]
    if score <= int(rubric["easy_max"]):
        label = "easy"
    elif score <= int(rubric["medium_max"]):
        label = "medium"
    else:
        label = "hard"
    return {"rubric_version": policy["schema_version"], "score": score, "label": label, "components": components}


def _task_difficulty(case_dir: Path) -> str:
    value = yaml.safe_load((case_dir / "task" / "task.yaml").read_text(encoding="utf-8"))
    return str((value or {}).get("difficulty") or "")


def _near_duplicate_digest(case: Any) -> str:
    raw = case.raw
    events = ((raw.get("scenarios") or {}).get("async") or {}).get("events") or []
    signature = {
        "source_tasks": sorted(
            (str(item.get("benchmark") or ""), str(item.get("id") or ""))
            for item in raw.get("source_tasks") or []
        ),
        "events": [
            {
                "at": item.get("at"),
                "invalidates_artifacts": sorted(item.get("invalidates_artifacts") or []),
                "reopens_milestones": sorted(item.get("reopens_milestones") or []),
            }
            for item in events
        ],
        "hidden_check_ids": sorted((raw.get("hidden_reverification_commands") or {}).keys()),
    }
    encoded = json.dumps(signature, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_dataset_audit(root: Path, instances: Iterable[Any]) -> dict[str, Any]:
    policy = load_dataset_policy(root)
    registry = json.loads((root / "cases" / "registry.json").read_text(encoding="utf-8"))
    registry_meta = {
        (str(family["case_id"]), str(instance["instance_id"])): {
            "split": instance.get("split"), "benchmark": family.get("benchmark")
        }
        for family in registry.get("case_families") or []
        for instance in family.get("instances") or []
    }
    counters: dict[str, Counter[str]] = {
        "splits": Counter(), "primary_event_theme_targets": Counter(),
        "async_scenario_class_targets": Counter(), "difficulty_targets": Counter(),
        "benchmarks": Counter(), "registered_cases": Counter(),
        "near_duplicate_groups": Counter(),
    }
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    quality_errors: list[str] = []
    split_sources: dict[tuple[str, str], set[str]] = defaultdict(set)
    duplicate_splits: dict[str, set[str]] = defaultdict(set)
    for instance in instances:
        case = instance.load() if hasattr(instance, "load") else instance
        instance_id = str(getattr(instance, "instance_id", "seed-1"))
        key = (case.case_id, instance_id)
        meta = registry_meta.get(key, {})
        split = str(meta.get("split") or "unassigned")
        benchmark = str(meta.get("benchmark") or "unknown")
        classification = case.raw.get("classification") or {}
        primary = str(classification.get("primary_event_theme") or "")
        scenario = str(classification.get("async_scenario_class") or "")
        profile = difficulty_profile(case, policy)
        stored_difficulty = _task_difficulty(case.case_dir)
        duplicate_digest = _near_duplicate_digest(case)
        case_quality_errors = validate_case_quality(root, case.case_dir, require_contract=True)
        quality_errors.extend(
            f"{case.case_id}/{instance_id}: {error}" for error in case_quality_errors
        )
        counters["splits"][split] += 1
        counters["primary_event_theme_targets"][primary] += 1
        counters["async_scenario_class_targets"][scenario] += 1
        counters["difficulty_targets"][profile["label"]] += 1
        counters["benchmarks"][benchmark] += 1
        counters["registered_cases"][case.case_id] += 1
        counters["near_duplicate_groups"][duplicate_digest] += 1
        duplicate_splits[duplicate_digest].add(split)
        for source in case.raw.get("source_tasks") or []:
            source_key = (str(source.get("benchmark") or ""), str(source.get("id") or ""))
            split_sources[source_key].add(split)
        if split not in DATASET_SPLITS:
            errors.append(f"{case.case_id}/{instance_id}: missing or invalid dataset split")
        if stored_difficulty != profile["label"]:
            errors.append(
                f"{case.case_id}/{instance_id}: task difficulty {stored_difficulty!r} "
                f"does not match structural rubric {profile['label']!r} (score {profile['score']})"
            )
        rows.append({
            "case_id": case.case_id, "instance_id": instance_id, "split": split,
            "benchmark": benchmark, "primary_event_theme": primary,
            "async_scenario_class": scenario, "difficulty": profile,
            "stored_difficulty": stored_difficulty, "near_duplicate_digest": duplicate_digest,
            "quality_contract_passed": not case_quality_errors,
            "quality_contract_errors": case_quality_errors,
        })

    for source, splits in split_sources.items():
        if len(splits) > 1:
            errors.append(f"source task {source[0]}/{source[1]} crosses splits: {sorted(splits)}")
    for digest, splits in duplicate_splits.items():
        if len(splits) > 1:
            errors.append(f"near-duplicate group {digest[:12]} crosses splits: {sorted(splits)}")

    target = int(policy["target_instance_count"])
    deficits: dict[str, dict[str, int]] = {}
    overflows: dict[str, dict[str, int]] = {}
    for policy_field, counter_name in (
        ("splits", "splits"),
        ("primary_event_theme_targets", "primary_event_theme_targets"),
        ("async_scenario_class_targets", "async_scenario_class_targets"),
        ("difficulty_targets", "difficulty_targets"),
    ):
        desired = policy[policy_field]
        actual = counters[counter_name]
        deficits[policy_field] = {
            key: max(0, int(value) - actual.get(key, 0)) for key, value in desired.items()
        }
        overflows[policy_field] = {
            key: max(0, actual.get(key, 0) - int(value)) for key, value in desired.items()
        }
        for key, amount in overflows[policy_field].items():
            if amount:
                errors.append(f"{policy_field}.{key} exceeds target by {amount}")

    count = len(rows)
    if count:
        max_case_id = max(counters["registered_cases"].values()) / count
        max_benchmark = max(counters["benchmarks"].values()) / count
        max_duplicate = max(counters["near_duplicate_groups"].values()) / count
    else:
        max_case_id = max_benchmark = max_duplicate = 0.0
    # Concentration limits are final-dataset gates. Report them during expansion without
    # rejecting a deliberately small seed/calibration set.
    concentration = {
        "maximum_case_id_fraction": max_case_id,
        "maximum_benchmark_fraction": max_benchmark,
        "maximum_near_duplicate_fraction": max_duplicate,
        "enforced": count >= int(policy["allowed_instance_count_range"][0]),
    }
    if concentration["enforced"]:
        if max_case_id > float(policy["case_id_policy"]["maximum_single_case_fraction"]):
            errors.append("single-case concentration exceeds the final-dataset limit")
        if max_duplicate > float(policy["case_id_policy"]["maximum_near_duplicate_fraction"]):
            errors.append("near-duplicate concentration exceeds the final-dataset limit")

    quality_contract_complete = not quality_errors
    publication_ready = count == target and not errors and quality_contract_complete
    return {
        "schema_version": "1.0", "policy_status": policy["status"],
        "registered_instance_count": count, "target_instance_count": target,
        "expansion_complete": publication_ready,
        "static_valid": not errors, "errors": sorted(set(errors)),
        "quality_contract_complete": quality_contract_complete,
        "publication_ready": publication_ready,
        "quality_errors": sorted(set(quality_errors)),
        "counts": {name: dict(sorted(counter.items())) for name, counter in counters.items()},
        "deficits": deficits, "overflows": overflows, "concentration": concentration,
        "rows": sorted(rows, key=lambda item: (item["case_id"], item["instance_id"])),
    }
