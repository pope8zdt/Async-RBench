"""Retrospective publication-readiness audit for registered legacy cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import yaml

from .case_quality import QUALITY_CONTRACT, load_quality_contract, validate_case_quality
from .spec import validate_case


def _instruction(path: Path) -> str:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return str((raw or {}).get("instruction") or "").strip()


def _canonical(value: str) -> str:
    return "\n".join(line.strip() for line in value.strip().splitlines())


def _count_semantic(case_dir: Path) -> int:
    value = json.loads((case_dir / "task/tests/semantic_checks.json").read_text(encoding="utf-8"))
    return len(value.get("checks") or [])


def build_retrospective_quality_audit(root: Path, instances: Iterable[Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for reference in instances:
        case = reference.load() if hasattr(reference, "load") else reference
        instance_id = str(getattr(reference, "instance_id", "seed-1"))
        public = yaml.safe_load(case.path.read_text(encoding="utf-8")) or {}
        task_path = case.case_dir / str(public.get("task_instruction_path") or "task/task.yaml")
        participant_instruction = _instruction(task_path)
        sources: list[dict[str, Any]] = []
        for source in case.raw.get("source_tasks") or []:
            upstream = str(source.get("upstream_path") or "")
            upstream_path = root / upstream if upstream else None
            source_path = (
                upstream_path
                if upstream_path and upstream_path.is_file()
                else upstream_path / "task.yaml"
                if upstream_path
                else None
            )
            available = bool(source_path and source_path.is_file())
            source_instruction = _instruction(source_path) if available and source_path else ""
            sources.append({
                "benchmark": str(source.get("benchmark") or ""),
                "task_id": str(source.get("id") or ""),
                "task_instruction_available": available,
                "task_path": str(source_path) if source_path else None,
                "verbatim_preserved": bool(
                    available and _canonical(source_instruction) in _canonical(participant_instruction)
                ),
            })
        quality_path = case.case_dir / QUALITY_CONTRACT
        quality_errors = validate_case_quality(root, case.case_dir, require_contract=True)
        contract = load_quality_contract(case.case_dir) if quality_path.is_file() else {}
        equivalence_count = len(contract.get("equivalence_solutions") or [])
        negative_count = len(contract.get("negative_mutations") or [])
        sufficiency = case.raw.get("information_sufficiency") or []
        mapped_sufficiency = sum(
            1 for item in sufficiency
            if isinstance(item, dict) and list(item.get("requirement_ids") or [])
        )
        pseudo_artifacts = [
            item for item in case.raw.get("artifacts") or []
            if not str(item.get("path") or "").startswith("/")
            or ":" in str(item.get("path") or "")[1:]
        ]
        observed_pseudo = sum(
            1 for item in pseudo_artifacts if str(item.get("observer_command") or "").strip()
        )
        technical_errors = validate_case(case)
        required_actions: list[str] = []
        if any(not source["task_instruction_available"] for source in sources):
            required_actions.append("pin_missing_source_instruction_or_approve_requirement_manifest")
        if any(
            source["task_instruction_available"] and not source["verbatim_preserved"]
            for source in sources
        ):
            required_actions.append("review_source_requirement_preservation")
        if not quality_path.is_file():
            required_actions.append("author_quality_contract")
        if equivalence_count < 1:
            required_actions.append("add_and_execute_noncanonical_equivalent_solution")
        if negative_count < 2:
            required_actions.append("add_and_execute_at_least_two_negative_mutations")
        if mapped_sufficiency != len(sufficiency):
            required_actions.append("map_information_sufficiency_to_public_requirements")
        if observed_pseudo != len(pseudo_artifacts):
            required_actions.append("add_missing_runtime_artifact_observers")
        if technical_errors:
            required_actions.append("repair_technical_case_contract")
        ready = not quality_errors and not technical_errors
        rows.append({
            "case_id": case.case_id,
            "instance_id": instance_id,
            "source_tasks": sources,
            "source_task_count": len(sources),
            "semantic_check_count": _count_semantic(case.case_dir),
            "workstream_count": len(case.raw.get("delegation_workstreams") or []),
            "hidden_check_count": len(case.raw.get("hidden_reverification_commands") or {}),
            "information_sufficiency": {
                "total": len(sufficiency), "mapped_to_requirements": mapped_sufficiency,
            },
            "runtime_artifacts": {
                "total": len(pseudo_artifacts), "with_observer": observed_pseudo,
            },
            "quality_contract_present": quality_path.is_file(),
            "quality_contract_errors": quality_errors,
            "equivalence_solution_count": equivalence_count,
            "negative_mutation_count": negative_count,
            "technical_errors": technical_errors,
            "required_actions": list(dict.fromkeys(required_actions)),
            "disposition": "eligible_for_execution_reaudit" if ready else "hold_for_retrofit",
        })
    eligible = sum(row["disposition"] == "eligible_for_execution_reaudit" for row in rows)
    return {
        "schema_version": "1.0",
        "registered_instance_count": len(rows),
        "eligible_for_execution_reaudit": eligible,
        "held_for_retrofit": len(rows) - eligible,
        "publication_ready": bool(rows) and eligible == len(rows),
        "rows": sorted(rows, key=lambda row: (row["case_id"], row["instance_id"])),
    }
