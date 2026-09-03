from __future__ import annotations

import json
from pathlib import Path

from async_rbench.evaluation.case_contract import validate_scoring_domains
from async_rbench.spec import discover_case_instances, discover_cases


ROOT = Path(__file__).resolve().parents[1]


def test_every_runnable_instance_declares_valid_scoring_domains() -> None:
    """Every registry reachable by an evaluation run passes the scoring gate."""
    case_ids = [case.case_id for case in discover_cases(ROOT)]
    failures: list[str] = []

    for instance in discover_case_instances(ROOT, case_ids):
        registry_path = instance.case_dir / "task" / "tests" / "semantic_checks.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        errors = validate_scoring_domains(list(registry.get("checks") or []))
        if errors:
            failures.append(
                f"{instance.case_id}::{instance.instance_id}: " + "; ".join(errors)
            )

    assert not failures, "\n".join(failures)
