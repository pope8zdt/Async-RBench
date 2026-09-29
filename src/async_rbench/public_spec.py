from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .evaluation.case_contract import find_private_fields


@dataclass(frozen=True)
class PublicCaseSpec:
    path: Path
    raw: dict[str, Any]

    @property
    def case_id(self) -> str:
        return str(self.raw["case_id"])

    @property
    def case_dir(self) -> Path:
        return self.path.parent.parent


def is_public_contract(path: Path) -> bool:
    return path.name == "case.yaml" and path.parent.name == "public"


def _resolve_task_path(case_dir: Path, reference: object) -> Path:
    relative = str(reference or "task/task.yaml")
    candidate = (case_dir / relative).resolve()
    try:
        candidate.relative_to(case_dir.resolve())
    except ValueError as exc:
        raise ValueError(
            f"task_instruction_path escapes case directory: {relative!r}"
        ) from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"missing public task instruction: {candidate}")
    return candidate


def load_public_case(path: Path) -> PublicCaseSpec:
    path = path.resolve()
    if not is_public_contract(path):
        raise ValueError(f"expected public/case.yaml contract, got: {path}")
    public = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(public, dict):
        raise ValueError(f"public case contract must be a mapping: {path}")
    task_path = _resolve_task_path(path.parent.parent, public.get("task_instruction_path"))
    task = yaml.safe_load(task_path.read_text(encoding="utf-8"))
    if not isinstance(task, dict):
        raise ValueError(f"public task instruction must be a mapping: {task_path}")

    workstreams = [dict(item) for item in public.get("workstreams") or []]
    raw = dict(public)
    raw.update({
        "delegation_workstreams": workstreams,
        "initial_wave": [{
            "workstream_id": str(item.get("id") or ""),
            "task": str(item.get("task") or ""),
            "targets": list(item.get("targets") or []),
            "expected_output": str(item.get("expected_output") or ""),
            "priority": str(item.get("priority") or "normal"),
            "required_evidence_fields": list(item.get("required_evidence_fields") or []),
        } for item in workstreams],
        "reverification_checks": list(public.get("public_checks") or []),
        "instruction": str(task.get("instruction") or ""),
        "difficulty": str(task.get("difficulty") or "").strip().lower(),
    })
    return PublicCaseSpec(path=path, raw=raw)


def validate_public_case(spec: PublicCaseSpec) -> list[str]:
    raw = spec.raw
    errors: list[str] = []
    for hit in find_private_fields(raw):
        field = hit.rsplit(".", 1)[-1]
        errors.append(f"{spec.path}: private field {field!r} is not allowed in public contract")
    for key in ("case_id", "source_tasks", "milestones", "artifacts", "workstreams"):
        if key not in raw:
            errors.append(f"{spec.path}: missing required public key {key!r}")
    if not str(raw.get("case_id") or "").strip():
        errors.append(f"{spec.path}: case_id must be non-empty")
    if not list(raw.get("source_tasks") or []):
        errors.append(f"{spec.path}: source_tasks must be non-empty")
    if not raw.get("instruction"):
        errors.append(f"{spec.path}: task instruction must be non-empty")
    if raw.get("difficulty") not in {"medium", "hard"}:
        errors.append(f"{spec.path}: difficulty must be medium or hard")
    for label, items in (
        ("milestone", raw.get("milestones") or []),
        ("artifact", raw.get("artifacts") or []),
        ("workstream", raw.get("workstreams") or []),
    ):
        identifiers = [str(item.get("id") or "") for item in items]
        if any(not item for item in identifiers):
            errors.append(f"{spec.path}: {label} ids must be non-empty")
        if len(identifiers) != len(set(identifiers)):
            errors.append(f"{spec.path}: {label} ids must be unique")
    return errors
