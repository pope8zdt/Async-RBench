from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PLAN_PATH = "configs/calibration-plan.json"


def load_calibration_plan(root: Path) -> dict[str, Any]:
    value = json.loads((root / PLAN_PATH).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("calibration plan must be an object")
    return value


def validate_calibration_plan(root: Path) -> list[str]:
    path = root / PLAN_PATH
    try:
        plan = load_calibration_plan(root)
        contract = json.loads((root / "evaluation_contract.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid calibration plan {path}: {exc}"]
    errors: list[str] = []
    if plan.get("schema_version") != "1.0":
        errors.append(f"{path}: schema_version must be '1.0'")
    if plan.get("status") != "ready_to_execute_after_preflight":
        errors.append(f"{path}: status must be ready_to_execute_after_preflight")
    if set(plan.get("execution_modes") or []) != set(contract.get("execution_modes") or []):
        errors.append(f"{path}: execution modes must match evaluation_contract.json")
    policy = contract.get("calibration_diagnostics") or {}
    repetitions = plan.get("repetitions_per_model_mode")
    if not isinstance(repetitions, int) or repetitions < int(policy["minimum_repetitions_per_model_mode"]):
        errors.append(f"{path}: insufficient repetitions_per_model_mode")
    models = plan.get("model_panel")
    if not isinstance(models, list):
        return [*errors, f"{path}: model_panel must be a list"]
    ids = [str(item.get("model_id") or "") for item in models if isinstance(item, dict)]
    families = {
        str(item.get("model_family") or "") for item in models
        if isinstance(item, dict) and item.get("model_family")
    }
    if not models:
        errors.append(f"{path}: model_panel must contain at least one executable profile")
    if len(set(ids)) != len(ids) or any(not value for value in ids):
        errors.append(f"{path}: model_id values must be non-empty and unique")
    if not families:
        errors.append(f"{path}: model_panel must name at least one model family")
    for item in models:
        if not isinstance(item, dict):
            errors.append(f"{path}: model_panel entries must be objects")
            continue
        profile = item.get("profile")
        if not isinstance(profile, str) or not (root / profile).is_file():
            errors.append(f"{path}: missing model profile {profile!r}")
    gates = plan.get("decision_gates") or {}
    expected = {
        "minimum_pilot_models": policy["minimum_pilot_models"],
        "minimum_model_families": policy["minimum_model_families"],
        "minimum_repetitions_per_model_mode": policy["minimum_repetitions_per_model_mode"],
        "minimum_executed_mutants_per_case": policy["minimum_executed_mutants_per_case"],
        "minimum_mutation_kill_rate": policy["minimum_mutation_kill_rate"],
        "minimum_critical_mutation_kill_rate": policy["minimum_critical_mutation_kill_rate"],
        "maximum_mean_async_X": policy["reference_maximum_mean_dynamic_X"],
        "maximum_single_model_async_X": policy["reference_maximum_single_model_dynamic_X"],
        "minimum_non_degenerate_point_fraction": policy["minimum_non_degenerate_point_fraction"],
        "maximum_absolute_phi": policy["maximum_absolute_phi_between_distinct_points"],
    }
    if gates != expected:
        errors.append(f"{path}: decision_gates must exactly mirror evaluation_contract.json")
    run_policy = plan.get("run_policy") or {}
    if run_policy.get("backend") != "real_api_only":
        errors.append(f"{path}: backend must be real_api_only")
    if run_policy.get("participant_failure_is_not_retried") is not True:
        errors.append(f"{path}: participant failures must not be retried")
    return errors


def validate_release_security(root: Path) -> list[str]:
    """Check repository-level credential exclusion without opening credential files."""
    path = root / ".gitignore"
    try:
        entries = {
            line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
    except OSError as exc:
        return [f"cannot read {path}: {exc}"]
    required = {"apikey.txt", "*.key", "*.pem"}
    missing = sorted(required - entries)
    return [f"{path}: missing credential exclusion {value!r}" for value in missing]


# Dataset policy statuses that lock the registered split for a formal release.
_RELEASE_LOCKED_DATASET_STATUSES = {
    "post_calibration_locked",
    "frozen",
    "publication_locked",
}


def validate_frozen_release(root: Path) -> list[str]:
    """Certify a release from its frozen contract and locked dataset.

    Calibration execution remains an optional diagnostic workflow. The tracked
    plan is validated separately for repository consistency, but its audit and
    model-panel size are not release prerequisites.
    """
    errors: list[str] = []
    try:
        contract = json.loads((root / "evaluation_contract.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot read evaluation_contract.json: {exc}"]
    if contract.get("status") != "frozen":
        errors.append(
            f"evaluation_contract.json status must be 'frozen' "
            f"(got {contract.get('status')!r})"
        )
    version = str(contract.get("version") or "")
    if version.endswith("-dev") or not version:
        errors.append(
            f"evaluation_contract.json version must be a released non-dev version "
            f"(got {version!r})"
        )
    try:
        dataset = json.loads((root / "dataset_policy.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [*errors, f"cannot read dataset_policy.json: {exc}"]
    status = str(dataset.get("status") or "")
    if status not in _RELEASE_LOCKED_DATASET_STATUSES:
        errors.append(
            f"dataset_policy.json status must be a release-locked status "
            f"(got {status!r})"
        )
    return errors
