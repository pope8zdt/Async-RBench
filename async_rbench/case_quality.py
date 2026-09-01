"""Fail-closed quality contract for transformed benchmark cases.

The ordinary case schema proves that files and field names are structurally
valid.  This module proves the two additional properties needed for dataset
production: every scored claim is grounded in participant-visible evidence,
and the hidden verifier accepts at least one non-canonical equivalent solution.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


QUALITY_CONTRACT = Path("private/quality_contract.yaml")
PARTICIPANT_VISIBLE_CONTRACT_PATHS = {"public_case.yaml", "task/task.yaml"}


def _instruction(path: Path) -> str:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("instruction"), str):
        raise ValueError(f"task instruction is missing or malformed: {path}")
    return raw["instruction"].strip()


def _canonical_instruction(text: str) -> str:
    # YAML block indentation is presentation, not task semantics.  Preserve all
    # text and line ordering while ignoring indentation/trailing-space drift.
    return "\n".join(line.strip() for line in text.strip().splitlines())


def instruction_sha256(text: str) -> str:
    return hashlib.sha256(_canonical_instruction(text).encode("utf-8")).hexdigest()


def load_quality_contract(case_dir: Path) -> dict[str, Any]:
    path = case_dir / QUALITY_CONTRACT
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"quality contract must be a mapping: {path}")
    return raw


def _inside(base: Path, relative: str) -> Path | None:
    candidate = Path(relative)
    if candidate.is_absolute():
        return None
    resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError:
        return None
    return resolved


def validate_relocatable_source_contract(case_dir: Path) -> list[str]:
    """Require source snapshots to remain valid when a case directory moves.

    Candidate families are promoted by moving the whole directory from
    ``candidate_cases/`` to ``cases/``.  A repository-root-relative source
    path tied to the former location passes candidate validation but becomes
    dangling after that move.  Promotion therefore requires every declared
    source snapshot to be case-relative.
    """
    case_dir = case_dir.resolve()
    contract_path = case_dir / QUALITY_CONTRACT
    try:
        contract = load_quality_contract(case_dir)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        return [f"invalid quality contract {contract_path}: {exc}"]
    errors: list[str] = []
    sources = ((contract.get("source_contract") or {}).get("sources") or [])
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            continue
        relative = str(source.get("task_path") or "")
        resolved = _inside(case_dir, relative)
        if resolved is None or not resolved.is_file():
            errors.append(
                f"{contract_path}: source_contract.sources[{index}].task_path must be "
                f"case-relative and relocation-safe: {relative!r}"
            )
    return errors


def _semantic_ids(case_dir: Path) -> set[str]:
    raw = json.loads(
        (case_dir / "task/tests/semantic_checks.json").read_text(encoding="utf-8")
    )
    return {str(item.get("id") or "") for item in raw.get("checks") or []}


def _dynamic_control_ids(case_dir: Path) -> set[str]:
    raw = json.loads(
        (case_dir / "task/tests/control_flow_checks.json").read_text(encoding="utf-8")
    )
    return {str(item.get("id") or "") for item in raw.get("checks") or []}


def validate_case_quality(root: Path, case_dir: Path, *, require_contract: bool = True) -> list[str]:
    """Validate traceability, source fidelity and equivalence-test declarations."""
    case_dir = case_dir.resolve()
    contract_path = case_dir / QUALITY_CONTRACT
    if not contract_path.is_file():
        return [f"missing transformed-case quality contract: {contract_path}"] if require_contract else []
    errors: list[str] = []
    try:
        contract = load_quality_contract(case_dir)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        return [f"invalid quality contract {contract_path}: {exc}"]
    if str(contract.get("schema_version")) != "1":
        errors.append(f"{contract_path}: schema_version must be '1'")

    public_case_path = case_dir / "public_case.yaml"
    try:
        public_case = yaml.safe_load(public_case_path.read_text(encoding="utf-8"))
        private_case = yaml.safe_load(
            (case_dir / "private/private_case.yaml").read_text(encoding="utf-8")
        )
        candidate_instruction = _instruction(case_dir / str(
            (public_case or {}).get("task_instruction_path") or "task/task.yaml"
        ))
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        return errors + [f"{contract_path}: cannot load case contracts: {exc}"]

    source_contract = contract.get("source_contract")
    manifest_requirement_references: list[tuple[str, set[str]]] = []
    if not isinstance(source_contract, dict):
        errors.append(f"{contract_path}: source_contract must be an object")
    else:
        policy = source_contract.get("instruction_preservation")
        if policy not in {"verbatim_append", "requirements_manifest"}:
            errors.append(
                f"{contract_path}: source_contract.instruction_preservation must be "
                "verbatim_append or requirements_manifest"
            )
        if policy == "requirements_manifest":
            review = source_contract.get("manifest_review")
            if not isinstance(review, dict):
                errors.append(
                    f"{contract_path}: requirements_manifest requires manifest_review"
                )
            else:
                if review.get("decision") != "approved":
                    errors.append(f"{contract_path}: manifest_review.decision must be approved")
                for field in ("reviewer_id", "reviewed_at"):
                    if not str(review.get(field) or "").strip():
                        errors.append(f"{contract_path}: manifest_review.{field} is required")
        sources = source_contract.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append(f"{contract_path}: source_contract.sources must be non-empty")
        else:
            declared_ids: set[str] = set()
            for index, source in enumerate(sources):
                label = f"{contract_path}: source_contract.sources[{index}]"
                if not isinstance(source, dict):
                    errors.append(f"{label} must be an object")
                    continue
                source_id = str(source.get("task_id") or "")
                if not source_id or source_id in declared_ids:
                    errors.append(f"{label}.task_id must be non-empty and unique")
                declared_ids.add(source_id)
                relative = str(source.get("task_path") or "")
                # New cases use a relocation-safe case-relative source snapshot.
                # Root-relative lookup remains as a compatibility fallback for
                # older official cases whose immutable source lives elsewhere.
                source_path = _inside(case_dir, relative)
                if source_path is None or not source_path.is_file():
                    source_path = _inside(root, relative)
                if source_path is None or not source_path.is_file():
                    errors.append(f"{label}.task_path is missing or escapes the repository: {relative!r}")
                    continue
                try:
                    source_instruction = _instruction(source_path)
                except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
                    errors.append(f"{label}: {exc}")
                    continue
                expected_sha = instruction_sha256(source_instruction)
                if source.get("instruction_sha256") != expected_sha:
                    errors.append(f"{label}.instruction_sha256 does not match the source instruction")
                if policy == "verbatim_append" and _canonical_instruction(
                    source_instruction
                ) not in _canonical_instruction(candidate_instruction):
                    errors.append(
                        f"{label}: source instruction is not preserved verbatim in the participant task"
                    )
                if policy == "requirements_manifest":
                    mappings = source.get("requirement_mappings")
                    if not isinstance(mappings, list) or not mappings:
                        errors.append(f"{label}.requirement_mappings must be non-empty")
                    else:
                        normalized_source = re.sub(r"\s+", " ", source_instruction).strip()
                        for mapping_index, mapping in enumerate(mappings):
                            mapping_label = f"{label}.requirement_mappings[{mapping_index}]"
                            if not isinstance(mapping, dict):
                                errors.append(f"{mapping_label} must be an object")
                                continue
                            anchor = re.sub(
                                r"\s+", " ", str(mapping.get("source_anchor") or "")
                            ).strip()
                            refs = set(map(str, mapping.get("requirement_ids") or []))
                            if not anchor or anchor not in normalized_source:
                                errors.append(
                                    f"{mapping_label}.source_anchor is absent from the source instruction"
                                )
                            if not refs:
                                errors.append(f"{mapping_label}.requirement_ids must be non-empty")
                            manifest_requirement_references.append((mapping_label, refs))
            expected_ids = {
                str(item.get("id") or "") for item in (public_case or {}).get("source_tasks") or []
            }
            if declared_ids != expected_ids:
                errors.append(
                    f"{contract_path}: source_contract task ids must exactly match public source_tasks"
                )

    requirements = contract.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        errors.append(f"{contract_path}: requirements must be a non-empty list")
        requirements = []
    requirement_ids: set[str] = set()
    covered_semantic: set[str] = set()
    covered_dynamic: set[str] = set()
    covered_workstreams: set[str] = set()
    covered_hidden: set[str] = set()
    for index, requirement in enumerate(requirements):
        label = f"{contract_path}: requirements[{index}]"
        if not isinstance(requirement, dict):
            errors.append(f"{label} must be an object")
            continue
        requirement_id = str(requirement.get("id") or "")
        if not requirement_id or requirement_id in requirement_ids:
            errors.append(f"{label}.id must be non-empty and unique")
        requirement_ids.add(requirement_id)
        evidence = requirement.get("public_evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{label}.public_evidence must be non-empty")
        else:
            for evidence_index, item in enumerate(evidence):
                evidence_label = f"{label}.public_evidence[{evidence_index}]"
                if not isinstance(item, dict):
                    errors.append(f"{evidence_label} must be an object")
                    continue
                relative = str(item.get("path") or "")
                normalized = relative.replace("\\", "/")
                if normalized not in PARTICIPANT_VISIBLE_CONTRACT_PATHS:
                    errors.append(
                        f"{evidence_label}.path is not an allowed participant-visible "
                        f"contract: {relative!r}"
                    )
                    continue
                path = _inside(case_dir, relative)
                anchor = str(item.get("contains") or "")
                if path is None or not path.is_file():
                    errors.append(f"{evidence_label}.path is missing or escapes the case: {relative!r}")
                elif not anchor:
                    errors.append(f"{evidence_label}.contains must be non-empty")
                elif re.sub(r"\s+", " ", anchor).strip() not in re.sub(
                    r"\s+", " ", path.read_text(encoding="utf-8")
                ).strip():
                    errors.append(f"{evidence_label} anchor is absent from {relative!r}: {anchor!r}")
        covers = requirement.get("covers")
        if not isinstance(covers, dict):
            errors.append(f"{label}.covers must be an object")
            continue
        covered_semantic.update(map(str, covers.get("semantic_checks") or []))
        covered_dynamic.update(map(str, covers.get("dynamic_control_checks") or []))
        covered_workstreams.update(map(str, covers.get("workstream_validators") or []))
        covered_hidden.update(map(str, covers.get("hidden_checks") or []))

    for mapping_label, references in manifest_requirement_references:
        unknown = sorted(references - requirement_ids)
        if unknown:
            errors.append(f"{mapping_label}.requirement_ids references unknown requirements: {unknown}")

    semantic_ids = _semantic_ids(case_dir)
    dynamic_ids = _dynamic_control_ids(case_dir)
    workstream_ids = {
        str(item.get("id") or "") for item in (public_case or {}).get("workstreams") or []
    }
    hidden_ids = set(map(str, (private_case or {}).get("hidden_checks") or {}))
    for label, covered, expected in (
        ("semantic checks", covered_semantic, semantic_ids),
        ("dynamic control checks", covered_dynamic, dynamic_ids),
        ("workstream validators", covered_workstreams, workstream_ids),
        ("hidden checks", covered_hidden, hidden_ids),
    ):
        missing = sorted(expected - covered)
        unknown = sorted(covered - expected)
        if missing:
            errors.append(f"{contract_path}: requirements do not ground all {label}: {missing}")
        if unknown:
            errors.append(f"{contract_path}: requirements reference unknown {label}: {unknown}")

    sufficiency = (private_case or {}).get("information_sufficiency") or []
    for index, item in enumerate(sufficiency):
        ids = item.get("requirement_ids") if isinstance(item, dict) else None
        label = f"{contract_path}: information_sufficiency[{index}].requirement_ids"
        if not isinstance(ids, list) or not ids:
            errors.append(f"{label} must be a non-empty list")
        elif set(map(str, ids)) - requirement_ids:
            errors.append(f"{label} references unknown quality requirements")

    alternatives = contract.get("equivalence_solutions")
    if not isinstance(alternatives, list) or not alternatives:
        errors.append(f"{contract_path}: at least one equivalence solution is required")
    else:
        seen: set[str] = set()
        for index, alternative in enumerate(alternatives):
            label = f"{contract_path}: equivalence_solutions[{index}]"
            if not isinstance(alternative, dict):
                errors.append(f"{label} must be an object")
                continue
            alternative_id = str(alternative.get("id") or "")
            if not alternative_id or alternative_id in seen:
                errors.append(f"{label}.id must be non-empty and unique")
            seen.add(alternative_id)
            relative = str(alternative.get("path") or "")
            normalized = relative.replace("\\", "/")
            path = _inside(case_dir, relative)
            if not normalized.startswith("task/equivalence_solutions/"):
                errors.append(f"{label}.path must be under task/equivalence_solutions/")
            if path is None or not path.is_file() or path.suffix != ".sh":
                errors.append(f"{label}.path must name an existing shell solution")
            if not str(alternative.get("distinguishes_from_oracle") or "").strip():
                errors.append(f"{label}.distinguishes_from_oracle is required")

    negatives = contract.get("negative_mutations")
    if not isinstance(negatives, list) or len(negatives) < 2:
        errors.append(f"{contract_path}: at least two executed negative mutations are required")
    else:
        seen_negative: set[str] = set()
        for index, mutation in enumerate(negatives):
            label = f"{contract_path}: negative_mutations[{index}]"
            if not isinstance(mutation, dict):
                errors.append(f"{label} must be an object")
                continue
            mutation_id = str(mutation.get("id") or "")
            if not mutation_id or mutation_id in seen_negative:
                errors.append(f"{label}.id must be non-empty and unique")
            seen_negative.add(mutation_id)
            relative = str(mutation.get("path") or "")
            normalized = relative.replace("\\", "/")
            path = _inside(case_dir, relative)
            if not normalized.startswith("task/negative_mutations/"):
                errors.append(f"{label}.path must be under task/negative_mutations/")
            if path is None or not path.is_file() or path.suffix != ".sh":
                errors.append(f"{label}.path must name an existing shell mutation")
            must_fail = set(map(str, mutation.get("must_fail") or []))
            if not must_fail:
                errors.append(f"{label}.must_fail must be non-empty")
            elif must_fail - semantic_ids:
                errors.append(f"{label}.must_fail references unknown semantic checks")
    return errors


def equivalence_solutions(case_dir: Path) -> list[dict[str, str]]:
    contract = load_quality_contract(case_dir)
    return [
        {
            "id": str(item["id"]),
            "path": str((case_dir / str(item["path"])).resolve()),
        }
        for item in contract.get("equivalence_solutions") or []
    ]


def negative_mutations(case_dir: Path) -> list[dict[str, Any]]:
    contract = load_quality_contract(case_dir)
    return [
        {
            "id": str(item["id"]),
            "path": str((case_dir / str(item["path"])).resolve()),
            "must_fail": list(map(str, item.get("must_fail") or [])),
        }
        for item in contract.get("negative_mutations") or []
    ]
