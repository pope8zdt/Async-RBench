from __future__ import annotations

import json

from async_rbench.source_fidelity import validate_candidate_source_fidelity


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value), encoding="utf-8")


def _candidate(tmp_path):
    root = tmp_path / "candidate"
    source_id = "database:011"
    _write(root / "public_case.yaml", {"source_tasks": [{"benchmark": "MultiAgentBench", "id": source_id}]})
    checks = [
        {"id": f"demo.source.{index}", "category": "source_semantics"}
        for index in range(4)
    ]
    _write(root / "task/tests/semantic_checks.json", {"checks": checks})
    _write(root / "task/task_file/scripts/write_manifest.py", f"SOURCE_ID={source_id!r}\n")
    _write(root / "PROVENANCE.md", f"Source: {source_id}\n")
    _write(root / "task/oracle.sh", "database_diagnosis\n")
    _write(
        root / "private/quality_contract.yaml",
        {"negative_mutations": [{"must_fail": ["demo.source.0"]}]},
    )
    return root


def test_source_fidelity_accepts_task_native_private_truth(tmp_path):
    root = _candidate(tmp_path)
    _write(root / "task/tests/fixtures/native_canonical_report.json", {"passed": True})

    assert validate_candidate_source_fidelity(root) == []


def test_source_fidelity_rejects_foreign_merger_and_public_truth(tmp_path):
    root = _candidate(tmp_path)
    _write(root / "task/upstream_solutions/multi-source-data-merger.sh", "test_merged_data_exact_values\n")
    _write(root / "task/task_file/native_canonical_report.json", {"answer": "secret"})

    errors = validate_candidate_source_fidelity(root)

    assert any("merger source identity" in error for error in errors)
    assert any("participant-visible" in error for error in errors)
