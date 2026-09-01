from __future__ import annotations

import json
import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..spec import discover_case_instances


def _load_registry_points(registry_dir: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    points: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for name in ("semantic_checks.json", "control_flow_checks.json"):
        path = registry_dir / name
        try:
            registry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"cannot audit mutations against {path}: {exc}")
            continue
        if not isinstance(registry, dict) or not isinstance(registry.get("checks"), list):
            errors.append(f"cannot audit mutations against malformed registry {path}")
            continue
        points.update({
            str(item["id"]): item
            for item in registry["checks"]
            if isinstance(item, dict) and "id" in item
        })
    return points, errors


def _validate_families(
    families: list[Any],
    registries: dict[str, dict[str, dict[str, Any]]],
    policy: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    try:
        minimum_concrete = int(policy.get("minimum_concrete_mutants_per_case", 40))
        minimum_coverage = int(policy.get("minimum_family_coverage_per_point", 1))
        minimum_critical = int(policy.get("minimum_family_coverage_per_critical_point", 2))
    except (TypeError, ValueError) as exc:
        return [f"mutation manifest policy counts must be integers: {exc}"]
    if min(minimum_concrete, minimum_coverage, minimum_critical) < 1:
        errors.append("mutation manifest policy counts must be positive")

    family_ids: set[str] = set()
    coverage: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    concrete_counts: dict[str, int] = defaultdict(int)
    for index, family in enumerate(families):
        if not isinstance(family, dict):
            errors.append(f"mutation families[{index}] must be an object")
            continue
        family_id = str(family.get("id", ""))
        case_id = str(family.get("case_id", ""))
        variants = list(family.get("variants") or [])
        must_fail = [str(value) for value in family.get("must_fail") or []]
        if not family_id or family_id in family_ids:
            errors.append(f"mutation family ids must be non-empty and unique: {family_id!r}")
        family_ids.add(family_id)
        if case_id not in registries:
            errors.append(f"{family_id}: unknown case_id {case_id!r}")
            continue
        if not family.get("operation") or not family.get("description"):
            errors.append(f"{family_id}: operation and description are required")
        if (
            len(variants) < 2
            or len(variants) != len(set(map(str, variants)))
            or any(not isinstance(value, str) or not value.strip() for value in variants)
        ):
            errors.append(
                f"{family_id}: variants must contain at least two unique non-empty strings"
            )
        concrete_counts[case_id] += len(variants)
        if not must_fail:
            errors.append(f"{family_id}: must_fail cannot be empty")
        for point_id in must_fail:
            if point_id not in registries[case_id]:
                errors.append(f"{family_id}: unknown test point {point_id!r}")
            else:
                coverage[case_id][point_id].add(family_id)

    for case_id, points in registries.items():
        if concrete_counts[case_id] < minimum_concrete:
            errors.append(
                f"{case_id}: {concrete_counts[case_id]} concrete mutants < {minimum_concrete}"
            )
        for point_id, point in points.items():
            required = minimum_critical if point.get("critical") is True else minimum_coverage
            observed = len(coverage[case_id][point_id])
            if observed < required:
                errors.append(
                    f"{case_id}: {point_id} covered by {observed} mutation families < {required}"
                )
    return errors


def validate_mutation_manifest(root: Path) -> list[str]:
    """Validate frozen mutation families against semantic registries.

    The manifest is executable-maintenance metadata: every family declares
    concrete variants and the semantic points that those variants must kill.
    This validator enforces coverage before expensive Docker mutation runs.
    """
    path = root / "tests" / "verifier_mutations" / "mutation_manifest.json"
    if not path.is_file():
        return [f"missing mutation manifest: {path}"]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return [f"invalid mutation manifest {path}: {exc}"]
    if not isinstance(manifest, dict):
        return [f"mutation manifest must be an object: {path}"]

    errors: list[str] = []
    policy = manifest.get("policy") or {}
    if not isinstance(policy, dict):
        return [f"mutation manifest policy must be an object: {path}"]
    try:
        int(policy.get("minimum_concrete_mutants_per_case", 40))
        int(policy.get("minimum_family_coverage_per_point", 1))
        int(policy.get("minimum_family_coverage_per_critical_point", 2))
    except (TypeError, ValueError) as exc:
        return [f"mutation manifest policy counts must be integers: {exc}"]
    raw_families = manifest.get("families")
    if not isinstance(raw_families, list):
        return errors + [f"mutation manifest families must be a list: {path}"]
    families = list(raw_families)

    # New cases keep their mutation metadata next to the case. This lets the
    # promotion gate validate the suite before moving the candidate, while the
    # central frozen manifest remains backwards compatible with existing cases.
    for suite_path in sorted((root / "cases").rglob("mutation_families.json")):
        try:
            suite = json.loads(suite_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"invalid case mutation suite {suite_path}: {exc}")
            continue
        if not isinstance(suite, dict) or not isinstance(suite.get("families"), list):
            errors.append(f"case mutation suite must contain a families list: {suite_path}")
            continue
        families.extend(suite["families"])

    registries: dict[str, dict[str, dict[str, Any]]] = {}
    for instance in discover_case_instances(root):
        registry_path = instance.case_dir / "task/tests/semantic_checks.json"
        case_id = instance.case_id
        points, point_errors = _load_registry_points(registry_path.parent)
        errors.extend(point_errors)
        registries.setdefault(case_id, {}).update(points)
    return errors + _validate_families(families, registries, policy)


def validate_candidate_mutation_suite(root: Path, candidate: Path, case_id: str) -> list[str]:
    """Validate candidate-local mutation metadata before promotion."""
    manifest_path = root / "tests" / "verifier_mutations" / "mutation_manifest.json"
    suite_path = candidate / "mutation_families.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return [f"invalid mutation manifest {manifest_path}: {exc}"]
    try:
        suite = json.loads(suite_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return [f"candidate mutation suite is required and must be valid: {suite_path}: {exc}"]
    if not isinstance(manifest, dict) or not isinstance(manifest.get("policy"), dict):
        return [f"mutation manifest policy must be an object: {manifest_path}"]
    if not isinstance(suite, dict) or not isinstance(suite.get("families"), list):
        return [f"candidate mutation suite must contain a families list: {suite_path}"]
    points, errors = _load_registry_points(candidate / "task" / "tests")
    if errors:
        return errors
    return _validate_families(suite["families"], {case_id: points}, manifest["policy"])


def validate_executed_mutation_evidence(root: Path, evidence_root: Path) -> list[str]:
    """Reject mutation matrices that are not backed by raw baseline/mutant reports."""
    matrix_path = evidence_root / "mutation_kill_matrix.json"
    if not matrix_path.is_file():
        return [f"missing executed mutation evidence: {matrix_path}"]
    try:
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return [f"invalid executed mutation evidence {matrix_path}: {exc}"]
    if not isinstance(matrix, dict) or matrix.get("schema_version") != "2.0":
        return [f"{matrix_path}: schema_version must be '2.0'"]
    rows = matrix.get("rows")
    if not isinstance(rows, list):
        return [f"{matrix_path}: rows must be a list"]

    manifest_paths = [root / "tests/verifier_mutations/mutation_manifest.json"]
    manifest_paths.extend(sorted((root / "cases").rglob("mutation_families.json")))
    declared: dict[tuple[str, str], dict[str, Any]] = {}
    for path in manifest_paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            return [f"cannot validate executed mutations against {path}: {exc}"]
        for family in value.get("families") or []:
            for variant in family.get("variants") or []:
                declared[(str(family.get("id")), str(variant))] = family

    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, 1):
        label = f"{matrix_path}: row {index}"
        if not isinstance(row, dict):
            errors.append(f"{label} must be an object")
            continue
        mutation_id = str(row.get("mutation_id") or "")
        if not mutation_id or mutation_id in seen:
            errors.append(f"{label} mutation_id must be non-empty and unique")
        seen.add(mutation_id)
        family_id = str(row.get("family_id") or "")
        variant = str(row.get("variant") or "")
        family = declared.get((family_id, variant))
        if family is None:
            errors.append(f"{label} does not name a declared family/variant")
            continue
        if row.get("case_id") != family.get("case_id"):
            errors.append(f"{label} case_id does not match the declared mutation family")
        if row.get("executed") is not True:
            errors.append(f"{label} must set executed=true only after both verifier runs")
        targets = row.get("target_point_ids")
        if not isinstance(targets, list) or set(map(str, targets)) != set(map(str, family.get("must_fail") or [])):
            errors.append(f"{label} target_point_ids must exactly match family.must_fail")
        killed = row.get("killed_point_ids")
        if not isinstance(killed, list) or not set(map(str, killed)).issubset(set(map(str, targets or []))):
            errors.append(f"{label} killed_point_ids must be a subset of target_point_ids")
        if not isinstance(row.get("artifact_mutation_sha256"), str) or len(row["artifact_mutation_sha256"]) != 64:
            errors.append(f"{label} requires artifact_mutation_sha256")
        for report_name, expected_success in (("baseline_verifier", True), ("mutated_verifier", False)):
            report_ref = row.get(report_name)
            if not isinstance(report_ref, dict):
                errors.append(f"{label} missing {report_name} provenance")
                continue
            relative = report_ref.get("report_path")
            if not isinstance(relative, str) or Path(relative).is_absolute():
                errors.append(f"{label} {report_name}.report_path must be evidence-relative")
                continue
            report_path = (evidence_root / relative).resolve()
            try:
                report_path.relative_to(evidence_root.resolve())
            except ValueError:
                errors.append(f"{label} {report_name}.report_path escapes evidence root")
                continue
            if not report_path.is_file():
                errors.append(f"{label} missing raw report {report_path}")
                continue
            digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
            if report_ref.get("report_sha256") != digest:
                errors.append(f"{label} {report_name} report digest mismatch")
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError) as exc:
                errors.append(f"{label} invalid {report_name} report: {exc}")
                continue
            if report.get("success") is not expected_success:
                errors.append(f"{label} {report_name} has unexpected success status")
            if not report.get("verifier_bundle_sha256"):
                errors.append(f"{label} {report_name} lacks verifier bundle digest")
    return errors
