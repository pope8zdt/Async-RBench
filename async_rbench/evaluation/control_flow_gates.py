"""Evaluator-observed control-flow test points.

Control-flow points are registered per case and execution mode, and the
registry's ``execution_modes`` list is the only source of applicability: every
point registered for an episode's mode is applicable, so all models under the
same mode share the same X denominator. A registered point whose trace
preconditions are absent fails the gate (model inaction = fail); it is never
``not_applicable`` at the trace level. Only a point not registered for the
mode, or whose gate has no evaluator, is ``not_applicable`` and excluded
from the denominator.

Control-flow points pass on evaluator-observed process evidence.  Their local
semantic anchors are reported separately for causal diagnosis; current V9.1
registries do not use those anchors to double-penalise the dynamic component.
Historical registries that explicitly set ``requires_outcome_anchor`` remain
readable for reproducibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .weighting import (
    DYNAMIC_COMPONENT_MASS,
    DYNAMIC_CONTROL_DIMENSIONS,
    DYNAMIC_SUCCESS_THRESHOLD,
    GATE_DYNAMIC_DIMENSIONS,
    SEMANTIC_COMPONENT_MASS,
    control_flow_weight, semantic_weight,
    semantic_weight_map,
)

GATE_NAMES = (
    "wait_for_authority", "reject_late_stale", "resolve_authority",
    "timely_cancellation", "selective_replan", "rederive_from_authority",
    "deduplicate_completion", "recover_failed_work", "arbitrate_conflict",
    "resource_triage",
)
GATE_EXECUTION_MODES = {
    "wait_for_authority": frozenset({"async"}),
    "reject_late_stale": frozenset({"async"}),
    "resolve_authority": frozenset({"async"}),
    "timely_cancellation": frozenset({"async"}),
    "selective_replan": frozenset({"async"}),
    "rederive_from_authority": frozenset({"async"}),
    "deduplicate_completion": frozenset({"async"}),
    "recover_failed_work": frozenset({"async"}),
    "arbitrate_conflict": frozenset({"async"}),
    "resource_triage": frozenset({"async"}),
}


def _artifacts(check: dict[str, Any]) -> list[str]:
    return [str(item) for item in (check.get("gate_args") or {}).get("artifacts") or []]


def _wait(check: dict[str, Any], facts: dict[str, Any]) -> tuple[bool, list[str]]:
    authority = facts.get("authoritative_delivery")
    if authority is None:
        return False, ["no authoritative delivery"]
    authority_id = str(authority.get("completion_id"))
    strict = check.get("requires_outcome_anchor") is True
    consumption = facts.get("consumption_by_completion_id", {}).get(authority_id)
    if strict and consumption is None:
        return False, ["authoritative completion was never consumed"]
    if not strict and authority_id not in facts.get("consumed_completion_ids", set()):
        return False, ["authoritative completion was never consumed"]
    for artifact_id in _artifacts(check):
        commits = facts.get("artifact_commits", {}).get(artifact_id, [])
        final = facts.get("final_artifacts", {}).get(artifact_id)
        if final is None:
            return False, [f"{artifact_id}: no final evaluator-observed commit"]
        if strict:
            if int(final.get("seq", 0)) <= int(consumption.get("seq", 0)):
                return False, [f"{artifact_id}: final commit did not follow authority consumption"]
        elif any(int(item.get("seq", 0)) <= int(authority.get("seq", 0)) for item in commits):
            return False, [f"{artifact_id}: committed before authoritative delivery"]
        if authority_id not in set(final.get("lineage_completion_ids", [])):
            return False, [f"{artifact_id}: final lineage omits authoritative completion"]
    return True, []


def _reject_stale(check: dict[str, Any], facts: dict[str, Any]) -> tuple[bool, list[str]]:
    strict = check.get("requires_outcome_anchor") is True
    required = set(facts.get("stale_required_completion_ids", set()))
    if strict and not required:
        return False, ["no evaluator-proven stale completion existed"]
    retained = set(facts.get("stale_retained_completion_ids", set()))
    for artifact_id in _artifacts(check):
        final = facts.get("final_artifacts", {}).get(artifact_id)
        if final is None:
            return False, [f"{artifact_id}: no final evaluator-observed commit"]
        forbidden = required if strict else retained
        if set(final.get("lineage_completion_ids", [])) & forbidden:
            return False, [f"{artifact_id}: final lineage retains a stale completion"]
    return True, []


def _cancel(check: dict[str, Any], facts: dict[str, Any]) -> tuple[bool, list[str]]:
    workstreams = {str(item) for item in (check.get("gate_args") or {}).get("workstreams") or []}
    spawned = facts.get("spawned_by_id", {})
    opportunity = set(facts.get("cancellation_opportunity_children", set()))
    children = {
        child_id for child_id in opportunity
        if workstreams & {str(item) for item in spawned.get(child_id, {}).get("work_units") or []}
    }
    if not children:
        return False, ["no progressed superseded child created the required cancellation opportunity"]
    missing = children - set(facts.get("timely_cancelled_children", set()))
    if missing:
        return False, ["superseded running child was not cancelled by main agent"]
    if int(facts.get("unnecessary_cancellation_count", 0)) > 0:
        return False, ["cancelled a child that was not a cancellation opportunity"]
    return True, []


def _resolve_authority(
    check: dict[str, Any], facts: dict[str, Any],
) -> tuple[bool, list[str]]:
    authority = facts.get("authoritative_delivery")
    if authority is None:
        return False, ["no authoritative delivery"]
    authority_id = str(authority.get("completion_id"))
    strict = check.get("requires_outcome_anchor") is True
    consumption = facts.get("consumption_by_completion_id", {}).get(authority_id)
    if strict and consumption is None:
        return False, ["authoritative completion was never consumed"]
    if not strict and authority_id not in facts.get("consumed_completion_ids", set()):
        return False, ["authoritative completion was never consumed"]
    for artifact_id in _artifacts(check):
        commits = facts.get("artifact_commits", {}).get(artifact_id, [])
        if strict and not any(int(item.get("seq", 0)) < int(authority.get("seq", 0)) for item in commits):
            return False, [f"{artifact_id}: no provisional pre-authority state was observed"]
        final = facts.get("final_artifacts", {}).get(artifact_id)
        if final is None:
            return False, [f"{artifact_id}: no final evaluator-observed commit"]
        if int(final.get("seq", 0)) <= int(authority.get("seq", 0)):
            return False, [f"{artifact_id}: final commit predates authority"]
        if strict and int(final.get("seq", 0)) <= int(consumption.get("seq", 0)):
            return False, [f"{artifact_id}: revised state predates authority consumption"]
        if authority_id not in set(final.get("lineage_completion_ids", [])):
            return False, [f"{artifact_id}: final lineage omits authoritative completion"]
    return True, []


def _selective_replan(
    check: dict[str, Any], facts: dict[str, Any],
) -> tuple[bool, list[str]]:
    args = check.get("gate_args") or {}
    strict = check.get("requires_outcome_anchor") is True
    affected = [str(item) for item in args.get("artifacts") or []]
    invalidations = facts.get("invalidating_deliveries", [])
    for artifact_id in affected:
        relevant = [
            item for item in invalidations
            if artifact_id in {
                str(value) for value in item.get("invalidates_artifacts") or []
            }
        ]
        if not relevant:
            return False, [f"{artifact_id}: no evaluator-declared invalidation"]
        invalidated_at = max(int(item.get("seq", 0)) for item in relevant)
        commits = facts.get("artifact_commits", {}).get(artifact_id, [])
        if strict and not any(int(item.get("seq", 0)) < invalidated_at for item in commits):
            return False, [f"{artifact_id}: no pre-invalidation state existed to replan"]
        final = facts.get("final_artifacts", {}).get(artifact_id)
        if final is None or int(final.get("seq", 0)) <= invalidated_at:
            return False, [f"{artifact_id}: was not recommitted after invalidation"]
    preserve = [str(item) for item in args.get("preserve_artifacts") or []]
    boundary_events = [
        item for item in invalidations
        if set(map(str, item.get("invalidates_artifacts") or [])) & set(affected)
    ]
    if boundary_events:
        boundary = max(int(item.get("seq", 0)) for item in boundary_events)
        for artifact_id in preserve:
            commits = facts.get("artifact_commits", {}).get(artifact_id, [])
            existed_before_boundary = any(
                int(commit.get("seq", 0)) <= boundary for commit in commits
            )
            recommitted_after_boundary = any(
                int(commit.get("seq", 0)) > boundary for commit in commits
            )
            if strict and not existed_before_boundary:
                return False, [
                    f"{artifact_id}: unaffected artifact had no pre-event state to preserve"
                ]
            if recommitted_after_boundary:
                return False, [
                    f"{artifact_id}: unaffected artifact was unnecessarily recommitted"
                ]
    return True, []


def _rederive(check: dict[str, Any], facts: dict[str, Any]) -> tuple[bool, list[str]]:
    authority = facts.get("authoritative_delivery")
    if authority is None:
        return False, ["no authoritative delivery"]
    authority_id = str(authority.get("completion_id"))
    if check.get("requires_outcome_anchor") is True and not facts.get("post_authority_verification"):
        return False, ["no evaluator-observed post-authority verification request"]
    invalidating: dict[str, list[dict[str, Any]]] = {}
    for delivery in facts.get("invalidating_deliveries", []):
        for artifact_id in delivery.get("invalidates_artifacts", []):
            invalidating.setdefault(str(artifact_id), []).append(delivery)
    for artifact_id in _artifacts(check):
        final = facts.get("final_artifacts", {}).get(artifact_id)
        if final is None:
            return False, [f"{artifact_id}: no final evaluator-observed commit"]
        if authority_id not in set(final.get("lineage_completion_ids", [])):
            return False, [f"{artifact_id}: final lineage omits authoritative completion"]
        if any(int(final.get("seq", 0)) <= int(item.get("seq", 0)) for item in invalidating.get(artifact_id, [])):
            return False, [f"{artifact_id}: final commit predates invalidating delivery"]
    return True, []


def _deduplicate(check: dict[str, Any], facts: dict[str, Any]) -> tuple[bool, list[str]]:
    replays = list(facts.get("replayed_deliveries") or [])
    if not replays:
        return False, ["no evaluator-observed completion replay"]
    first_replay_seq = min(int(item.get("seq", 0)) for item in replays)
    for artifact_id in _artifacts(check):
        if any(
            int(item.get("seq", 0)) > first_replay_seq
            for item in facts.get("artifact_commits", {}).get(artifact_id, [])
        ):
            return False, [f"{artifact_id}: recommitted after a duplicate completion"]
    if int(facts.get("duplicate_side_effect_count", 0)) > 0:
        return False, ["duplicate completion caused a repeated side effect"]
    return True, []


def _recover_failed(check: dict[str, Any], facts: dict[str, Any]) -> tuple[bool, list[str]]:
    failed = set(facts.get("failed_workstreams") or set())
    required = set(map(str, (check.get("gate_args") or {}).get("workstreams") or []))
    targets = failed & required if required else failed
    if not targets:
        return False, ["no evaluator-observed failed workstream matched the recovery point"]
    recovered = set(facts.get("recovered_workstreams") or set())
    missing = targets - recovered
    if missing:
        return False, [f"failed workstreams were not usefully recovered: {sorted(missing)!r}"]
    return True, []


def _arbitrate_conflict(check: dict[str, Any], facts: dict[str, Any]) -> tuple[bool, list[str]]:
    args = check.get("gate_args") or {}
    accepted = set(map(str, args.get("accepted_completion_ids") or []))
    rejected = set(map(str, args.get("rejected_completion_ids") or []))
    by_kind = facts.get("delivery_completion_ids_by_kind") or {}
    for kind in args.get("accepted_result_kinds") or []:
        accepted.update(map(str, by_kind.get(str(kind), set())))
    for kind in args.get("rejected_result_kinds") or []:
        rejected.update(map(str, by_kind.get(str(kind), set())))
    if not accepted:
        authority = facts.get("authoritative_delivery") or {}
        if authority.get("completion_id"):
            accepted.add(str(authority["completion_id"]))
    if not rejected:
        rejected = set(facts.get("conflicting_completion_ids") or set()) - accepted
    if not accepted or not rejected:
        return False, ["conflict policy has no evaluator-proven accepted/rejected alternatives"]
    for artifact_id in _artifacts(check):
        final = facts.get("final_artifacts", {}).get(artifact_id)
        if final is None:
            return False, [f"{artifact_id}: no final evaluator-observed commit"]
        lineage = set(map(str, final.get("lineage_completion_ids") or []))
        if not accepted <= lineage or lineage & rejected:
            return False, [f"{artifact_id}: final lineage does not implement the arbitration rule"]
    return True, []


def _resource_triage(check: dict[str, Any], facts: dict[str, Any]) -> tuple[bool, list[str]]:
    args = check.get("gate_args") or {}
    cancel_units = set(map(str, args.get("cancel_workstreams") or []))
    preserve_units = set(map(str, args.get("preserve_workstreams") or []))
    cancelled = set(facts.get("cancelled_workstreams") or set())
    if cancel_units and not cancel_units <= cancelled:
        return False, [f"resource triage did not cancel {sorted(cancel_units - cancelled)!r}"]
    if preserve_units & cancelled:
        return False, [f"resource triage cancelled critical work {sorted(preserve_units & cancelled)!r}"]
    if facts.get("resource_limit_exceeded") is True:
        return False, ["participant exceeded the evaluator-owned resource limit"]
    return True, []


_EVALUATORS = {
    "wait_for_authority": _wait,
    "reject_late_stale": _reject_stale,
    "resolve_authority": _resolve_authority,
    "timely_cancellation": _cancel,
    "selective_replan": _selective_replan,
    "rederive_from_authority": _rederive,
    "deduplicate_completion": _deduplicate,
    "recover_failed_work": _recover_failed,
    "arbitrate_conflict": _arbitrate_conflict,
    "resource_triage": _resource_triage,
}


def evaluate_control_flow_checks(
    registry_checks: list[dict[str, Any]], execution_mode: str,
    facts: dict[str, Any], semantic_results: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    semantic_by_id = {str(item.get("id")): item for item in (semantic_results or [])}
    results: list[dict[str, Any]] = []
    for check in registry_checks:
        check_id = str(check.get("id", ""))
        gate = str(check.get("gate", ""))
        entry: dict[str, Any] = {
            "id": check_id, "gate": gate,
            "dimension": str(
                check.get("dimension") or GATE_DYNAMIC_DIMENSIONS.get(gate, "")
            ),
            "measurement_type": str(check.get("measurement_type", "control")),
            "capability_target": str(check.get("capability_target", "")),
            "relevance_tier": str(check.get("relevance_tier", "")),
            "registered_execution_modes": list(check.get("execution_modes") or []),
            "critical": bool(check.get("critical")), "status": "not_applicable",
            "decision_group": str(check.get("decision_group") or ""),
            "task_requirement_id": str(check.get("task_requirement_id") or ""),
            "obligation": str(check.get("obligation") or ""),
            "anchor_passed": None, "gate_passed": None,
            "process_status": "not_applicable", "reasons": [],
        }
        if execution_mode not in entry["registered_execution_modes"]:
            entry["reasons"].append(
                f"not registered for execution mode {execution_mode}"
            )
            results.append(entry)
            continue
        # Registry-decided applicability: a point registered for the mode
        # is always applicable. The gate evaluators treat an absent trace
        # precondition as a FAIL (model inaction = fail, never not_applicable),
        # keeping the applicable-point set — and thus the X denominator —
        # identical for every model under the same mode.
        if gate not in _EVALUATORS:
            entry["reasons"].append(f"no evaluator for gate {gate}")
            results.append(entry)
            continue
        # V6/V7 points use their local outcome anchor as part of the effective
        # decision score. Legacy points remain process-only for reproducibility.
        anchors = [str(item) for item in (check.get("outcome_anchors") or [])]
        missing = [item for item in anchors if item not in semantic_by_id]
        anchor_passed = bool(anchors) and not missing and all(
            semantic_by_id[item].get("passed") is True for item in anchors
        )
        reasons = [f"anchor(s) missing from verifier results: {missing}"] if missing else []
        gate_passed, gate_reasons = _EVALUATORS[gate](check, facts)
        reasons.extend(gate_reasons)
        process_status = "pass" if gate_passed else "fail"
        requires_anchor = check.get("requires_outcome_anchor") is True
        effective_passed = gate_passed and (anchor_passed or not requires_anchor)
        if requires_anchor and not anchor_passed:
            reasons.append("local outcome anchor did not pass")
        entry.update({
            "anchor_passed": anchor_passed, "gate_passed": gate_passed,
            "process_status": process_status,
            "reasons": reasons,
            "status": "pass" if effective_passed else "fail",
        })
        results.append(entry)
    counts = {
        "total": len(results),
        "applicable": sum(item["status"] != "not_applicable" for item in results),
        "passed": sum(item["status"] == "pass" for item in results),
        "failed": sum(item["status"] == "fail" for item in results),
        "not_applicable": sum(item["status"] == "not_applicable" for item in results),
    }
    return results, counts


def semantic_task_score(
    semantic_results: list[dict[str, Any]] | None,
    verifier_rate: float | None,
    semantic_registry: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> float | None:
    """Return the unchanged verifier outcome score as an independent component."""
    if not semantic_results:
        return verifier_rate
    checks = (
        semantic_registry.get("checks")
        if isinstance(semantic_registry, dict) else semantic_registry
    ) or []
    by_id = {str(item.get("id")): item for item in checks if isinstance(item, dict)}
    if any(item.get("requirement_group") for item in by_id.values()):
        grouped: dict[str, list[dict[str, Any]]] = {}
        for result in semantic_results:
            spec = by_id.get(str(result.get("id")), {})
            group = str(spec.get("requirement_group") or spec.get("id") or result.get("id"))
            grouped.setdefault(group, []).append({**spec, **result})
        rates = []
        for items in grouped.values():
            total = sum(semantic_weight(item) for item in items)
            passed = sum(semantic_weight(item) for item in items if item.get("passed") is True)
            rates.append(passed / total if total else 0.0)
        return sum(rates) / len(rates) if rates else verifier_rate
    weights = semantic_weight_map(semantic_registry)
    passed = sum(
        weights.get(str(item.get("id")), 1)
        for item in semantic_results if item.get("passed") is True
    )
    total = sum(weights.get(str(item.get("id")), 1) for item in semantic_results)
    return passed / total if total else verifier_rate


def dynamic_dimension_scores(
    control_flow_results: list[dict[str, Any]],
) -> dict[str, float]:
    """Macro-ready per-dimension rates over the registry-fixed applicable set."""
    grouped: dict[str, list[dict[str, Any]]] = {
        dimension: [] for dimension in DYNAMIC_CONTROL_DIMENSIONS
    }
    for item in control_flow_results:
        if item.get("status") == "not_applicable":
            continue
        dimension = str(
            item.get("dimension")
            or GATE_DYNAMIC_DIMENSIONS.get(str(item.get("gate") or ""), "")
        )
        if dimension in grouped:
            grouped[dimension].append(item)
    result: dict[str, float] = {}
    for dimension, items in grouped.items():
        if not items:
            continue
        total = sum(control_flow_weight(item) for item in items)
        passed = sum(
            control_flow_weight(item)
            for item in items if item.get("status") == "pass"
        )
        result[dimension] = passed / total if total else 0.0
    return result


def dynamic_decision_group_scores(
    control_flow_results: list[dict[str, Any]],
) -> dict[str, float]:
    """Per-obligation diagnostics for V7 task-causal registries."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in control_flow_results:
        if item.get("status") == "not_applicable":
            continue
        group = str(item.get("decision_group") or "")
        if group:
            grouped.setdefault(group, []).append(item)
    result: dict[str, float] = {}
    for group, items in grouped.items():
        total = sum(control_flow_weight(item) for item in items)
        passed = sum(
            control_flow_weight(item) for item in items if item.get("status") == "pass"
        )
        result[group] = passed / total if total else 0.0
    return result


def dynamic_control_score(
    control_flow_results: list[dict[str, Any]],
) -> float | None:
    """Primary benchmark score: equal-mass macro over dynamic decision stages."""
    applicable = [item for item in control_flow_results if item.get("status") != "not_applicable"]
    if any(item.get("decision_group") for item in applicable):
        scores = dynamic_decision_group_scores(applicable)
        rates = list(scores.values())
        return sum(rates) / len(rates) if rates else None
    scores = dynamic_dimension_scores(control_flow_results)
    return sum(scores.values()) / len(scores) if scores else None


def dynamic_process_score(
    control_flow_results: list[dict[str, Any]],
) -> float | None:
    """Diagnostic process-only macro, before local outcome anchoring."""
    grouped: dict[str, list[dict[str, Any]]] = {
        dimension: [] for dimension in DYNAMIC_CONTROL_DIMENSIONS
    }
    for item in control_flow_results:
        if item.get("process_status") == "not_applicable":
            continue
        dimension = str(
            item.get("dimension")
            or GATE_DYNAMIC_DIMENSIONS.get(str(item.get("gate") or ""), "")
        )
        if dimension in grouped:
            grouped[dimension].append(item)
    rates: list[float] = []
    for items in grouped.values():
        if not items:
            continue
        total = sum(control_flow_weight(item) for item in items)
        passed = sum(
            control_flow_weight(item)
            for item in items if item.get("process_status") == "pass"
        )
        rates.append(passed / total if total else 0.0)
    return sum(rates) / len(rates) if rates else None


def critical_dynamic_success(
    control_flow_results: list[dict[str, Any]],
) -> bool | None:
    critical = [
        item for item in control_flow_results
        if item.get("status") != "not_applicable" and item.get("critical") is True
    ]
    return all(item.get("status") == "pass" for item in critical) if critical else None


def combine_dt_score(
    dynamic_score: float | None, semantic_score: float | None,
) -> float | None:
    """Secondary 80/20 summary; semantic quality can contribute at most 20%."""
    if dynamic_score is None or semantic_score is None:
        return None
    return DYNAMIC_COMPONENT_MASS * dynamic_score + SEMANTIC_COMPONENT_MASS * semantic_score


def dynamic_success(
    dynamic_score: float | None, critical_success: bool | None,
) -> bool | None:
    if dynamic_score is None:
        return None
    return bool(critical_success is True and dynamic_score >= DYNAMIC_SUCCESS_THRESHOLD)


def merge_test_point_pass_rate(
    semantic_results: list[dict[str, Any]] | None,
    verifier_rate: float | None,
    control_flow_results: list[dict[str, Any]],
    semantic_registry: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> float | None:
    """Compatibility scalar: semantic baseline for linear, v9 DTScore for async.

    New consumers must use ``dynamic_control_score`` as the primary async
    metric and display ``semantic_task_score`` independently.
    """
    semantic_score = semantic_task_score(
        semantic_results, verifier_rate, semantic_registry,
    )
    dynamic_score = dynamic_control_score(control_flow_results)
    return combine_dt_score(dynamic_score, semantic_score) if dynamic_score is not None else semantic_score


# ---------------------------------------------------------------------------
# Observation-point scoring (spec 9): separate Base Task Score from the
# per-event Dynamic Replanning Score.
#
# A semantic check is tagged with exactly one ``score_domain``:
#   ``base_task``          -> feeds Linear/Async BTS.
#   ``async_replanning``   -> does NOT feed BTS; feeds only its event's
#                             AsyncOutcome, and must bind a real ``event_id``.
# ``relevance_tier`` is removed as a scoring gate in the new contract version.
# ---------------------------------------------------------------------------

# ``score_domain`` enum and ``expected_disposition`` interpretation live with
# the contract layer (``case_contract.SCORE_DOMAINS``); here we only route a
# component by a contract's declared applicability, treating ``expected_disposition``
# as an opaque diagnostic string.

COMPONENT_ORDER = (
    "required_effect_coverage",
    "preservation",
    "forbidden_effect_compliance",
    "closure",
)


# Spec 9.2 blend: an event DRS is an equal mix of its process score and its
# async-outcome score, regardless of disposition.
PROCESS_BLEND_WEIGHT = 0.5


@dataclass
class EventDRS:
    """A single event's Dynamic Replanning Score with component attribution.

    ``total`` is the event DRS: ``PROCESS_BLEND_WEIGHT * process_score
    + (1 - PROCESS_BLEND_WEIGHT) * async_outcome``, i.e. a 0.5/0.5 mix.
    When the event is unscored (infrastructure/case failure) ``total`` is None.
    """

    process_score: float | None
    async_outcome: float | None
    component_scores: dict[str, float | None]
    expected_disposition: str = ""
    applicability: dict[str, bool] = field(default_factory=dict)
    status: str = "scored"

    @property
    def total(self) -> float | None:
        if self.status != "scored" or self.process_score is None or self.async_outcome is None:
            return None
        return PROCESS_BLEND_WEIGHT * self.process_score + (
            1 - PROCESS_BLEND_WEIGHT
        ) * self.async_outcome


def _state_token(state: Any, artifact_id: str) -> Any:
    """Return the comparable state token for an artifact in a before/after snapshot.

    ``state`` may be a flat ``{artifact_id: digest}`` mapping, a mapping with an
    ``artifacts`` sub-mapping, or a scalar (meaning every artifact shares it).
    """
    if state is None:
        return None
    if isinstance(state, dict):
        # A top-level key wins over the ``artifacts`` sub-mapping.
        if artifact_id in state:
            return state[artifact_id]
        artifacts = state.get("artifacts")
        if isinstance(artifacts, dict) and artifact_id in artifacts:
            return artifacts[artifact_id]
        return None
    return state


def _required_effect_coverage(
    contract: dict[str, Any], before: Any, after: Any,
) -> float | None:
    required = [str(item) for item in (contract.get("required_changes") or [])]
    if not required:
        return None
    changed = sum(
        1 for artifact_id in required
        if _state_token(before, artifact_id) != _state_token(after, artifact_id)
    )
    return changed / len(required)


def _preservation_score(
    contract: dict[str, Any], before: Any, after: Any,
) -> float | None:
    preserved = [str(item) for item in (contract.get("required_preservation") or [])]
    if not preserved:
        return None
    consistent = sum(
        1 for artifact_id in preserved
        if _state_token(before, artifact_id) == _state_token(after, artifact_id)
    )
    return consistent / len(preserved)


def _forbidden_effect_compliance(
    contract: dict[str, Any], before: Any, after: Any,
) -> float | None:
    forbidden = [str(item) for item in (contract.get("forbidden_changes") or [])]
    if not forbidden:
        return None
    compliant = sum(
        1 for artifact_id in forbidden
        # A forbidden artifact must remain unchanged: a change is a violation.
        if _state_token(before, artifact_id) == _state_token(after, artifact_id)
    )
    return compliant / len(forbidden)


def _closure_score(
    contract: dict[str, Any], semantic_results: list[dict[str, Any]] | None,
) -> float | None:
    checks = [
        str(item)
        for item in (contract.get("closure_checks") or contract.get("required_verification") or [])
    ]
    if not checks:
        return None
    by_id = {str(item.get("id")): item for item in (semantic_results or [])}
    passed = sum(1 for check_id in checks if by_id.get(check_id, {}).get("passed") is True)
    return passed / len(checks)


def _component_applicability(contract: dict[str, Any]) -> set[str]:
    """Route components by the contract's declared applicability, not trajectory.

    A contract may declare ``applicable_components`` explicitly; otherwise the
    presence of a component's declared source list routes it.  An empty required
    change set makes RequiredEffectCoverage inapplicable, so a participant cannot
    dodge a denominator by inaction (and a no-replan event cannot be penalised).
    """
    declared = contract.get("applicable_components")
    if declared is not None:
        return set(str(item) for item in declared)
    applicable = set()
    if contract.get("required_changes"):
        applicable.add("required_effect_coverage")
    if contract.get("required_preservation"):
        applicable.add("preservation")
    if contract.get("forbidden_changes"):
        applicable.add("forbidden_effect_compliance")
    if contract.get("closure_checks") or contract.get("required_verification"):
        applicable.add("closure")
    return applicable


def _event_async_outcome(
    event_id: str | None, semantic_results: list[dict[str, Any]] | None,
) -> float | None:
    checks = [
        item for item in (semantic_results or [])
        if item.get("score_domain") == "async_replanning"
        and str(item.get("event_id")) == str(event_id)
    ]
    if not checks:
        return None
    passed = sum(1 for item in checks if item.get("passed") is True)
    return passed / len(checks)


def _provisional_missing(contract: dict[str, Any], before: Any) -> bool:
    """Spec 9.4: participant failed to create a required provisional state."""
    if contract.get("requires_provisional") is not True:
        return False
    if before is None:
        return True
    artifact = contract.get("provisional_artifact")
    if artifact is not None:
        return _state_token(before, str(artifact)) is None
    return False


def _component_value(
    name: str, contract: dict[str, Any], before: Any, after: Any,
    semantic_results: list[dict[str, Any]] | None,
) -> float | None:
    if name == "required_effect_coverage":
        return _required_effect_coverage(contract, before, after)
    if name == "preservation":
        return _preservation_score(contract, before, after)
    if name == "forbidden_effect_compliance":
        return _forbidden_effect_compliance(contract, before, after)
    if name == "closure":
        return _closure_score(contract, semantic_results)
    return None


def score_base_task(
    semantic_results: list[dict[str, Any]] | None,
) -> float | None:
    """Base Task Score: fraction of ``score_domain == base_task`` checks passing."""
    checks = [
        item for item in (semantic_results or [])
        if item.get("score_domain") == "base_task"
    ]
    if not checks:
        return None
    passed = sum(1 for item in checks if item.get("passed") is True)
    return passed / len(checks)


def score_event_replanning(
    contract: dict[str, Any] | None,
    before: Any,
    after: Any,
    semantic_results: list[dict[str, Any]] | None,
) -> EventDRS:
    """Score a single event's replanning (DRS).

    ``before`` / ``after`` are state snapshots around the event boundary.  The
    contract declares, in advance, the required/preserved/forbidden artifacts and
    the event's closure checks; applicability is declared, never inferred from
    the trajectory.
    """
    contract = dict(contract or {})
    disposition = str(contract.get("expected_disposition") or "")
    status = str(contract.get("event_status") or "scored")
    empty_components = {name: None for name in COMPONENT_ORDER}

    # Evaluator inability to produce/present the declared event is an
    # infrastructure/case failure, not a model score (spec 9.4).
    if status != "scored":
        return EventDRS(
            process_score=None,
            async_outcome=None,
            component_scores=empty_components,
            expected_disposition=disposition,
            applicability={name: False for name in COMPONENT_ORDER},
            status=status,
        )

    applicability = _component_applicability(contract)
    component_scores = {
        name: _component_value(name, contract, before, after, semantic_results)
        for name in COMPONENT_ORDER
    }
    applicable = {name: name in applicability for name in COMPONENT_ORDER}

    # Spec 9.4: participant failure to create the required provisional within
    # the full pre budget yields a related DRS of 0.
    if _provisional_missing(contract, before):
        return EventDRS(
            process_score=0.0,
            async_outcome=0.0,
            component_scores=component_scores,
            expected_disposition=disposition,
            applicability=applicable,
            status="scored",
        )

    applicable_values = [
        component_scores[name] for name in COMPONENT_ORDER
        if name in applicability and component_scores[name] is not None
    ]
    process_score = (
        sum(applicable_values) / len(applicable_values) if applicable_values else None
    )
    async_outcome = _event_async_outcome(contract.get("event_id"), semantic_results)
    return EventDRS(
        process_score=process_score,
        async_outcome=async_outcome,
        component_scores=component_scores,
        expected_disposition=disposition,
        applicability=applicable,
        status="scored",
    )


def score_async_drs(
    event_scores: list[EventDRS] | None,
) -> float | None:
    """Aggregate per-event DRS: mean over scored events, ignoring unscored ones."""
    totals = [item.total for item in (event_scores or []) if item.total is not None]
    return sum(totals) / len(totals) if totals else None
