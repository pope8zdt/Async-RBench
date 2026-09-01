from __future__ import annotations

import pytest

from async_rbench.evaluation.case_contract import (
    ContractError,
    assert_participant_safe,
    public_delivery,
)


def test_public_delivery_is_an_allowlist_projection() -> None:
    projected = public_delivery({
        "type": "result_delivered",
        "child_id": "child-1",
        "completion_id": "completion-1",
        "result_kind": "authoritative_answer",
        "payload": {"revision": "r2"},
        "payload_sha256": "a" * 64,
        "stale": True,
        "stale_visibility": "latent",
        "benchmark_event_id": "case_async_authority",
        "invalidates_artifacts": ["final"],
        "reopens_milestones": ["replan"],
        "controlled_order": True,
    }, workstream_id="inspect_revision")
    assert projected == {
        "type": "result_delivered",
        "child_id": "child-1",
        "completion_id": "completion-1",
        "workstream_id": "inspect_revision",
        "payload": {"revision": "r2"},
        "payload_sha256": "a" * 64,
    }


def test_participant_surface_rejects_private_fields_recursively() -> None:
    with pytest.raises(ContractError):
        assert_participant_safe(
            {"message": {"stale_visibility": "latent"}}, surface="model transcript",
        )
