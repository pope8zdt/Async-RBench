from __future__ import annotations

import json
from pathlib import Path

from async_rbench.evaluation.report_contract import (
    build_report_fixture,
    classify_validator_output,
    has_hidden_validator,
    locate_fixture_report_file,
    render_validator_command,
    report_contract_errors,
    run_report_validator,
    validator_code_lines,
)
from async_rbench.evaluation.result_contract import validate_payload_contract


CONTRACT = {
    "kind": "report_file",
    "report_file": {
        "path": "/app/output_data/workstreams/requirement_worker_01.json",
        "must_exist": True,
        "must_be_valid_json": True,
        "fields_equal_evidence": ["finding", "revision_sha256"],
    },
}
REQUIRED_FILE = "/app/output_data/workstreams/requirement_worker_01.json"
WORKSTREAM = {
    "public_result_contract": CONTRACT,
    "required_files": [REQUIRED_FILE],
    "allowed_files": [REQUIRED_FILE],
    "required_evidence_fields": ["report_path", "revision_sha256", "finding"],
    "evidence_schema": {
        "report_path": {"type": "string", "pattern": "^/app/output_data/workstreams/.+\\.json$"},
        "revision_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "finding": {"type": "string"},
    },
}


def test_rendered_validator_compiles_and_is_deterministic() -> None:
    cmd = render_validator_command(CONTRACT, REQUIRED_FILE)
    inner = cmd.split('python3 -c "', 1)[1].rsplit('"', 1)[0]
    compile(inner, "<fixture>", "exec")
    assert cmd == render_validator_command(CONTRACT, REQUIRED_FILE)
    # p0-4: a drift between validator and contract must not be silently accepted.
    assert report_contract_errors(WORKSTREAM) == []


def test_rules_are_public_not_hidden() -> None:
    assert has_hidden_validator(WORKSTREAM) is False
    hidden = dict(WORKSTREAM)
    hidden["validator_command"] = render_validator_command(CONTRACT, REQUIRED_FILE)
    hidden["public_result_contract"] = {}
    assert has_hidden_validator(hidden) is True


def test_report_path_aligns_to_single_required_file() -> None:
    # The report artifact must be the one files[0] the evaluator inspects.
    event = {
        "type": "child_completed",
        "payload": {
            "evidence": {
                "report_path": "/app/output_data/workstreams/other.json",
                "revision_sha256": "0" * 64,
                "finding": "x",
            },
            "files": [REQUIRED_FILE],
        },
    }
    codes, _ = validate_payload_contract(WORKSTREAM, event)
    assert "report_path_not_required_file" in codes


def test_private_validator_executes_on_fixtures() -> None:
    fixture = build_report_fixture(WORKSTREAM)
    assert fixture["report_path"] == REQUIRED_FILE
    assert "report_file_missing" in fixture["negatives"]
    assert "report_json_invalid" in fixture["negatives"]
    assert "report_missing_required_field" in fixture["negatives"]
    assert "report_payload_field_mismatch" in fixture["negatives"]
    assert "report_path_not_required_file" in fixture["negatives"]

    import tempfile

    with tempfile.TemporaryDirectory(prefix="rbench-rpt-") as td:
        workspace_root = Path(td)
        report_file = locate_fixture_report_file(fixture, workspace_root)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        evidence = fixture["positive"]["payload"]["evidence"]

        def stage_valid() -> None:
            report_file.write_text(
                json.dumps({
                    "finding": evidence["finding"],
                    "revision_sha256": evidence["revision_sha256"],
                }, ensure_ascii=False),
                encoding="utf-8",
            )

        stage_valid()
        positive_code, positive_marks = run_report_validator(
            WORKSTREAM, workspace_root, fixture["positive"]["payload"],
        )
        assert positive_code == 0 and positive_marks == []

        stage_valid()
        report_file.unlink(missing_ok=True)
        code, marks = run_report_validator(
            WORKSTREAM, workspace_root, fixture["negatives"]["report_file_missing"]["payload"],
        )
        assert code != 0 and marks[0][0] == "report_file_missing"

        stage_valid()
        report_file.write_text("{not valid json", encoding="utf-8")
        code, marks = run_report_validator(
            WORKSTREAM, workspace_root, fixture["negatives"]["report_json_invalid"]["payload"],
        )
        assert code != 0 and marks[0][0] == "report_json_invalid"

        stage_valid()
        report_file.write_text(
            json.dumps({"revision_sha256": evidence["revision_sha256"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        code, marks = run_report_validator(
            WORKSTREAM, workspace_root, fixture["negatives"]["report_missing_required_field"]["payload"],
        )
        assert code != 0 and marks[0][0] == "report_missing_required_field"

        stage_valid()
        code, marks = run_report_validator(
            WORKSTREAM, workspace_root, fixture["negatives"]["report_path_not_required_file"]["payload"],
        )
        assert code != 0 and marks[0][0] == "report_path_not_required_file"


def test_classify_validator_output_parses_granular_codes() -> None:
    output = "ASYNC_RBENCH_CONTRACT_FAIL:report_payload_field_mismatch:finding\n"
    assert classify_validator_output(output) == [("report_payload_field_mismatch", "finding")]
    assert classify_validator_output("") == []
    assert classify_validator_output("other log line") == []
