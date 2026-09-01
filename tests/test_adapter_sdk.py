from __future__ import annotations

import io
import json

import pytest

from async_rbench.evaluation.protocol import ProtocolError, validate_adapter_event
from async_rbench.protocol_sdk.gateway import JsonlGateway, configure_utf8_stdio


def _emit_all(gateway: JsonlGateway) -> list[dict]:
    lines = [line for line in gateway.stdout.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def test_sdk_helpers_emit_valid_events():
    out = io.StringIO()
    gateway = JsonlGateway(stdout=out)
    gateway.child_spawned("c1", ["wal_recovery"])
    gateway.child_started("c1")
    gateway.child_progress_checkpoint("c1", 17)
    gateway.child_completed("c1", "comp-1", {"rows": 11})
    gateway.main_action("a1", "terminal")
    gateway.child_path_promotion_result(
        "a2", "comp-1", "c1", "/child/out.json", "/app/out.json",
        True, 0,
    )
    gateway.result_consumed("comp-1", "a1")
    gateway.artifact_committed(
        "artifact", "v1", ["comp-1"],
        observed_digest="a" * 64, observed_path="/tmp/artifact",
    )
    events = _emit_all(gateway)
    assert [event["type"] for event in events] == [
        "child_spawned", "child_started", "child_progress_checkpoint",
        "child_completed", "main_action", "child_path_promotion_result",
        "result_consumed", "artifact_committed",
    ]
    for event in events:
        validate_adapter_event(event)


def test_child_progress_checkpoint_rejects_invalid_phase_or_tokens():
    with pytest.raises(ProtocolError, match="phase"):
        validate_adapter_event({
            "type": "child_progress_checkpoint", "child_id": "c1",
            "phase": "started", "tokens": 1,
        })


def test_child_path_promotion_result_requires_typed_outcome():
    with pytest.raises(ProtocolError, match="success"):
        validate_adapter_event({
            "type": "child_path_promotion_result", "action_id": "a1",
            "completion_id": "p1", "child_id": "c1",
            "source_path": "/child/a", "destination_path": "/app/a",
            "success": "yes", "exit_code": 0,
        })
    with pytest.raises(ProtocolError, match="tokens"):
        validate_adapter_event({
            "type": "child_progress_checkpoint", "child_id": "c1",
            "phase": "first_model_turn_finished", "tokens": -1,
        })


def test_artifact_committed_is_evaluator_observed():
    out = io.StringIO()
    JsonlGateway(stdout=out).artifact_committed(
        "artifact", "v1", ["comp-1"], observed_digest="b" * 64, observed_path="/x",
    )
    event = json.loads(out.getvalue().splitlines()[0])
    assert event["evaluator_observed"] is True
    assert event["observed_digest"] == "b" * 64
    assert event["observed_path"] == "/x"


def test_adapter_cannot_self_report_private_verification():
    with pytest.raises(ProtocolError, match="unknown adapter event type"):
        validate_adapter_event({
            "type": "verification_requested", "check_id": "check-1",
            "passed": True, "lineage_completion_ids": ["comp-1"],
            "evaluator_owned": True,
        })


def test_emit_validates_before_write():
    out = io.StringIO()
    gateway = JsonlGateway(stdout=out)
    with pytest.raises(ProtocolError):
        gateway.artifact_committed("artifact", "v1", ["comp-1"], observed_digest="not-a-sha256")
    # Nothing was written for the rejected event.
    assert out.getvalue() == ""


def test_configure_utf8_stdio_does_not_raise():
    configure_utf8_stdio()
