from __future__ import annotations

from pathlib import Path

import pytest

from async_rbench.evaluation.calibration import _frozen_point_ids
from async_rbench.evaluation.control_flow_gates import merge_test_point_pass_rate
from async_rbench.evaluation.scoring import _weighted_control_flow_counts, _weighted_semantic_counts
from async_rbench.evaluation.weighting import (
    control_flow_weight, point_weight, semantic_weight, semantic_weight_map,
)


ROOT = Path(__file__).resolve().parents[1]


def test_weight_comes_only_from_research_relevance_tier():
    assert point_weight({"relevance_tier": "critical"}) == 4
    assert semantic_weight({"measurement_type": "semantic", "relevance_tier": "direct"}) == 3
    assert control_flow_weight({"measurement_type": "control", "relevance_tier": "supporting"}) == 2
    assert point_weight({"relevance_tier": "base"}) == 1
    assert point_weight({}) == 1


def test_measurement_type_and_gate_do_not_change_weight():
    semantic = {"measurement_type": "semantic", "gate": "reject_late_stale", "relevance_tier": "direct"}
    control = {"measurement_type": "control", "gate": "wait_for_authority", "relevance_tier": "direct"}
    assert semantic_weight(semantic) == control_flow_weight(control) == 3


def test_semantic_weight_map_keys_by_id():
    mapping = semantic_weight_map({"checks": [
        {"id": "a", "relevance_tier": "critical"},
        {"id": "b", "relevance_tier": "base"},
    ]})
    assert mapping == {"a": 4, "b": 1}
    assert semantic_weight_map(None) == {}


def test_relevance_weights_are_consistent_across_scoring_consumers():
    semantic = [{"id": "s1", "passed": True}, {"id": "s2", "passed": False}]
    registry = {"checks": [
        {"id": "s1", "relevance_tier": "critical"},
        {"id": "s2", "relevance_tier": "base"},
    ]}
    control = [{
        "id": "c1", "gate": "wait_for_authority", "dimension": "event_intake",
        "relevance_tier": "direct", "status": "pass",
    }]
    assert _weighted_semantic_counts(semantic, registry) == {
        "passed": 4, "failed": 1, "total": 5,
    }
    assert _weighted_control_flow_counts(control)["passed"] == 3
    assert merge_test_point_pass_rate(
        semantic, None, control, semantic_registry=registry,
    ) == pytest.approx(0.96)


def test_calibration_snapshot_uses_registry_relevance_tiers():
    _, _, _, weights = _frozen_point_ids(ROOT)
    async_weights = weights["secure-release"]["async"]
    assert async_weights["sr.stale.pre_rewrite_main_patch_rejected"] == 4
    assert async_weights["sr.lineage.sanitized_head_reachable"] == 3
    assert async_weights["sr.lineage.manifest_schema"] == 1
    assert async_weights["sr.cf.reject_pre_rewrite_deployment"] == 4
    assert async_weights["sr.cf.redeploy_from_clean_baseline"] == 4
