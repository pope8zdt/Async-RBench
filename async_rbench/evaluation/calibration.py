from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from .weighting import ASYNC_EXECUTION_MODES, control_flow_weight, semantic_weight_map
from .mutation_audit import validate_executed_mutation_evidence


def _case_split_map(root: Path) -> dict[str, set[str]]:
    """Map case_id to the set of instance splits registered for that family."""
    registry_path = root / "cases" / "registry.json"
    if not registry_path.is_file():
        return {}
    registry = _load_json(registry_path)
    splits: dict[str, set[str]] = {}
    for family in registry.get("case_families") or []:
        case_id = str(family.get("case_id") or "")
        if not case_id:
            continue
        instance_splits = {
            str(instance.get("split") or "unassigned")
            for instance in family.get("instances") or []
        }
        # A family with no explicit instance split is unassigned and may not be
        # used for calibration: assigning development/test evidence to the
        # calibration audit would be an isolation failure.
        splits[case_id] = instance_splits or {"unassigned"}
    return splits


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _phi(left: list[bool], right: list[bool]) -> float | None:
    n11 = sum(a and b for a, b in zip(left, right))
    n10 = sum(a and not b for a, b in zip(left, right))
    n01 = sum(not a and b for a, b in zip(left, right))
    n00 = len(left) - n11 - n10 - n01
    denominator = math.sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    return (n11 * n00 - n10 * n01) / denominator if denominator else None


def _frozen_point_ids(root: Path) -> tuple[
    dict[str, set[str]],
    dict[str, dict[str, set[str]]],
    dict[str, set[str]],
    dict[str, dict[str, dict[str, int]]],
]:
    semantic: dict[str, set[str]] = {}
    by_mode: dict[str, dict[str, set[str]]] = {}
    critical: dict[str, set[str]] = {}
    weights: dict[str, dict[str, dict[str, int]]] = {}
    for path in sorted((root / "cases").glob("*/task/tests/semantic_checks.json")):
        case_id = path.parents[2].name
        semantic_checks = _load_json(path)["checks"]
        control_checks = _load_json(path.with_name("control_flow_checks.json"))["checks"]
        semantic[case_id] = {str(item["id"]) for item in semantic_checks}
        critical[case_id] = {
            str(item["id"]) for item in [*semantic_checks, *control_checks]
            if item.get("critical") is True
        }
        by_mode[case_id] = {
            mode: semantic[case_id] | {
                str(item["id"]) for item in control_checks
                if mode in (item.get("execution_modes") or [])
            }
            for mode in ASYNC_EXECUTION_MODES
        }
        weights[case_id] = {}
        semantic_weights = semantic_weight_map(semantic_checks)
        control_weights = {
            str(item["id"]): control_flow_weight(item) for item in control_checks
        }
        for mode, point_ids in by_mode[case_id].items():
            weights[case_id][mode] = {
                point_id: (semantic_weights.get(point_id) or control_weights.get(point_id, 1))
                for point_id in point_ids
            }
    return semantic, by_mode, critical, weights


def audit_score_calibration(root: Path, evidence_root: Path) -> dict[str, Any]:
    contract = _load_json(root / "evaluation_contract.json")
    policy = contract["calibration_diagnostics"]
    semantic_ids, registry_ids_by_mode, critical_ids, weighted_ids_by_mode = _frozen_point_ids(root)
    registry_ids = {
        case_id: set().union(*mode_sets.values())
        for case_id, mode_sets in registry_ids_by_mode.items()
    }
    dynamic_ids = {
        case_id: point_ids - semantic_ids.get(case_id, set())
        for case_id, point_ids in registry_ids.items()
    }

    gaps: list[str] = []
    mutation_path = evidence_root / "mutation_kill_matrix.json"
    response_path = evidence_root / "point_response_matrix.json"
    if not mutation_path.is_file():
        gaps.append(f"missing executed mutation evidence: {mutation_path}")
    if not response_path.is_file():
        gaps.append(f"missing cross-model point-response evidence: {response_path}")
    if gaps:
        return {"policy": policy, "gaps": gaps, "cases": {}}

    mutation_rows = list((_load_json(mutation_path) or {}).get("rows") or [])
    response_rows = list((_load_json(response_path) or {}).get("rows") or [])
    case_reports: dict[str, dict[str, Any]] = {}

    # P0-3: calibration is only valid on the calibration split.  Evidence that
    # admits a development/test instance into the calibration audit is a leak and
    # must fail the audit rather than silently pollute the calibrated weights.
    # This gate runs before the (stricter) mutation-evidence validation so a
    # cross-split leak is never masked by a separate malformed-matrix error.
    split_map = _case_split_map(root)
    evidence_case_ids = {
        str(row.get("case_id")) for row in [*mutation_rows, *response_rows]
        if isinstance(row, dict) and row.get("case_id")
    }
    for case_id in sorted(evidence_case_ids - set(split_map)):
        gaps.append(f"{case_id}: calibration evidence for a case not in cases/registry.json")
    for case_id in sorted(evidence_case_ids):
        splits = split_map.get(case_id, {"unassigned"})
        if splits - {"calibration"}:
            gaps.append(
                f"{case_id}: calibration evidence includes non-calibration instances {sorted(splits)}"
            )
    calibration_case_ids = {
        case_id for case_id, splits in split_map.items() if splits == {"calibration"}
    }
    for case_id in sorted(calibration_case_ids):
        if case_id not in registry_ids:
            # A registered calibration family with no frozen point registry is a
            # build omission, not a silent skip.
            gaps.append(f"{case_id}: calibration family has no frozen point registry")
    if gaps:
        return {"policy": policy, "gaps": sorted(set(gaps)), "cases": case_reports}

    mutation_evidence_errors = validate_executed_mutation_evidence(root, evidence_root)
    if mutation_evidence_errors:
        return {"policy": policy, "gaps": mutation_evidence_errors, "cases": {}}

    for case_id, point_ids in registry_ids.items():
        if case_id not in calibration_case_ids:
            continue
        case_gaps: list[str] = []
        mutants = [row for row in mutation_rows if row.get("case_id") == case_id and row.get("executed") is True]
        killed = [row for row in mutants if set(row.get("killed_point_ids") or []) & point_ids]
        critical_dynamic_ids = critical_ids[case_id] & dynamic_ids[case_id]
        critical_mutants = [
            row for row in mutants
            if set(row.get("target_point_ids") or []) & critical_dynamic_ids
        ]
        critical_killed = [
            row for row in critical_mutants
            if set(row.get("killed_point_ids") or []) & point_ids
        ]
        mutation_rate = len(killed) / len(mutants) if mutants else None
        critical_mutation_rate = (
            len(critical_killed) / len(critical_mutants) if critical_mutants else None
        )
        if len(mutants) < int(policy["minimum_executed_mutants_per_case"]):
            case_gaps.append("insufficient executed mutants")
        if mutation_rate is None or mutation_rate < float(policy["minimum_mutation_kill_rate"]):
            case_gaps.append("mutation kill rate below diagnostic reference")
        if (
            critical_mutation_rate is None
            or critical_mutation_rate < float(policy["minimum_critical_mutation_kill_rate"])
        ):
            case_gaps.append("critical mutation kill rate below diagnostic reference")

        observations = [
            row for row in response_rows
            if row.get("case_id") == case_id
            and row.get("execution_mode") in ASYNC_EXECUTION_MODES
        ]
        model_ids = {str(row.get("model_id")) for row in observations if row.get("model_id")}
        model_families = {
            str(row.get("model_family")) for row in observations if row.get("model_family")
        }
        if len(model_ids) < int(policy["minimum_pilot_models"]):
            case_gaps.append("insufficient pilot models")
        if len(model_families) < int(policy["minimum_model_families"]):
            case_gaps.append("insufficient model families")

        repetition_counts: dict[tuple[str, str], set[int]] = defaultdict(set)
        for row in observations:
            repetition_counts[(str(row.get("model_id")), str(row.get("execution_mode")))].add(
                int(row.get("repeat", 0))
            )
            expected = registry_ids_by_mode[case_id].get(str(row.get("execution_mode")), set())
            if set((row.get("points") or {})) != expected:
                case_gaps.append("point-response row does not exactly cover frozen registry")
        expected_model_modes = {
            (model_id, mode) for model_id in model_ids for mode in ASYNC_EXECUTION_MODES
        }
        if any(
            len(repetition_counts[key]) < int(policy["minimum_repetitions_per_model_mode"])
            for key in expected_model_modes
        ):
            case_gaps.append("insufficient repetitions for one or more model/mode pairs")

        scores_by_model: dict[str, list[float]] = defaultdict(list)
        point_vectors: dict[str, dict[int, bool]] = {
            point_id: {} for point_id in dynamic_ids[case_id]
        }
        for observation_index, row in enumerate(observations):
            points = row.get("points") or {}
            execution_mode = str(row.get("execution_mode"))
            expected = registry_ids_by_mode[case_id].get(execution_mode, set())
            if set(points) != expected:
                continue
            weights_for_mode = weighted_ids_by_mode[case_id].get(execution_mode, {})
            dynamic_points = {
                point_id: value for point_id, value in points.items()
                if point_id in dynamic_ids[case_id]
            }
            weighted_total = sum(
                weights_for_mode.get(point_id, 1) for point_id in dynamic_points
            )
            weighted_passed = sum(
                weights_for_mode.get(point_id, 1)
                for point_id, value in dynamic_points.items() if value is True
            )
            scores_by_model[str(row["model_id"])].append(
                weighted_passed / weighted_total if weighted_total else 0.0
            )
            for point_id, value in dynamic_points.items():
                point_vectors[point_id][observation_index] = value is True
        model_scores = {
            model_id: sum(values) / len(values)
            for model_id, values in scores_by_model.items() if values
        }
        mean_dynamic_x = (
            sum(model_scores.values()) / len(model_scores) if model_scores else None
        )
        maximum_model_x = max(model_scores.values()) if model_scores else None
        if mean_dynamic_x is None or mean_dynamic_x > float(policy["reference_maximum_mean_dynamic_X"]):
            case_gaps.append("mean dynamic X is missing or saturated")
        if maximum_model_x is None or maximum_model_x > float(policy["reference_maximum_single_model_dynamic_X"]):
            case_gaps.append("a pilot model saturates dynamic X")

        low, high = map(float, policy["non_degenerate_point_pass_rate_interval"])
        point_pass_rates = {
            point_id: sum(values.values()) / len(values) if values else None
            for point_id, values in point_vectors.items()
        }
        non_degenerate = sum(
            value is not None and low <= value <= high for value in point_pass_rates.values()
        )
        non_degenerate_fraction = (
            non_degenerate / len(dynamic_ids[case_id]) if dynamic_ids[case_id] else 0.0
        )
        if non_degenerate_fraction < float(policy["minimum_non_degenerate_point_fraction"]):
            case_gaps.append("too many degenerate test points")

        max_abs_phi = 0.0
        ordered_points = sorted(dynamic_ids[case_id])
        for index, left_id in enumerate(ordered_points):
            for right_id in ordered_points[index + 1:]:
                common = sorted(set(point_vectors[left_id]) & set(point_vectors[right_id]))
                phi = _phi(
                    [point_vectors[left_id][key] for key in common],
                    [point_vectors[right_id][key] for key in common],
                ) if common else None
                if phi is not None:
                    max_abs_phi = max(max_abs_phi, abs(phi))
        if max_abs_phi > float(policy["maximum_absolute_phi_between_distinct_points"]):
            case_gaps.append("test-point dependence exceeds phi threshold")

        case_reports[case_id] = {
            "gaps": sorted(set(case_gaps)),
            "executed_mutants": len(mutants),
            "mutation_kill_rate": mutation_rate,
            "critical_mutation_kill_rate": critical_mutation_rate,
            "pilot_models": len(model_ids),
            "model_families": len(model_families),
            "mean_dynamic_control_score": mean_dynamic_x,
            "maximum_model_dynamic_control_score": maximum_model_x,
            "dynamic_point_count": len(dynamic_ids[case_id]),
            "non_degenerate_point_fraction": non_degenerate_fraction,
            "maximum_absolute_phi": max_abs_phi,
        }
        gaps.extend(f"{case_id}: {gap}" for gap in sorted(set(case_gaps)))

    return {"policy": policy, "gaps": gaps, "cases": case_reports}
