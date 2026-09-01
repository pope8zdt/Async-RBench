"""Frozen authoring policies for the eight asynchronous event themes.

Event themes classify evaluator-owned stimuli.  They deliberately do not name
participant capabilities and they do not prescribe a fixed number of scoring
points.  A Case IR selects the obligations that are causally meaningful for a
particular task and binds each obligation to task-specific evidence.
"""

from __future__ import annotations

from typing import Any


EVENT_POLICY_VERSION = "1"

EVENT_POLICIES: dict[str, dict[str, Any]] = {
    "delayed_authoritative_result": {
        "required_obligations": {"classify_authority", "revise_affected", "verify_closure"},
        "mutation_families": {"ignore_authority", "retain_provisional", "skip_reverification"},
    },
    "late_or_out_of_order_superseded_result": {
        "required_obligations": {"classify_stale", "exclude_stale", "verify_closure"},
        "mutation_families": {"accept_stale", "rollback_to_stale", "mix_lineages"},
    },
    "partial_then_complete_result": {
        "required_obligations": {"classify_completeness", "revise_affected", "verify_closure"},
        "mutation_families": {"treat_partial_as_final", "drop_confirmed_partial", "skip_reverification"},
    },
    "conflicting_valid_results": {
        "required_obligations": {"classify_conflict", "arbitrate_conflict", "verify_closure"},
        "mutation_families": {"blind_first_result", "blind_last_result", "inconsistent_merge"},
    },
    "duplicate_or_replayed_completion": {
        "required_obligations": {"classify_duplicate", "preserve_idempotency"},
        "mutation_families": {"double_consume", "duplicate_side_effect", "unnecessary_recompute"},
    },
    "child_failure_or_implicit_error": {
        "required_obligations": {"classify_failure", "recover_or_redelegate", "verify_closure"},
        "mutation_families": {"promote_failed_result", "omit_recovery", "false_success"},
    },
    "task_scope_or_dependency_change": {
        "required_obligations": {"classify_scope_delta", "revise_affected", "preserve_unaffected", "verify_closure"},
        "mutation_families": {
            "under_invalidate", "over_invalidate", "ignore_new_requirement",
            "skip_reverification",
        },
    },
    "straggler_under_resource_pressure": {
        "required_obligations": {"classify_critical_path", "resource_triage", "verify_closure"},
        "mutation_families": {"wait_for_low_value_straggler", "cancel_critical_work", "exceed_budget"},
    },
}


def validate_event_policy_binding(theme: str, obligations: set[str]) -> list[str]:
    policy = EVENT_POLICIES.get(theme)
    if policy is None:
        return [f"unknown primary event theme {theme!r}"]
    missing = sorted(set(policy["required_obligations"]) - obligations)
    return [
        f"event theme {theme!r} lacks required causal obligations {missing!r}"
    ] if missing else []
