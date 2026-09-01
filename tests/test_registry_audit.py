from __future__ import annotations

import json
from pathlib import Path

from async_rbench.evaluation.registry_audit import validate_semantic_registries


ROOT = Path(__file__).resolve().parents[1]


def test_registered_semantic_registries_are_content_derived_and_valid() -> None:
    assert validate_semantic_registries(ROOT) == []


def test_registry_audit_rejects_duplicate_ids_and_nodes(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "case-a"
    registry_dir = case_dir / "task" / "tests"
    registry_dir.mkdir(parents=True)
    (tmp_path / "cases" / "registry.json").write_text(
        json.dumps({
                "schema_version": "2",
                "case_families": [
                    {
                        "case_id": "case-a", "benchmark": "terminal-bench",
                        "control_prefix": "ca",
                        "instances": [
                            {"instance_id": "seed-1", "path": ".", "split": "calibration"}
                        ],
                    }
                ],
        }),
        encoding="utf-8",
    )
    (case_dir / "public_case.yaml").write_text(
        "format_version: 2\ncase_id: case-a\ntitle: Case A\ntask_instruction_path: task/task.yaml\nartifacts: []\nworkstreams: []\npublic_checks: []\n",
        encoding="utf-8",
    )
    (case_dir / "private").mkdir()
    (case_dir / "private" / "private_case.yaml").write_text(
        "format_version: 2\ncase_id: case-a\ncapabilities: []\nworkstream_bindings: {}\nscenarios:\n  linear: {events: []}\n  async: {events: []}\nhidden_checks: {}\ninformation_sufficiency: []\n",
        encoding="utf-8",
    )
    (case_dir / "task" / "task.yaml").write_text("instruction: test\n", encoding="utf-8")
    (registry_dir / "test_case_outcomes.py").write_text("def test_present(): pass\n", encoding="utf-8")
    checks = [
        {
            "id": "same",
            "pytest_node": "test_case_outcomes.py::test_present",
            "category": "authority_final_truth",
            "description": "present",
            "critical": True,
            "measurement_type": "semantic",
            "capability_target": "async_result_integration",
            "relevance_tier": "direct",
        }
    ] * 24
    (registry_dir / "semantic_checks.json").write_text(
        json.dumps({"version": "3", "checks": checks}), encoding="utf-8"
    )

    errors = validate_semantic_registries(tmp_path)
    assert any("duplicate semantic check id" in error for error in errors)
    assert any("duplicate semantic pytest node" in error for error in errors)
