from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.migrate_workstream_result_contracts import (
    ValidatorMigration,
    classify_validator,
    migrate_corpus,
)


REPORT_EQUALITY_COMMAND = (
    "python3 -c \"import base64,json,os,pathlib; "
    "e=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64']))['evidence']; "
    "p=pathlib.Path(e['report_path']); assert p.is_file(); r=json.load(open(p)); "
    "assert r['finding']==e['finding']; "
    "assert r['revision_sha256']==e['revision_sha256']\""
)
FILE_EXISTS_COMMAND = (
    "python3 -c \"import base64,json,os,pathlib; "
    "e=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64']))['evidence']; "
    "p=pathlib.Path(e['report_path']); assert p.is_file()\""
)
COMPLEX_COMMAND = (
    "python3 -c \"import json; rows=json.load(open('/app/data.json')); "
    "assert len(rows)==11\""
)


def test_classifies_observed_validator_families() -> None:
    assert classify_validator(REPORT_EQUALITY_COMMAND) == ValidatorMigration(
        stage="submission_contract",
        kind="report_file",
        fields=("finding", "revision_sha256"),
        must_be_valid_json=True,
    )
    exists = classify_validator(FILE_EXISTS_COMMAND)
    assert exists.stage == "submission_contract"
    assert exists.kind == "report_file"
    assert exists.fields == ()
    assert exists.must_be_valid_json is False
    assert classify_validator(COMPLEX_COMMAND).stage == "semantic_evidence"


def _write_minimal_corpus(root: Path) -> None:
    case = root / "cases" / "fixture"
    (case / "private").mkdir(parents=True)
    (case / "public_case.yaml").write_text(yaml.safe_dump({
        "format_version": 2,
        "case_id": "fixture",
        "workstreams": [{
            "id": "worker",
            "required_evidence_fields": ["report_path", "finding", "revision_sha256"],
            "evidence_schema": {
                "report_path": {"type": "string"},
                "finding": {"type": "string"},
                "revision_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "allowed_files": ["/app/output_data/workstreams/worker.json"],
            "required_files": ["/app/output_data/workstreams/worker.json"],
            "public_result_contract": {"kind": "payload_only"},
        }],
    }, sort_keys=False), encoding="utf-8")
    (case / "private" / "private_case.yaml").write_text(json.dumps({
        "format_version": 2,
        "case_id": "fixture",
        "workstream_bindings": {
            "worker": {
                "result_kind": "result_01",
                "validator_command": REPORT_EQUALITY_COMMAND,
                "validator_timeout_sec": 120,
                "private_evidence_schema": {
                    "report_path": {"type": "string"},
                    "finding": {"type": "string"},
                    "revision_sha256": {
                        "type": "string", "pattern": "^[0-9a-f]{64}$",
                    },
                },
            },
        },
    }, indent=2), encoding="utf-8")


def test_migration_is_idempotent_and_renders_public_report_contract(tmp_path: Path) -> None:
    _write_minimal_corpus(tmp_path)

    first = migrate_corpus(tmp_path, apply=True)
    public_path = tmp_path / "cases" / "fixture" / "public_case.yaml"
    private_path = tmp_path / "cases" / "fixture" / "private" / "private_case.yaml"
    first_bytes = (public_path.read_bytes(), private_path.read_bytes())
    second = migrate_corpus(tmp_path, apply=True)

    assert first["errors"] == []
    assert first["changes_required"] == 1
    assert second["errors"] == []
    assert second["changes_required"] == 0
    assert (public_path.read_bytes(), private_path.read_bytes()) == first_bytes
    public = yaml.safe_load(public_path.read_text(encoding="utf-8"))
    private = yaml.safe_load(private_path.read_text(encoding="utf-8"))
    contract = public["workstreams"][0]["public_result_contract"]
    assert contract["kind"] == "report_file"
    assert contract["report_file"]["fields_equal_evidence"] == [
        "finding", "revision_sha256",
    ]
    assert private["workstream_bindings"]["worker"]["validator_stage"] == (
        "submission_contract"
    )
