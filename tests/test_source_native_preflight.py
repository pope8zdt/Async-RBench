import hashlib
import json
from pathlib import Path

from scripts.preflight_source_native_v4 import (
    ROOT,
    audit_marble_source_record,
    audit_case,
    expected_source_task_id,
    resolve_contained,
)


SOURCE_ROOT = ROOT / "artifacts/source-native-v4"

from author_local import requires_author_local

_MANIFEST_IDENTITY = requires_author_local("artifacts/source-native-v4/native_manifest.jsonl")


def test_resolve_contained_rejects_absolute_and_parent_escape(tmp_path):
    assert resolve_contained(tmp_path, "../escape", "candidate")[1] == (
        "candidate_outside_root"
    )
    assert resolve_contained(tmp_path, str(tmp_path.resolve()), "candidate")[1] == (
        "candidate_absolute"
    )
    resolved, error = resolve_contained(tmp_path, "inside/file.json", "candidate")
    assert error is None
    assert resolved == (tmp_path / "inside/file.json").resolve()


def test_source_task_identity_is_benchmark_specific():
    assert expected_source_task_id(
        "OSWorld", {"domain": "chrome", "task_id": "task-1"}
    ) == "osworld:chrome:task-1"
    assert expected_source_task_id(
        "SWE-bench", {"instance_id": "org__repo-1"}
    ) == "org__repo-1"
    assert expected_source_task_id(
        "MultiAgentBench", {"task_id": "coding:001"}
    ) == "coding:001"


@_MANIFEST_IDENTITY
def test_audit_cross_checks_manifest_identity_against_spec():
    rows = [
        json.loads(line)
        for line in (SOURCE_ROOT / "native_manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    row = next(item for item in rows if item["benchmark"] == "OSWorld")
    schema = json.loads(
        (ROOT / "schemas/source_native_case_v4.schema.json").read_text(encoding="utf-8")
    )
    mismatched = dict(row, benchmark="MultiAgentBench")
    errors = audit_case(SOURCE_ROOT, mismatched, schema)
    assert "manifest_spec_benchmark_mismatch" in errors


def test_marble_source_line_and_digest_are_verified(tmp_path):
    source = tmp_path / "tasks.jsonl"
    payload = {"task_id": 8, "scenario": "database", "task": "diagnose"}
    source.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    binding = {
        "line_number": 1,
        "record_sha256": digest,
        "scenario": "database",
        "task_id": "database:008",
    }
    assert audit_marble_source_record(source, binding) == []
    assert "marble_source_record_hash_mismatch" in audit_marble_source_record(
        source, dict(binding, record_sha256="0" * 64)
    )
    assert audit_marble_source_record(source, dict(binding, line_number=2)) == [
        "marble_source_line_missing"
    ]
