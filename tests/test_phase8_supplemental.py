from __future__ import annotations

from async_rbench.evaluation.case_contract import public_delivery, public_rejection
from async_rbench.evaluation.scoring import _materialize_private_delivery_facts


def test_public_delivery_drops_all_control_truth() -> None:
    public = public_delivery({
        "child_id": "c", "completion_id": "p", "payload": {"x": 1},
        "payload_sha256": "a" * 64, "result_kind": "private-role",
        "stale": True, "invalidates_artifacts": ["a"], "reopens_milestones": ["m"],
    }, workstream_id="ws")
    assert set(public) == {
        "type", "child_id", "completion_id", "workstream_id", "payload", "payload_sha256",
    }


def test_public_rejection_drops_private_role() -> None:
    public = public_rejection({
        "child_id": "c", "completion_id": "p", "result_kind": "private-role",
        "reason_codes": ["missing_required_evidence", "validator_command_failed"],
    }, workstream_id="ws")
    assert set(public) == {
        "type", "child_id", "completion_id", "workstream_id", "reason_codes",
    }
    assert public["reason_codes"] == [
        "missing_required_evidence", "result_contract_rejected",
    ]


def test_scorer_recovers_exact_private_rejection_reason() -> None:
    materialized = _materialize_private_delivery_facts([
        {
            "type": "result_rejection_evaluator_fact",
            "completion_id": "p",
            "result_kind": "private-role",
            "reason_codes": ["validator_command_failed"],
        },
        {
            "type": "result_rejected",
            "completion_id": "p",
            "reason_codes": ["result_contract_rejected"],
        },
    ])
    rejection = materialized[-1]
    assert rejection["result_kind"] == "private-role"
    assert rejection["reason_codes"] == ["validator_command_failed"]
