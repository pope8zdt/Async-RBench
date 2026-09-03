from __future__ import annotations

import asyncio
from typing import Any

import pytest

from async_rbench.evaluation.public_result_validation import (
    validate_public_contract_definition,
    validate_public_submission,
)
from async_rbench.evaluation.workspace_runtime import CommandResult


BASE = {
    "required_evidence_fields": ["report_path", "finding"],
    "evidence_schema": {
        "report_path": {"type": "string"},
        "finding": {"type": "string"},
    },
    "allowed_files": ["/app/out.json"],
    "required_files": ["/app/out.json"],
}


@pytest.mark.parametrize(("contract", "expected_error"), [
    ({}, "public_result_contract.kind is required"),
    ({"kind": "unknown"}, "unsupported public_result_contract.kind"),
    ({"kind": "report_file", "report_file": {}}, "report_file.path is required"),
])
def test_invalid_public_contract_fails_definition_validation(
    contract: dict[str, Any], expected_error: str,
) -> None:
    errors = validate_public_contract_definition({**BASE, "public_result_contract": contract})
    assert any(expected_error in error for error in errors)


def test_payload_only_does_not_invent_report_path_binding() -> None:
    workstream = {**BASE, "public_result_contract": {"kind": "payload_only"}}
    event = {"child_id": "c1", "payload": {
        "evidence": {"report_path": "/app/other.json", "finding": "x"},
        "files": ["/app/out.json"],
    }}
    workspace = RecordingWorkspace()
    result = asyncio.run(validate_public_submission(workstream, event, workspace))
    assert result.valid is True
    assert workspace.calls == []


def test_report_file_definition_and_path_are_strict() -> None:
    contract = {
        "kind": "report_file",
        "report_file": {
            "path": "/app/out.json",
            "must_exist": True,
            "must_be_valid_json": True,
            "fields_equal_evidence": ["finding"],
        },
    }
    workstream = {**BASE, "public_result_contract": contract}
    assert validate_public_contract_definition(workstream) == ()
    duplicate = {
        **workstream,
        "public_result_contract": {
            "kind": "report_file",
            "report_file": {**contract["report_file"], "fields_equal_evidence": ["finding", "finding"]},
        },
    }
    assert any("must be unique" in e for e in validate_public_contract_definition(duplicate))
    non_json = {
        **workstream,
        "public_result_contract": {
            "kind": "report_file",
            "report_file": {**contract["report_file"], "must_be_valid_json": False},
        },
    }
    assert any("must_be_valid_json" in e for e in validate_public_contract_definition(non_json))

    event = {"child_id": "c1", "payload": {
        "evidence": {"report_path": "/app/other.json", "finding": "x"},
        "files": ["/app/out.json"],
    }}
    result = asyncio.run(validate_public_submission(workstream, event, RecordingWorkspace()))
    assert result.reason_codes == ("report_path_not_required_file",)


class RecordingWorkspace:
    def __init__(self, result: CommandResult | None = None) -> None:
        self.result = result or CommandResult(0, "")
        self.calls: list[tuple[str, str, int]] = []

    async def child_terminal(self, child_id: str, command: str, timeout: int) -> CommandResult:
        self.calls.append((child_id, command, timeout))
        return self.result


def test_report_file_surfaces_granular_public_validator_code() -> None:
    workstream = {
        **BASE,
        "public_result_contract": {
            "kind": "report_file",
            "report_file": {
                "path": "/app/out.json",
                "must_exist": True,
                "must_be_valid_json": True,
                "fields_equal_evidence": ["finding"],
            },
        },
    }
    event = {"child_id": "c1", "payload": {
        "evidence": {"report_path": "/app/out.json", "finding": "x"},
        "files": ["/app/out.json"],
    }}
    workspace = RecordingWorkspace(CommandResult(
        1, "ASYNC_RBENCH_CONTRACT_FAIL:report_json_invalid\n",
    ))
    result = asyncio.run(validate_public_submission(workstream, event, workspace))
    assert result.valid is False
    assert result.reason_codes == ("report_json_invalid",)
