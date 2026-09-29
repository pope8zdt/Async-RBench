from __future__ import annotations

import json
from pathlib import Path

import yaml

from async_rbench.cli import main


def _public_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    case_dir = root / "data" / "async-rbench" / "cases" / "case-a"
    (case_dir / "public").mkdir(parents=True)
    (case_dir / "task" / "task_file").mkdir(parents=True)
    (root / "data" / "async-rbench" / "registry.json").write_text(json.dumps({
        "schema_version": "2",
        "case_families": [{
            "case_id": "case-a",
            "benchmark": "terminal-bench",
            "control_prefix": "ca",
            "instances": [{"instance_id": "seed-1", "path": ".", "split": "test"}],
        }],
    }), encoding="utf-8")
    (case_dir / "public" / "case.yaml").write_text(yaml.safe_dump({
        "format_version": 2,
        "case_id": "case-a",
        "title": "Case A",
        "task_instruction_path": "task/task.yaml",
        "source_tasks": [{"id": "source-a", "benchmark": "terminal-bench"}],
        "milestones": [{"id": "done", "depends_on": []}],
        "artifacts": [{"id": "answer", "path": "/app/answer.json"}],
        "workstreams": [{
            "id": "worker-a", "task": "Inspect input.", "targets": ["answer"],
            "expected_output": "Evidence.", "priority": "normal",
            "required_evidence_fields": ["value"],
            "evidence_schema": {"value": {"type": "integer"}},
            "allowed_files": [], "required_files": [],
            "public_result_contract": {"kind": "payload_only"},
        }],
        "public_checks": [],
    }, sort_keys=False), encoding="utf-8")
    (case_dir / "task" / "task.yaml").write_text(
        "instruction: Do task A.\ndifficulty: medium\n", encoding="utf-8"
    )
    # A malformed sentinel proves public commands never attempt to parse it.
    (case_dir / "evaluator").mkdir()
    (case_dir / "evaluator" / "case.yaml").write_text("[not: valid", encoding="utf-8")
    return root


def test_public_commands_work_without_judge_bundle(tmp_path: Path, capsys) -> None:
    root = _public_repo(tmp_path)

    assert main(["list", "--root", str(root)]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["cases"] == ["case-a"]

    assert main(["inspect", "case-a", "--root", str(root)]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["case_id"] == "case-a"
    assert "classification" not in inspected

    assert main(["validate-public", "--root", str(root)]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated == {"case_count": 1, "instances": 1, "valid": True}


def test_validate_alias_is_public_only(tmp_path: Path, capsys) -> None:
    root = _public_repo(tmp_path)
    assert main(["validate", "--root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True
