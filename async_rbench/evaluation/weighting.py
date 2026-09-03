"""Single source of truth for Async-RBench component scoring.

Semantic and dynamic-control points remain independently observable.  Relevance
tiers weight points *inside* a component, while fixed component masses prevent
the much larger semantic registry from drowning the dynamic construct.
"""

from __future__ import annotations

from typing import Any

MEASUREMENT_TYPES = frozenset({"semantic", "control"})

DYNAMIC_CONTROL_DIMENSIONS = (
    "event_intake",
    "state_revision",
    "plan_revision",
    "closure",
)

GATE_DYNAMIC_DIMENSIONS = {
    "wait_for_authority": "event_intake",
    "reject_late_stale": "state_revision",
    "resolve_authority": "state_revision",
    "timely_cancellation": "plan_revision",
    "selective_replan": "plan_revision",
    "rederive_from_authority": "closure",
    "deduplicate_completion": "state_revision",
    "recover_failed_work": "plan_revision",
    "arbitrate_conflict": "state_revision",
    "resource_triage": "plan_revision",
}

SCORE_POLICY_VERSION = "dtbench-v9-causal-groups-2"
DYNAMIC_COMPONENT_MASS = 0.80
SEMANTIC_COMPONENT_MASS = 0.20
DYNAMIC_SUCCESS_THRESHOLD = 0.75

CAPABILITY_TARGETS = frozenset({
    "base_task_completion",
    "async_result_integration",
    "async_dynamic_replanning",
    "async_consistency_closure",
})

RELEVANCE_WEIGHTS = {
    "base": 1,
    "supporting": 2,
    "direct": 3,
    "critical": 4,
}

# Kept as a compatibility name for static audits.  In v9 this is the complete
# semantic component mass, not a share computed from the number of points.
MAX_BASE_WEIGHT_SHARE = SEMANTIC_COMPONENT_MASS

ASYNC_EXECUTION_MODES = frozenset({"async"})


def point_weight(item: dict[str, Any]) -> int:
    """Return a point's frozen weight from research relevance alone."""
    return RELEVANCE_WEIGHTS.get(str(item.get("relevance_tier") or ""), 1)


def semantic_weight(item: dict[str, Any]) -> int:
    """Weight of a semantic point; measurement type is intentionally ignored."""
    return point_weight(item)


def control_flow_weight(item: dict[str, Any]) -> int:
    """Weight of a control point; gate name is intentionally ignored."""
    return point_weight(item)


def semantic_weight_map(
    semantic_registry: dict[str, Any] | list[dict[str, Any]] | None,
) -> dict[str, int]:
    """Id -> weight map over a semantic registry (dict with ``checks`` or a list)."""
    checks: list[dict[str, Any]] | None
    if isinstance(semantic_registry, dict):
        checks = (
            semantic_registry.get("checks")
            if isinstance(semantic_registry.get("checks"), list)
            else None
        )
    elif isinstance(semantic_registry, list):
        checks = semantic_registry
    else:
        checks = None
    if not checks:
        return {}
    return {
        str(item.get("id")): semantic_weight(item)
        for item in checks
        if isinstance(item, dict) and item.get("id") is not None
    }
