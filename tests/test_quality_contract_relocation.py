from __future__ import annotations

import json

from async_rbench.case_quality import validate_relocatable_source_contract


def _write_contract(case_dir, task_path: str) -> None:
    private = case_dir / "private"
    private.mkdir(parents=True)
    (private / "source_task.yaml").write_text("instruction: source\n", encoding="utf-8")
    (private / "quality_contract.yaml").write_text(
        json.dumps({
            "schema_version": "1",
            "source_contract": {
                "instruction_preservation": "verbatim_append",
                "sources": [{"task_id": "source-1", "task_path": task_path}],
            },
        }),
        encoding="utf-8",
    )


def test_relocatable_source_contract_accepts_case_relative_snapshot(tmp_path):
    case_dir = tmp_path / "candidate_cases" / "demo"
    _write_contract(case_dir, "private/source_task.yaml")

    assert validate_relocatable_source_contract(case_dir) == []


def test_relocatable_source_contract_rejects_candidate_root_path(tmp_path):
    case_dir = tmp_path / "candidate_cases" / "demo"
    _write_contract(case_dir, "candidate_cases/demo/private/source_task.yaml")

    errors = validate_relocatable_source_contract(case_dir)
    assert len(errors) == 1
    assert "relocation-safe" in errors[0]
