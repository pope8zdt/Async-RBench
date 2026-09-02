from __future__ import annotations

import pytest

from async_rbench.evaluation.case_contract import (
    ContractError,
    assert_participant_safe,
    public_delivery,
)
from async_rbench.evaluation.event_store import classify_visibility, strip_for_adapter
from async_rbench.evaluation.protocol import VISIBILITY_KERNEL_PRIVATE


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


def test_result_presented_projection_excludes_private_expected_effect() -> None:
    projected = strip_for_adapter({
        "type": "result_presented",
        "delivery_occurrence_id": "o1",
        "completion_id": "c1",
        "turn_id": "t2",
        "window_id": "w1",
        "payload": {"answer": 42},
        "payload_sha256": "a" * 64,
        "expected_disposition": "authoritative",
        "authoritative_result_kind": "wal",
        "stale": True,
        "stale_visibility": "latent",
        "controlled_order": True,
    })
    assert projected == {
        "type": "result_presented",
        "delivery_occurrence_id": "o1",
        "completion_id": "c1",
        "turn_id": "t2",
        "window_id": "w1",
        "payload": {"answer": 42},
        "payload_sha256": "a" * 64,
    }


def test_presentation_prepared_classifies_kernel_private_and_may_carry_snapshot_digest() -> None:
    # Kernel-private records may carry evaluator snapshot digests and source case
    # event ids; they never reach a model-visible surface, so they do not leak.
    event = {
        "type": "presentation_prepared",
        "delivery_occurrence_id": "o1",
        "completion_id": "c1",
        "snapshot_digest": "a" * 64,
        "case_event_id": "case123:e42",
    }
    assert classify_visibility(event["type"]) == VISIBILITY_KERNEL_PRIVATE
    assert event["snapshot_digest"] == "a" * 64
    assert event["case_event_id"] == "case123:e42"
