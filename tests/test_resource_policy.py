from __future__ import annotations

from pathlib import Path

import pytest

from async_rbench.evaluation.protocol import ProtocolError, validate_adapter_event
from async_rbench.evaluation.resource_policy import validate_official_resource_policy


ROOT = Path(__file__).resolve().parents[1]
DEEPSEEK_CONFIG = ROOT / "configs/model-profiles/deepseek-v4-pro.yaml"


def test_calibration_profile_matches_official_resource_policy() -> None:
    digest = validate_official_resource_policy(
        ROOT, DEEPSEEK_CONFIG, episode_timeout_sec=2400, gateway_grace_sec=15,
    )
    assert len(digest) == 64


def test_official_resource_policy_rejects_runtime_drift() -> None:
    with pytest.raises(ValueError, match="resource policy mismatch"):
        validate_official_resource_policy(
            ROOT, DEEPSEEK_CONFIG, episode_timeout_sec=1800, gateway_grace_sec=15,
        )


def test_v101_explicit_episode_statuses_are_step_or_safety_bounded() -> None:
    validate_adapter_event({
        "type": "episode_ended",
        "local_status": "step_limit_reached",
        "declared_task_success": False,
    })
    validate_adapter_event({
        "type": "episode_ended",
        "local_status": "resource_safety_abort",
        "declared_task_success": False,
    })
    with pytest.raises(ProtocolError, match="local_status"):
        validate_adapter_event({
            "type": "episode_ended",
            "local_status": "budget_exhausted",
        })
    with pytest.raises(ProtocolError, match="local_status"):
        validate_adapter_event({"type": "episode_ended", "local_status": "unknown"})


def test_v101_runtime_diagnostic_events_are_protocol_validated() -> None:
    validate_adapter_event({
        "type": "finish_invoked",
        "requested_status": "completed",
        "pending_occurrence_count": 1,
        "active_response_window": False,
        "final_commit_current": False,
        "verification_current": False,
        "closure_complete": False,
    })
    validate_adapter_event({
        "type": "token_usage_snapshot",
        "emergency_cap": 20_000_000,
        "total": 12,
        "main": 7,
        "child": 5,
        "by_actor": {"main": 7, "child:c1": 5},
        "tripped": False,
        "trigger_role": None,
    })
    validate_adapter_event({
        "type": "resource_safety_abort",
        "emergency_cap": 20_000_000,
        "observed_total": 20_000_001,
        "trigger_role": "child:c1",
    })
    with pytest.raises(ProtocolError, match="unknown adapter event"):
        validate_adapter_event({
            "type": "child_token_budget_exhausted",
            "child_id": "c1",
            "reason": "old",
            "pool": "child_shared",
        })
