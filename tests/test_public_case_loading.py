from __future__ import annotations

import json
from pathlib import Path

import yaml

from async_rbench.public_spec import load_public_case, validate_public_case
from async_rbench.spec import discover_case_instances, discover_cases


def _write_public_case(root: Path, case_id: str = "public-only") -> Path:
    case_dir = root / "data" / "async-rbench" / "cases" / case_id
    (case_dir / "public").mkdir(parents=True)
    (case_dir / "task" / "task_file").mkdir(parents=True)
    public = {
        "format_version": 2,
        "case_id": case_id,
        "title": "Public only case",
        "task_instruction_path": "task/task.yaml",
        "source_tasks": [{"id": "source-1", "benchmark": "Terminal-Bench"}],
        "milestones": [{"id": "done", "depends_on": []}],
        "artifacts": [{"id": "answer", "path": "/app/answer.txt"}],
        "workstreams": [{
            "id": "worker-a",
            "task": "Produce the answer.",
            "targets": ["answer"],
            "expected_output": "answer.txt",
            "priority": "normal",
            "required_evidence_fields": [],
            "evidence_schema": {},
            "allowed_files": ["/app/answer.txt"],
            "required_files": ["/app/answer.txt"],
            "public_result_contract": {"kind": "payload_only"},
        }],
        "public_checks": [],
    }
    (case_dir / "public" / "case.yaml").write_text(
        yaml.safe_dump(public, sort_keys=False), encoding="utf-8",
    )
    (case_dir / "task" / "task.yaml").write_text(
        yaml.safe_dump({"instruction": "Do the public task.", "difficulty": "medium"}),
        encoding="utf-8",
    )
    (case_dir / "task" / "task_file" / "input.txt").write_text("input\n", encoding="utf-8")
    return case_dir


def _write_registry(root: Path, case_id: str = "public-only") -> None:
    path = root / "data" / "async-rbench" / "registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": "2",
        "case_families": [{
            "case_id": case_id,
            "benchmark": "terminal-bench",
            "control_prefix": "po",
            "instances": [{"instance_id": "seed-1", "path": ".", "split": "test"}],
        }],
    }), encoding="utf-8")


def test_public_case_loads_without_evaluator_directory(tmp_path: Path) -> None:
    case_dir = _write_public_case(tmp_path)

    spec = load_public_case(case_dir / "public" / "case.yaml")

    assert spec.case_id == "public-only"
    assert spec.case_dir == case_dir
    assert spec.raw["instruction"] == "Do the public task."
    assert spec.raw["difficulty"] == "medium"
    assert [row["id"] for row in spec.raw["delegation_workstreams"]] == ["worker-a"]
    assert "classification" not in spec.raw
    assert "hidden_reverification_commands" not in spec.raw
    assert validate_public_case(spec) == []


def test_public_discovery_never_reads_present_evaluator_truth(tmp_path: Path) -> None:
    case_dir = _write_public_case(tmp_path)
    (case_dir / "evaluator").mkdir()
    (case_dir / "evaluator" / "case.yaml").write_text(": invalid judge yaml", encoding="utf-8")
    _write_registry(tmp_path)

    cases = discover_cases(tmp_path)
    instances = discover_case_instances(tmp_path)

    assert [case.case_id for case in cases] == ["public-only"]
    assert [instance.load().case_id for instance in instances] == ["public-only"]


def test_public_case_rejects_private_fields_in_public_contract(tmp_path: Path) -> None:
    case_dir = _write_public_case(tmp_path)
    path = case_dir / "public" / "case.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["classification"] = {"primary_event_theme": "secret"}
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    spec = load_public_case(path)
    errors = validate_public_case(spec)

    assert any("private field 'classification'" in error for error in errors)


def test_public_case_rejects_task_instruction_path_escape(tmp_path: Path) -> None:
    case_dir = _write_public_case(tmp_path)
    path = case_dir / "public" / "case.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["task_instruction_path"] = "../../outside.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    try:
        load_public_case(path)
    except ValueError as exc:
        assert "task_instruction_path escapes case directory" in str(exc)
    else:
        raise AssertionError("escaping task_instruction_path was accepted")
