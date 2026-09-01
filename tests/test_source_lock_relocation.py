from __future__ import annotations

import json

from async_rbench.provenance import validate_relocatable_source_native_lock


def _write_lock(case_dir, source_path: str, production_path: str = ".") -> None:
    private = case_dir / "private"
    private.mkdir(parents=True, exist_ok=True)
    (private / "source_lock.json").write_text(json.dumps({
        "production_case_path": production_path,
        "source_files": [source_path],
        "source_file_sha256": {source_path: "0" * 64},
    }), encoding="utf-8")


def test_source_lock_accepts_case_relative_path(tmp_path):
    case_dir = tmp_path / "candidate_cases" / "demo"
    (case_dir / "private").mkdir(parents=True)
    (case_dir / "private/official_task.json").write_text("{}", encoding="utf-8")
    _write_lock(case_dir, "private/official_task.json")
    assert validate_relocatable_source_native_lock(case_dir) == []


def test_source_lock_rejects_candidate_coupled_paths(tmp_path):
    case_dir = tmp_path / "candidate_cases" / "demo"
    _write_lock(
        case_dir,
        "candidate_cases/demo/private/official_task.json",
        "candidate_cases/demo",
    )
    errors = validate_relocatable_source_native_lock(case_dir)
    assert len(errors) == 2
    assert any("case-relative" in error for error in errors)
    assert any("production_case_path" in error for error in errors)


def test_source_lock_rejects_missing_case_contained_file(tmp_path):
    case_dir = tmp_path / "candidate_cases" / "demo"
    _write_lock(case_dir, "private/missing.json")
    errors = validate_relocatable_source_native_lock(case_dir)
    assert errors == [
        "demo: case-contained locked source file is missing: private/missing.json"
    ]


def test_source_lock_rejects_repository_artifact_path(tmp_path):
    case_dir = tmp_path / "candidate_cases" / "demo"
    _write_lock(case_dir, "artifacts/source-native-v4/native_case.json")
    errors = validate_relocatable_source_native_lock(case_dir)
    assert errors == [
        "demo: source-native lock path must be case-relative under private/: "
        "artifacts/source-native-v4/native_case.json"
    ]
