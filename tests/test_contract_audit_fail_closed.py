from __future__ import annotations

from types import SimpleNamespace

from async_rbench.evaluation import audit as audit_module
from async_rbench.evaluation.audit import audit_contract_fixtures


def _instance(workstream: dict) -> SimpleNamespace:
    raw = {
        "case_id": "fixture-case",
        "delegation_workstreams": [workstream],
        "information_sufficiency": [{
            "workstream_id": workstream["id"],
            "required_output_fields": list(workstream["required_evidence_fields"]),
        }],
    }
    return SimpleNamespace(
        instance_id="seed-1",
        load=lambda: SimpleNamespace(case_id="fixture-case", raw=raw),
    )


def _base_workstream() -> dict:
    return {
        "id": "worker",
        "required_evidence_fields": ["finding"],
        "public_evidence_schema": {"finding": {"type": "string"}},
        "evidence_schema": {"finding": {"type": "string", "const": "expected"}},
        "allowed_files": [],
        "required_files": [],
        "validator_command": "python3 -c \"raise SystemExit(0)\"",
        "validator_timeout_sec": 30,
    }


def test_submission_validator_without_public_report_contract_fails_closed(monkeypatch) -> None:
    workstream = {
        **_base_workstream(),
        "validator_stage": "submission_contract",
        "public_result_contract": {"kind": "payload_only"},
    }
    monkeypatch.setattr(
        audit_module, "discover_case_instances", lambda _root: [_instance(workstream)],
    )

    report = audit_contract_fixtures(SimpleNamespace())

    assert report["passed"] is False
    assert report["failed_workstreams"] == ["fixture-case/seed-1/worker"]
    row = report["workstreams"][0]
    assert row["validator_stage_valid"] is False
    assert row["hidden_submission_constraint"] is True


def test_semantic_validator_with_payload_only_is_not_hidden_submission_gate(monkeypatch) -> None:
    workstream = {
        **_base_workstream(),
        "validator_stage": "semantic_evidence",
        "public_result_contract": {"kind": "payload_only"},
    }
    monkeypatch.setattr(
        audit_module, "discover_case_instances", lambda _root: [_instance(workstream)],
    )

    report = audit_contract_fixtures(SimpleNamespace())

    assert report["passed"] is True
    assert report["hidden_validator_workstream_count"] == 0
    row = report["workstreams"][0]
    assert row["validator_stage_valid"] is True
    assert row["private_fixture_supported"] is False
    assert row["hidden_submission_constraint"] is False


def test_unknown_validator_stage_fails_closed(monkeypatch) -> None:
    workstream = {
        **_base_workstream(),
        "validator_stage": "mystery",
        "public_result_contract": {"kind": "payload_only"},
    }
    monkeypatch.setattr(
        audit_module, "discover_case_instances", lambda _root: [_instance(workstream)],
    )

    report = audit_contract_fixtures(SimpleNamespace())

    assert report["passed"] is False
    assert report["workstreams"][0]["validator_stage_valid"] is False
