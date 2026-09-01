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


def test_budget_exhausted_is_a_valid_explicit_episode_status() -> None:
    validate_adapter_event({
        "type": "episode_ended",
        "local_status": "budget_exhausted",
        "declared_task_success": False,
    })
    with pytest.raises(ProtocolError, match="local_status"):
        validate_adapter_event({"type": "episode_ended", "local_status": "unknown"})
