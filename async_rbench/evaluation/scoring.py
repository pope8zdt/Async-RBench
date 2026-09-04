from __future__ import annotations

from collections import defaultdict
from typing import Any

from .protocol import canonical_digest
from .pytest_results import parse_pytest_summary
from .event_store import _KERNEL_PRIVATE_FIELDS
from .termination import (
    GATEWAY_ACCEPTED,
    NO_SUBMISSION,
    PUBLIC_REJECTION,
    RESOURCE_SAFETY_ABORT,
    SEALED_PENDING_VERDICT,
    STEP_LIMIT_REACHED,
    TERMINAL_CLASSES,
    classify_child_terminals,
)
from .control_flow_gates import (
    EventDRS,
    _provisional_missing,
    combine_dt_score,
    critical_dynamic_success,
    dynamic_control_score,
    dynamic_dimension_scores, dynamic_decision_group_scores,
    dynamic_process_score,
    dynamic_success,
    evaluate_control_flow_checks,
    score_async_drs,
    score_base_task,
    score_event_replanning,
    semantic_task_score,
)
from .weighting import (
    SCORE_POLICY_VERSION, control_flow_weight, semantic_weight_map,
)


def _events_of(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [event for event in events if event.get("type") == event_type]


def _extra_tokens_from_public_rejections(
    rows: list[dict[str, Any]],
) -> int:
    """Task 8 P1-19 cost-of-rejection over *public* rejections only.

    Per workstream, extra child tokens are what the workstream spent on
    ``public_rejection`` attempts *beyond* the accepted one: the public-rejected
    attempts that precede the gateway-accepted attempt, or every public-rejected
    attempt when none was accepted.  Sealed-without-verdict attempts are not
    public rejections and private-only (case-contract) rejections are benchmark
    errors, so neither contributes.
    """
    attempt_rows_by_workstream: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        attempt_rows_by_workstream[str(row.get("workstream_id") or "no_workstream")].append(row)
    extra = 0
    for attempt_rows in attempt_rows_by_workstream.values():
        ordered = sorted(attempt_rows, key=lambda row: int(row["attempt_number"]))
        accepted_index = next(
            (index for index, row in enumerate(ordered)
             if row["terminal_class"] == GATEWAY_ACCEPTED), None,
        )
        rejected_up_to = (
            [row for row in ordered[:accepted_index]
             if row["terminal_class"] == PUBLIC_REJECTION]
            if accepted_index is not None
            else [row for row in ordered if row["terminal_class"] == PUBLIC_REJECTION]
        )
        extra += sum(int(row["tokens"]) for row in rejected_up_to)
    return extra


def _materialize_private_delivery_facts(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Join private delivery truth only inside the scorer.

    Persisted public ``result_delivered`` records intentionally lack semantic
    roles, staleness and invalidation instructions. The scorer reconstructs its
    evaluator view by completion id without mutating the participant trace.
    """
    delivery_facts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("type") == "result_delivery_evaluator_fact":
            delivery_facts[str(event.get("completion_id"))].append(event)
    rejection_facts = {
        str(event.get("completion_id")): event
        for event in events
        if event.get("type") == "result_rejection_evaluator_fact"
    }
    result: list[dict[str, Any]] = []
    for event in events:
        event_type = event.get("type")
        if event_type not in {"result_delivered", "result_rejected"}:
            result.append(event)
            continue
        if event_type == "result_delivered":
            queued = delivery_facts.get(str(event.get("completion_id"))) or []
            fact = queued.pop(0) if queued else None
        else:
            fact = rejection_facts.get(str(event.get("completion_id")))
        if fact is None:
            result.append(event)
            continue
        merged = {
            **event,
            "result_kind": fact.get("result_kind"),
            "benchmark_event_id": fact.get("benchmark_event_id"),
            "controlled_order": fact.get("controlled_order"),
        }
        if event_type == "result_delivered":
            merged.update({
                "evaluator_stale": fact.get("stale"),
                "evaluator_stale_measurable": fact.get("stale_measurable"),
                "evaluator_stale_reason": fact.get("stale_reason"),
                "invalidates_artifacts": list(fact.get("invalidates_artifacts") or []),
                "reopens_milestones": list(fact.get("reopens_milestones") or []),
                "replayed": fact.get("replayed") is True,
                "replay_of_completion_id": fact.get("replay_of_completion_id"),
                # Task 9 designed-terminal private facts: the public record already
                # carries the observable ``terminal_outcome``; the design
                # classification and reason stay kernel-private and are re-joined
                # here for the P1-17 terminal classifier (never for the participant).
                "evaluator_designed_failure": fact.get("designed_failure"),
                "evaluator_terminal_reason": fact.get("terminal_reason"),
                "terminal_outcome": (
                    event.get("terminal_outcome") or fact.get("terminal_outcome")
                ),
            })
        else:
            merged["reason_codes"] = list(fact.get("reason_codes") or [])
        result.append(merged)
    return result


def _registry_checks(
    registry: dict[str, Any] | list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalise a registry into a list of checks (dict with ``checks`` or a list)."""
    if isinstance(registry, dict):
        checks = registry.get("checks")
        return list(checks) if isinstance(checks, list) else []
    if isinstance(registry, list):
        return list(registry)
    return []


def _last_by(events: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result = {}
    for event in events:
        result[str(event[key])] = event
    return result


def _weighted_semantic_counts(
    semantic_results: list[dict[str, Any]] | None,
    semantic_registry: dict[str, Any] | list[dict[str, Any]] | None,
) -> dict[str, int] | None:
    if semantic_results is None:
        return None
    weight_map = semantic_weight_map(semantic_registry)
    passed = 0
    failed = 0
    total = 0
    for item in semantic_results:
        weight = weight_map.get(str(item.get("id")), 1)
        total += weight
        if item.get("passed") is True:
            passed += weight
        else:
            failed += weight
    return {"passed": passed, "failed": failed, "total": total}


def _event_drs_to_dict(event_drs: Any) -> dict[str, Any]:
    """Project an ``EventDRS`` to a JSON-serialisable diagnostic record."""
    return {
        "process_score": event_drs.process_score,
        "async_outcome": event_drs.async_outcome,
        "component_scores": dict(event_drs.component_scores),
        "expected_disposition": event_drs.expected_disposition,
        "applicability": dict(event_drs.applicability),
        "status": event_drs.status,
        "total": event_drs.total,
    }


def _contract_carries_scoring_fields(contract: dict[str, Any]) -> bool:
    """True when an event contract declares the new observation-point scoring fields."""
    return bool(
        contract.get("required_changes") or contract.get("required_preservation")
        or contract.get("forbidden_changes") or contract.get("closure_checks")
        or contract.get("required_verification") or contract.get("expected_disposition")
        or contract.get("applicable_components") or contract.get("requires_provisional")
        or contract.get("event_status")
    )


def _event_state_snapshots(
    artifact_commits: dict[str, list[dict[str, Any]]],
    related_artifacts: set[str],
    boundary_seq: int,
) -> tuple[dict[str, str], dict[str, str]]:
    """Build before/after digest snapshots around an event's boundary."""
    before: dict[str, str] = {}
    after: dict[str, str] = {}
    for artifact_id in related_artifacts:
        commits = artifact_commits.get(str(artifact_id), [])
        pre = [item for item in commits if int(item.get("seq", 0)) < boundary_seq]
        post = [item for item in commits if int(item.get("seq", 0)) >= boundary_seq]
        if pre:
            before[artifact_id] = str(max(pre, key=lambda item: int(item.get("seq", 0))).get("observed_digest", ""))
        if post:
            after[artifact_id] = str(max(post, key=lambda item: int(item.get("seq", 0))).get("observed_digest", ""))
    return before, after


def _weighted_control_flow_counts(
    control_flow_results: list[dict[str, Any]] | None,
) -> dict[str, int] | None:
    if control_flow_results is None:
        return None
    passed = 0
    failed = 0
    applicable = 0
    total = 0
    for item in control_flow_results:
        weight = control_flow_weight(item)
        total += weight
        if item.get("status") == "not_applicable":
            continue
        applicable += weight
        if item.get("status") == "pass":
            passed += weight
        else:
            failed += weight
    return {
        "passed": passed,
        "failed": failed,
        "applicable": applicable,
        "not_applicable": total - applicable,
        "total": total,
    }


def score_trace(
    events: list[dict[str, Any]], case_spec: dict[str, Any], execution_mode: str,
    initial_completion_ids: set[str] | None = None,
    semantic_registry: dict[str, Any] | list[dict[str, Any]] | None = None,
    control_flow_checks: list[dict[str, Any]] | None = None,
    event_contracts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    events = _materialize_private_delivery_facts(events)
    protocol_valid = not _events_of(events, "protocol_violation")
    gateway_violation_count = sum(
        1 for event in _events_of(events, "protocol_violation") if event.get("gateway") is True
    )
    gateway_control_valid = not _events_of(events, "delegation_gate_fallback")
    # A hidden-truth field appearing on an event the *adapter* emitted means the
    # kernel-private evaluator state leaked across the boundary — the adapter
    # should never hold ``evaluator_stale*`` and thus never echo it back.
    visibility_leakage_detected = any(
        (event.get("actor") == "adapter" or event.get("source") == "adapter")
        and any(field in event for field in _KERNEL_PRIVATE_FIELDS)
        for event in events
    )
    spawned = {e["child_id"]: e for e in _events_of(events, "child_spawned") if e.get("parent_id") == "main"}
    delegation_validation_errors = _events_of(events, "delegation_validation_error")
    started = _last_by(_events_of(events, "child_started"), "child_id")
    completed = _last_by(_events_of(events, "child_completed"), "child_id")
    all_deliveries = _events_of(events, "result_delivered")
    replayed_deliveries = [event for event in all_deliveries if event.get("replayed") is True]
    deliveries = [event for event in all_deliveries if event.get("replayed") is not True]
    contract_rejections = _events_of(events, "result_rejected")
    gateway_outcomes = sorted(
        [*deliveries, *contract_rejections], key=lambda event: int(event.get("seq", 0))
    )
    delivery_by_child = _last_by(deliveries, "child_id")
    authoritative_kind = case_spec.get("authoritative_result_kind")
    authoritative_deliveries = [e for e in deliveries if e.get("result_kind") == authoritative_kind]
    authoritative_delivery = max(authoritative_deliveries, key=lambda event: event["seq"]) if authoritative_deliveries else None
    authoritative_rejections = [
        event for event in contract_rejections
        if event.get("result_kind") == authoritative_kind
    ]
    authoritative_rejection = (
        max(authoritative_rejections, key=lambda event: event["seq"])
        if authoritative_rejections else None
    )
    authoritative_outcomes = [*authoritative_deliveries, *authoritative_rejections]
    authoritative_outcome = (
        max(authoritative_outcomes, key=lambda event: event["seq"])
        if authoritative_outcomes else None
    )
    superseded_kind = case_spec.get("superseded_result_kind")

    # Scenario construction is a benchmark-execution audit: the automatic
    # initial wave started as designed. Model behaviour never changes
    # ``scenario_constructed``; only the
    # infrastructure failing to construct the scenario can make it false. The
    # old ``scenario_entry`` (below) is kept as a model-orchestration diagnostic.
    infrastructure_failure_events = _events_of(events, "infrastructure_failure")
    initial_wave_workstreams = {
        str(item.get("workstream_id"))
        for item in case_spec.get("initial_wave", [])
    }
    # Children tagged ``initial_wave=True`` are the benchmark-owned wave; a
    # recovery/replacement child for the same workstream is tagged False and
    # never counts toward the construction audit.
    initial_wave_children = {
        child_id for child_id, spawn in spawned.items()
        if spawn.get("initial_wave") is True
    }
    initial_wave_spawned_workstreams = {
        str(ws) for child_id in initial_wave_children
        for ws in (spawned[child_id].get("work_units") or [])
    }
    initial_wave_declared_as_designed = bool(
        initial_wave_workstreams
        and initial_wave_workstreams <= initial_wave_spawned_workstreams
    )
    initial_wave_started_as_designed = bool(
        initial_wave_declared_as_designed
        and (
            bool(initial_wave_children & set(started))
            if execution_mode == "linear"
            else initial_wave_children <= set(started)
        )
    )
    construction_failure_events = [
        event for event in infrastructure_failure_events
        if (
            event.get("component") in {
                "initial_wave_declaration", "initial_wave_budget", "initial_wave_barrier",
            }
            or (
                event.get("component") == "child_workspace"
                and str(event.get("child_id")) in initial_wave_children
            )
        )
    ]
    scenario_construction_base = bool(
        initial_wave_started_as_designed and not construction_failure_events
    )
    scenario_construction_errors = [
        f"infrastructure failure ({event.get('component')}): {event.get('detail')}"
        for event in construction_failure_events
    ]

    child_ids = sorted(set(spawned) & set(started))
    overlap = False
    initial_wave_overlap = False
    for index, left in enumerate(child_ids):
        for right in child_ids[index + 1:]:
            left_end = completed.get(left, {}).get("seq", float("inf"))
            right_end = completed.get(right, {}).get("seq", float("inf"))
            if started[left]["seq"] < right_end and started[right]["seq"] < left_end:
                overlap = True
                if left in initial_wave_children and right in initial_wave_children:
                    initial_wave_overlap = True

    delivery_while_unresolved = False
    for delivery in deliveries:
        for child_id, spawn in spawned.items():
            other_delivery = delivery_by_child.get(child_id)
            if child_id != delivery.get("child_id") and spawn["seq"] < delivery["seq"] and (
                other_delivery is None or other_delivery["seq"] > delivery["seq"]
            ):
                delivery_while_unresolved = True

    action_while_unresolved = False
    for action in _events_of(events, "main_action"):
        for child_id, spawn in spawned.items():
            delivery = delivery_by_child.get(child_id)
            if spawn["seq"] < action["seq"] and (delivery is None or delivery["seq"] > action["seq"]):
                action_while_unresolved = True

    concurrent_scenario_entry = bool(
        protocol_valid and gateway_control_valid and len(spawned) >= 2 and overlap
        and delivery_while_unresolved and action_while_unresolved
    )
    expected_results = [
        event.get("result")
        for event in case_spec.get("scenarios", {}).get(execution_mode, {}).get("events", [])
        if event.get("result") is not None
    ]
    observed_scheduled_order = [
        event.get("result_kind") for event in gateway_outcomes
        if event.get("benchmark_event_id") is not None
    ]
    observed_order = observed_scheduled_order or [
        event.get("result_kind") for event in gateway_outcomes
        if event.get("result_kind") in expected_results
    ]
    # Some live cases deliberately have no replay schedule: their authority is
    # produced by a real child while the superseded child is still running.
    # Keep A/B tied to explicit benchmark_event_id order, but audit an unscheduled
    # live pair directly from evaluator-observed gateway outcomes.  Otherwise an
    # empty live ``events`` declaration makes construction impossible even when
    # the runtime created the intended authority-before-superseded race.
    live_pair_order = [
        event.get("result_kind") for event in gateway_outcomes
        if event.get("result_kind") in {authoritative_kind, superseded_kind}
    ]
    cancellation_opportunity_children: set[str] = set()
    timely_cancelled_children: set[str] = set()
    # Only an explicit main-agent cancellation measures cancellation policy.
    # Infrastructure failures and episode-shutdown cleanup are lifecycle events,
    # not agent decisions.
    cancellations = [
        event for event in _events_of(events, "child_cancelled")
        if event.get("initiated_by", "main") == "main"
    ]
    workstream_results = {
        str(item.get("id")): str(item.get("result_kind"))
        for item in case_spec.get("delegation_workstreams", [])
    }
    measures_inflight_cancellation = (
        execution_mode == "async"
        and any(
            item.get("gate") == "timely_cancellation"
            and execution_mode in set(item.get("execution_modes") or [])
            for item in (control_flow_checks or [])
        )
    )
    if authoritative_delivery and measures_inflight_cancellation:
        for child_id, start_event in started.items():
            completion = completed.get(child_id)
            child_workstreams = list(spawned.get(child_id, {}).get("work_units") or [])
            assigned_results = {workstream_results.get(str(item)) for item in child_workstreams}
            if (
                child_id in initial_wave_children
                and
                superseded_kind in assigned_results
                and start_event["seq"] < authoritative_delivery["seq"]
                and (completion is None or completion["seq"] > authoritative_delivery["seq"])
            ):
                cancellation_opportunity_children.add(child_id)
        for event in cancellations:
            child_id = str(event.get("child_id"))
            if child_id in cancellation_opportunity_children and event["seq"] > authoritative_delivery["seq"]:
                timely_cancelled_children.add(child_id)
    observed_is_expected_prefix = bool(expected_results) and observed_order == expected_results[:len(observed_order)]
    missing_scheduled_results = (
        expected_results[len(observed_order):] if observed_is_expected_prefix else []
    )
    live_cancellation_order_valid = bool(
        measures_inflight_cancellation
        and authoritative_delivery
        and timely_cancelled_children
        and missing_scheduled_results
        and observed_is_expected_prefix
        and all(kind == superseded_kind for kind in missing_scheduled_results)
    )
    live_authority_first = bool(
        authoritative_outcome
        and (
            superseded_kind not in live_pair_order
            or (
                authoritative_kind in live_pair_order
                and live_pair_order.index(authoritative_kind)
                < live_pair_order.index(superseded_kind)
            )
        )
    )
    # Async completion order is intentionally *not* scripted.  Construction
    # requires that the evaluator observed every declared result role, while
    # the order itself remains a measured property of the real run.
    schedule_coverage_valid = (
        True if execution_mode == "linear"
        else bool(expected_results) and set(expected_results) <= set(observed_order)
    )
    construction_order_valid = schedule_coverage_valid
    live_progress_children = {
        str(event.get("child_id"))
        for event in _events_of(events, "child_progress_checkpoint")
        if event.get("phase") == "first_model_turn_finished"
        and authoritative_outcome is not None
        and int(event.get("seq", 0)) < int(authoritative_outcome.get("seq", 0))
    }
    live_opportunity_valid = (
        not measures_inflight_cancellation
        or authoritative_rejection is not None
        or bool(cancellation_opportunity_children & live_progress_children)
    )
    # Linear and async both run the benchmark-owned wave concurrently (spec §6).
    # The initial wave must establish real child-child execution overlap; the
    # only linear difference is that the main model sees ONE atomic bundle at the
    # end rather than per-result interruptions, so overlap is no longer the
    # thing linear avoids.
    concurrency_construction_valid = bool(initial_wave_overlap)
    if not concurrency_construction_valid:
        scenario_construction_errors.append(
            "benchmark failed to establish the required initial-wave execution overlap"
        )
    scenario_exposure_errors: list[str] = []
    if not construction_order_valid:
        scenario_exposure_errors.append(
            "participant ended before every case-specified async result role was observed"
        )
    if not live_opportunity_valid:
        scenario_exposure_errors.append(
            "participant ended without observing the designed in-flight cancellation opportunity"
        )
    scenario_exposure_complete = bool(
        construction_order_valid and live_opportunity_valid
    )
    scenario_constructed = bool(
        scenario_construction_base
        and concurrency_construction_valid
    )
    if execution_mode == "linear":
        # Linear must have a concurrent child-child wave (overlap) and the main
        # agent must wait for its atomic bundle before acting, so it must NOT
        # overlap a still-unresolved child (action_while_unresolved is False).
        scenario_entry = bool(
            protocol_valid and gateway_control_valid and len(spawned) >= 2
            and overlap and not action_while_unresolved
        )
    else:
        scenario_entry = concurrent_scenario_entry and schedule_coverage_valid

    verifier = _events_of(events, "verifier_result")
    verifier_summary = verifier[-1] if verifier else {}
    test_counts = verifier_summary.get("test_counts")
    test_pass_fraction = verifier_summary.get("test_pass_fraction")
    test_point_pass_rate = verifier_summary.get("test_point_pass_rate")
    if test_counts is None and verifier_summary.get("output"):
        parsed = parse_pytest_summary(str(verifier_summary["output"]))
        test_pass_fraction = parsed["test_pass_fraction"]
        test_counts = {
            key: parsed[key]
            for key in (
                "passed", "failed", "errors", "counted", "skipped",
                "deselected", "xfailed", "xpassed", "warnings",
                "summary_lines",
            )
        }
    consumed_completion_ids = {
        event["completion_id"] for event in _events_of(events, "result_consumed")
    }
    consumption_by_completion_id = _last_by(
        _events_of(events, "result_consumed"), "completion_id",
    )
    # Invalid/unaccepted lineage must not create useful-delegation credit even
    # if a custom adapter emits the artifact event despite a protocol violation.
    artifact_events = [
        event for event in _events_of(events, "artifact_committed")
        if set(event.get("lineage_completion_ids", [])).issubset(consumed_completion_ids)
        and event.get("evaluator_observed") is True
        and len(str(event.get("observed_digest", ""))) == 64
    ]
    artifact_commits: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for artifact in artifact_events:
        artifact_commits[str(artifact.get("artifact_id"))].append(artifact)
    final_artifacts = _last_by(artifact_events, "artifact_id")
    completion_to_child = {
        event["completion_id"]: event["child_id"] for event in _events_of(events, "child_completed")
    }
    useful_children = set()
    for artifact in final_artifacts.values():
        for completion_id in artifact.get("lineage_completion_ids", []):
            if completion_id in completion_to_child:
                useful_children.add(completion_to_child[completion_id])
    useful_delegation = len(useful_children) >= 2

    stale_deliveries = [
        event for event in deliveries
        if event.get("evaluator_stale", event.get("stale", False)) is True
    ]
    stale_completion_ids = {event["completion_id"] for event in stale_deliveries}
    stale_delivery_by_id = {event["completion_id"]: event for event in stale_deliveries}
    unmeasurable_completion_ids = {
        event["completion_id"] for event in deliveries
        if event.get("evaluator_stale_measurable") is False
    }
    verification_events = _events_of(events, "verification_requested")
    stale_revalidation = case_spec.get("stale_revalidation", {})
    revalidation_contract = stale_revalidation.get("artifact_checks", {})
    configured_candidate_checks = stale_revalidation.get("candidate_checks")

    def candidate_lineage_revalidated(
        artifact_id: str, artifact: dict[str, Any], candidate_completion_id: str,
        trigger_delivery: dict[str, Any],
    ) -> bool:
        if authoritative_delivery is None:
            return False
        authority_id = authoritative_delivery["completion_id"]
        lineage = set(artifact.get("lineage_completion_ids", []))
        required_lineage = {authority_id, candidate_completion_id}
        if artifact["seq"] <= trigger_delivery["seq"] or not required_lineage <= lineage:
            return False
        required = set(revalidation_contract.get(artifact_id, []))
        if not required:
            return False
        candidate_checks = (
            set(configured_candidate_checks)
            if configured_candidate_checks is not None else required
        )
        passed = set()
        for event in verification_events:
            check_id = event.get("check_id")
            if (
                check_id not in required
                or event["seq"] <= trigger_delivery["seq"]
                or event.get("passed") is not True
                or event.get("evaluator_owned") is not True
            ):
                continue
            check_lineage = set(event.get("lineage_completion_ids", []))
            required_check_lineage = {authority_id}
            if check_id in candidate_checks:
                required_check_lineage.add(candidate_completion_id)
            if required_check_lineage <= check_lineage:
                passed.add(str(check_id))
        return required <= passed

    def stale_lineage_revalidated(
        artifact_id: str, artifact: dict[str, Any], stale_completion_id: str,
    ) -> bool:
        return candidate_lineage_revalidated(
            artifact_id, artifact, stale_completion_id,
            stale_delivery_by_id[stale_completion_id],
        )

    stale_reasons = []
    invalidating_deliveries = [e for e in deliveries if e.get("invalidates_artifacts")]
    pre_authority_candidate_ids = set()
    if authoritative_delivery and invalidating_deliveries:
        pre_authority_candidate_ids = {
            str(event["completion_id"])
            for event in deliveries
            if event.get("result_kind") == superseded_kind
            and event["seq"] < authoritative_delivery["seq"]
        }
    stale_required_completion_ids = set(stale_completion_ids) | pre_authority_candidate_ids
    for delivery in invalidating_deliveries:
        for artifact_id in delivery["invalidates_artifacts"]:
            if artifact_id == "pre_event_verification":
                continue
            if artifact_id not in final_artifacts:
                stale_reasons.append(
                    f"{artifact_id}: missing evaluator-observed final artifact after "
                    f"{delivery.get('benchmark_event_id')}"
                )
    for artifact_id, artifact in final_artifacts.items():
        lineage = set(artifact.get("lineage_completion_ids", []))
        for stale_completion_id in lineage & stale_completion_ids:
            if not stale_lineage_revalidated(artifact_id, artifact, stale_completion_id):
                stale_reasons.append(
                    f"{artifact_id}: lineage contains unrevalidated stale completion"
                )
        for delivery in invalidating_deliveries:
            if artifact_id in delivery["invalidates_artifacts"]:
                if artifact["seq"] <= delivery["seq"]:
                    stale_reasons.append(f"{artifact_id}: not recommitted after {delivery.get('benchmark_event_id')}")
                elif delivery["completion_id"] not in lineage:
                    stale_reasons.append(f"{artifact_id}: revised lineage omits critical completion")
    final_lineage_completion_ids = {
        completion_id
        for artifact in final_artifacts.values()
        for completion_id in artifact.get("lineage_completion_ids", [])
    }
    # A failed/turn-exhausted provisional result can be replaced without being
    # adopted. Missing revision evidence matters only when that completion is
    # retained in a final artifact, or when no artifact lineage was observable.
    stale_truth_unmeasurable = bool(
        unmeasurable_completion_ids & final_lineage_completion_ids
    ) or bool(unmeasurable_completion_ids and not artifact_events)
    stale_retained_completion_ids: set[str] = set()
    for completion_id in stale_completion_ids:
        retained = [
            (artifact_id, artifact)
            for artifact_id, artifact in final_artifacts.items()
            if completion_id in artifact.get("lineage_completion_ids", [])
        ]
        if retained and not all(
            stale_lineage_revalidated(artifact_id, artifact, completion_id)
            for artifact_id, artifact in retained
        ):
            stale_retained_completion_ids.add(str(completion_id))
    invalidated_artifact_ids = {
        str(artifact_id)
        for delivery in invalidating_deliveries
        for artifact_id in delivery.get("invalidates_artifacts", [])
        if artifact_id != "pre_event_verification"
    }
    for completion_id in pre_authority_candidate_ids:
        retained = [
            (artifact_id, artifact)
            for artifact_id, artifact in final_artifacts.items()
            if artifact_id in invalidated_artifact_ids
            and completion_id in artifact.get("lineage_completion_ids", [])
        ]
        if retained and not all(
            candidate_lineage_revalidated(
                artifact_id, artifact, completion_id, authoritative_delivery,
            )
            for artifact_id, artifact in retained
        ):
            stale_retained_completion_ids.add(str(completion_id))
    stale_required_count = len(stale_required_completion_ids)
    stale_retained_count = len(stale_retained_completion_ids)
    stale_retention_rate = (
        stale_retained_count / stale_required_count if stale_required_count else None
    )
    fresh_final_state = bool(
        not stale_truth_unmeasurable
        and not stale_reasons
        and stale_retained_count == 0
    )

    recovery_latencies = []
    recovery_action_counts = []
    recovery_turn_counts = []

    def record_recovery(trigger: dict[str, Any], corrected: dict[str, Any]) -> None:
        recovery_latencies.append(corrected["elapsed_ms"] - trigger["elapsed_ms"])
        recovery_action_counts.append(sum(
            trigger["seq"] < event["seq"] <= corrected["seq"]
            for event in _events_of(events, "main_action")
        ))
        recovery_turn_counts.append(sum(
            trigger["seq"] < event["seq"] <= corrected["seq"]
            and event.get("phase") == "model_call_finished"
            and event.get("role") == "main"
            for event in _events_of(events, "agent_progress")
        ))

    for delivery in invalidating_deliveries:
        candidates = [
            event for event in artifact_events
            if event["seq"] > delivery["seq"]
            and event["artifact_id"] in delivery["invalidates_artifacts"]
            and delivery["completion_id"] in event.get("lineage_completion_ids", [])
        ]
        if candidates:
            corrected = min(candidates, key=lambda event: event["seq"])
            record_recovery(delivery, corrected)

    stale_lineage_artifacts = []
    revalidated_stale_artifacts = []
    for artifact_id, artifact in final_artifacts.items():
        for stale_completion_id in set(artifact.get("lineage_completion_ids", [])) & stale_completion_ids:
            stale_lineage_artifacts.append((artifact_id, artifact, stale_completion_id))
            if stale_lineage_revalidated(artifact_id, artifact, stale_completion_id):
                revalidated_stale_artifacts.append((artifact_id, artifact, stale_completion_id))
    if stale_lineage_artifacts and len(revalidated_stale_artifacts) == len(stale_lineage_artifacts):
        first_by_completion: dict[str, dict[str, Any]] = {}
        for _, artifact, stale_completion_id in revalidated_stale_artifacts:
            prior = first_by_completion.get(stale_completion_id)
            if prior is None or artifact["seq"] < prior["seq"]:
                first_by_completion[stale_completion_id] = artifact
        for stale_completion_id, corrected in first_by_completion.items():
            record_recovery(stale_delivery_by_id[stale_completion_id], corrected)

    # A contract-rejected asynchronous result is also a real replanning
    # trigger: the workstream resolved on schedule but produced unusable
    # evidence. Recovery requires a later valid delivery of every rejected
    # result kind. This is measured independently of final task correctness,
    # which remains covered by the frozen semantic/control test points.
    rejection_trigger_by_kind: dict[str, dict[str, Any]] = {}
    for rejection in contract_rejections:
        result_kind = str(rejection.get("result_kind", ""))
        prior = rejection_trigger_by_kind.get(result_kind)
        if prior is None or int(rejection.get("seq", 0)) > int(prior.get("seq", 0)):
            rejection_trigger_by_kind[result_kind] = rejection
    contract_recovery_deliveries: dict[str, dict[str, Any]] = {}
    for result_kind, trigger in rejection_trigger_by_kind.items():
        correction = min(
            (
                delivery for delivery in deliveries
                if str(delivery.get("result_kind", "")) == result_kind
                and int(delivery.get("seq", 0)) > int(trigger.get("seq", 0))
            ),
            key=lambda event: int(event.get("seq", 0)),
            default=None,
        )
        if correction is not None:
            contract_recovery_deliveries[result_kind] = correction
            record_recovery(trigger, correction)

    recovery_requirements: list[bool] = []
    if invalidating_deliveries:
        recovery_requirements.append(bool(fresh_final_state and recovery_latencies))
    elif stale_lineage_artifacts:
        recovery_requirements.append(
            len(revalidated_stale_artifacts) == len(stale_lineage_artifacts)
        )
    if rejection_trigger_by_kind:
        recovery_requirements.append(
            len(contract_recovery_deliveries) == len(rejection_trigger_by_kind)
        )
    recovery_status = (
        "not_required" if not recovery_requirements
        else ("recovered" if all(recovery_requirements) else "unrecovered")
    )
    recovered = recovery_status == "recovered"
    recovery_latency_ms = (
        max(recovery_latencies) if recovered and recovery_latencies else None
    )
    recovery_main_actions = (
        max(recovery_action_counts) if recovered and recovery_action_counts else None
    )
    recovery_main_turns = (
        max(recovery_turn_counts) if recovered and recovery_turn_counts else None
    )
    recovery_required = recovery_status != "not_required"

    obsolete_tokens = 0
    completion_by_id = {e["completion_id"]: e for e in _events_of(events, "child_completed")}
    finished_calls = [
        event for event in _events_of(events, "agent_progress")
        if event.get("phase") == "model_call_finished"
    ]
    main_tokens = sum(
        int(event.get("tokens", 0)) for event in finished_calls
        if event.get("role") == "main"
    )
    child_progress = [
        event for event in finished_calls if str(event.get("role", "")).startswith("child:")
    ]
    child_completion_tokens = sum(
        int(event.get("usage", {}).get("tokens", 0))
        for event in completion_by_id.values()
    )
    child_tokens = (
        sum(int(event.get("tokens", 0)) for event in child_progress)
        if child_progress else child_completion_tokens
    )
    total_tokens = main_tokens + child_tokens
    useful_child_tokens = sum(
        int(event.get("usage", {}).get("tokens", 0))
        for event in completion_by_id.values()
        if str(event.get("child_id")) in useful_children
    )
    revalidated_stale_completion_ids = {
        stale_completion_id
        for stale_completion_id in stale_completion_ids
        if (retained := [
            (artifact_id, artifact)
            for artifact_id, artifact in final_artifacts.items()
            if stale_completion_id in artifact.get("lineage_completion_ids", [])
        ])
        and all(
            stale_lineage_revalidated(artifact_id, artifact, stale_completion_id)
            for artifact_id, artifact in retained
        )
    }
    obsolete_completion_ids = stale_completion_ids - revalidated_stale_completion_ids
    if authoritative_delivery and pre_authority_candidate_ids and invalidating_deliveries:
        salvaged_pre_authority_candidates: set[str] = set()
        if recovery_status == "recovered":
            for candidate_id in pre_authority_candidate_ids:
                retained = [
                    (artifact_id, artifact)
                    for artifact_id, artifact in final_artifacts.items()
                    if artifact_id in invalidated_artifact_ids
                    and candidate_id in artifact.get("lineage_completion_ids", [])
                ]
                if retained and all(
                    candidate_lineage_revalidated(
                        artifact_id, artifact, candidate_id, authoritative_delivery,
                    )
                    for artifact_id, artifact in retained
                ):
                    salvaged_pre_authority_candidates.add(candidate_id)
        obsolete_completion_ids.update(
            pre_authority_candidate_ids - salvaged_pre_authority_candidates
        )
    for completion_id, completion in completion_by_id.items():
        tokens = int(completion.get("usage", {}).get("tokens", 0))
        if completion_id in obsolete_completion_ids:
            obsolete_tokens += tokens
    obsolete_work_ratio = obsolete_tokens / child_tokens if child_tokens else 0.0
    elapsed_values = [float(event.get("elapsed_ms", 0.0)) for event in events]
    episode_duration_ms = (
        max(elapsed_values) - min(elapsed_values) if elapsed_values else 0.0
    )

    cancelled_child_ids = {str(event.get("child_id")) for event in cancellations}
    cancelled_child_tokens = sum(
        int(event.get("tokens", 0)) for event in child_progress
        if str(event.get("role", "")).removeprefix("child:") in cancelled_child_ids
    )
    spawn_events = _events_of(events, "child_spawned")
    # The reference runtime explicitly tags benchmark-owned initial children.
    # Any later model-requested child is a replacement/redelegation regardless
    # of whether it was spawned before or after the authoritative delivery.
    # Retain the old temporal inference only for legacy third-party traces that
    # predate the initial_wave tag.
    if any("initial_wave" in event for event in spawn_events):
        redelegation_spawns = [
            event for event in spawn_events if event.get("initial_wave") is False
        ]
    else:
        redelegation_spawns = [
            event for event in spawn_events
            if authoritative_delivery and event["seq"] > authoritative_delivery["seq"]
        ]
    redelegated_children = {str(event["child_id"]) for event in redelegation_spawns}
    redelegated_useful_children = redelegated_children & useful_children
    failed_workstreams = {
        str(workstream)
        for child_id, event in completed.items()
        if event.get("success") is False
        or str(event.get("status") or "").lower() in {
            "failed", "error", "timeout", "step_limit_reached",
            "resource_safety_abort",
        }
        for workstream in (spawned.get(child_id, {}).get("work_units") or [])
    }
    recovered_workstreams = {
        str(workstream)
        for child_id in redelegated_useful_children
        for workstream in (spawned.get(child_id, {}).get("work_units") or [])
    }
    cancelled_workstreams = {
        str(workstream)
        for child_id in cancelled_child_ids
        for workstream in (spawned.get(child_id, {}).get("work_units") or [])
    }
    delivery_completion_ids_by_kind: dict[str, set[str]] = defaultdict(set)
    for delivery in deliveries:
        delivery_completion_ids_by_kind[str(delivery.get("result_kind") or "")].add(
            str(delivery.get("completion_id") or "")
        )
    local_statuses = {
        str(event.get("local_status") or event.get("status") or "")
        for event in _events_of(events, "episode_ended")
    }
    promotion_attempts = [
        event for event in _events_of(events, "main_action")
        if event.get("kind") == "promote_child_path"
    ]
    promotion_results = _events_of(events, "child_path_promotion_result")
    successful_promotions = [
        event for event in promotion_results if event.get("success") is True
    ]
    promotion_attempt_ids = [str(event.get("action_id")) for event in promotion_attempts]
    promotion_result_counts_by_action: dict[str, int] = defaultdict(int)
    for event in promotion_results:
        promotion_result_counts_by_action[str(event.get("action_id"))] += 1
    promotion_audit_errors = []
    for action_id in promotion_attempt_ids:
        result_count = promotion_result_counts_by_action.get(action_id, 0)
        if result_count != 1:
            promotion_audit_errors.append(
                f"promotion action {action_id!r} has {result_count} outcome events; expected 1"
            )
    for action_id in sorted(set(promotion_result_counts_by_action) - set(promotion_attempt_ids)):
        promotion_audit_errors.append(
            f"promotion outcome references unknown action {action_id!r}"
        )
    if len(promotion_attempt_ids) != len(set(promotion_attempt_ids)):
        promotion_audit_errors.append("promotion action ids are not unique")
    if measures_inflight_cancellation:
        scenario_entry = scenario_entry and bool(cancellation_opportunity_children)

    control_flow_facts = {
        "scenario_entry": scenario_entry,
        "scenario_constructed": scenario_constructed,
        "scenario_construction_errors": scenario_construction_errors,
        "scenario_exposure_complete": scenario_exposure_complete,
        "scenario_exposure_errors": scenario_exposure_errors,
        "consumed_completion_ids": consumed_completion_ids,
        "consumption_by_completion_id": consumption_by_completion_id,
        "authoritative_delivery": authoritative_delivery,
        "stale_deliveries": stale_deliveries,
        "stale_retained_completion_ids": stale_retained_completion_ids,
        "invalidating_deliveries": invalidating_deliveries,
        "final_artifacts": final_artifacts,
        "artifact_commits": dict(artifact_commits),
        "stale_required_completion_ids": stale_required_completion_ids,
        "cancellation_opportunity_children": cancellation_opportunity_children,
        "timely_cancelled_children": timely_cancelled_children,
        "unnecessary_cancellation_count": len(cancellations) - len(timely_cancelled_children),
        "spawned_by_id": spawned,
        "workstream_results": workstream_results,
        "post_authority_verification": bool(
            authoritative_delivery
            and any(
                int(event.get("seq", 0)) > int(authoritative_delivery.get("seq", 0))
                for event in _events_of(events, "verification_requested")
            )
        ),
        "replayed_deliveries": replayed_deliveries,
        "duplicate_side_effect_count": 0,
        "failed_workstreams": failed_workstreams,
        "recovered_workstreams": recovered_workstreams,
        "cancelled_workstreams": cancelled_workstreams,
        "delivery_completion_ids_by_kind": dict(delivery_completion_ids_by_kind),
        "conflicting_completion_ids": {
            str(item.get("completion_id")) for item in deliveries
        },
        "resource_limit_exceeded": bool(
            {"step_limit_reached", "resource_safety_abort"} & local_statuses
        ),
    }
    control_flow_results, control_flow_counts = evaluate_control_flow_checks(
        list(control_flow_checks or []), execution_mode, control_flow_facts,
        verifier_summary.get("semantic_check_results"),
    )
    semantic_results = verifier_summary.get("semantic_check_results")
    semantic_score = semantic_task_score(
        semantic_results, test_point_pass_rate, semantic_registry,
    )
    # Base Task Score: only ``score_domain == base_task`` checks feed BTS, so
    # async replanning evidence never leaks into the mode-neutral task score.
    base_task_score = score_base_task(semantic_results)
    dynamic_dimension_rates = dynamic_dimension_scores(control_flow_results)
    dynamic_group_rates = dynamic_decision_group_scores(control_flow_results)
    process_dynamic_score = dynamic_process_score(control_flow_results)

    # Qualification is benchmark-owned.  Participant behaviour may prevent a
    # valid authority result, end before the event boundary, or leave a
    # cancellation opportunity unrealised; those outcomes must score as failed
    # control decisions rather than removing the episode from the denominator.
    # Keep them as opportunity diagnostics, distinct from infrastructure
    # failures that genuinely make the measurement unscorable.
    dynamic_scenario_errors: list[str] = []
    dynamic_opportunity_errors: list[str] = []
    dynamic_event_exposure: dict[str, str] = {}
    contracts = list(event_contracts or [])
    async_drs: float | None = None
    async_event_drs: dict[str, Any] = {}
    provisional_established = 0
    participant_provisional_failure = 0
    if execution_mode == "async" and contracts:
        if not scenario_constructed:
            dynamic_scenario_errors.append("benchmark scenario construction failed")
        for failure in infrastructure_failure_events:
            if failure.get("component") == "delivery_intervention":
                dynamic_scenario_errors.append(
                    "benchmark delivery intervention failed: "
                    + str(failure.get("detail") or "unknown failure")
                )
        if not scenario_entry:
            dynamic_opportunity_errors.append("required dynamic opportunity was not entered")
        if not scenario_exposure_complete:
            dynamic_opportunity_errors.append("designed event exposure was incomplete")
        deliveries_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
        rejections_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for delivery in deliveries:
            deliveries_by_event[str(delivery.get("benchmark_event_id") or "")].append(delivery)
        for rejection in contract_rejections:
            rejections_by_event[str(rejection.get("benchmark_event_id") or "")].append(rejection)
        for contract in contracts:
            event_id = str(contract.get("event_id") or "")
            event_deliveries = list(deliveries_by_event.get(event_id) or [])
            event_rejections = list(rejections_by_event.get(event_id) or [])
            # Historical first-10 packages split the causal root event from an
            # ``.authority_result`` schedule event.  Accept that descendant as
            # diagnostic evidence while repaired packages bind the root ID
            # directly.  Restrict the compatibility join to the authoritative
            # result kind so ordinary workstream children cannot impersonate
            # the causal event.
            if not event_deliveries and not event_rejections:
                event_deliveries = [
                    item for key, values in deliveries_by_event.items()
                    if key.startswith(event_id + ".")
                    for item in values
                    if item.get("result_kind") == authoritative_kind
                ]
                event_rejections = [
                    item for key, values in rejections_by_event.items()
                    if key.startswith(event_id + ".")
                    for item in values
                    if item.get("result_kind") == authoritative_kind
                ]
            if not event_deliveries:
                if event_rejections:
                    dynamic_event_exposure[event_id] = "authority_rejected"
                    dynamic_opportunity_errors.append(
                        f"event {event_id!r} authority result was rejected by its contract"
                    )
                else:
                    dynamic_event_exposure[event_id] = "not_observed"
                    dynamic_opportunity_errors.append(
                        f"event {event_id!r} was not reached by the participant"
                    )
                continue
            dynamic_event_exposure[event_id] = "delivered"
            boundary = min(int(item.get("seq", 0)) for item in event_deliveries)
            delta = contract.get("state_delta") or {}
            affected = [str(item) for item in delta.get("affected_artifacts") or []]
            unaffected = [str(item) for item in delta.get("unaffected_artifacts") or []]
            trigger_artifacts = {
                str(item)
                for item in (contract.get("arrival_contract") or {}).get("after_artifacts", [])
            }
            opportunities = {str(item) for item in contract.get("required_opportunities") or []}
            if "stale_completion" in opportunities and not stale_required_completion_ids:
                dynamic_opportunity_errors.append(
                    f"event {event_id!r} created no evaluator-proven stale completion"
                )
            if "inflight_cancellation" in opportunities and not cancellation_opportunity_children:
                dynamic_opportunity_errors.append(
                    f"event {event_id!r} created no in-flight cancellation opportunity"
                )
            # Pre-event participant commits are scored decision preconditions,
            # not infrastructure qualification. Their absence fails the point;
            # it must never convert model inaction into an unscored episode.
        # Observation-point DRS (spec 9): each declared event that carries the
        # new scoring fields is scored independently of BTS; a final base-task
        # failure never erases an already-measurable event DRS.
        event_drs_scores: list[Any] = []
        for contract in contracts:
            event_id = str(contract.get("event_id") or "")
            if not _contract_carries_scoring_fields(contract):
                continue
            event_deliveries = list(deliveries_by_event.get(event_id) or [])
            event_rejections = list(rejections_by_event.get(event_id) or [])
            boundary_events = [*event_deliveries, *event_rejections]
            if not boundary_events:
                # Current semantics: a declared event the participant never
                # reached (no evaluator-observed boundary) is excluded from the
                # async_drs mean rather than scored 0 — treated as unscored, not
                # as a model failure.  Pinned by a test; pending a final ruling
                # from the spec owner (unreached -> unscored vs 0).
                continue
            boundary_seq = min(int(item.get("seq", 0)) for item in boundary_events)
            delta = contract.get("state_delta") or {}
            related_artifacts = {str(item) for item in delta.get("affected_artifacts") or []}
            related_artifacts |= {str(item) for item in delta.get("unaffected_artifacts") or []}
            related_artifacts |= {str(item) for item in contract.get("required_changes") or []}
            related_artifacts |= {str(item) for item in contract.get("required_preservation") or []}
            related_artifacts |= {str(item) for item in contract.get("forbidden_changes") or []}
            before, after = _event_state_snapshots(
                artifact_commits, related_artifacts, boundary_seq,
            )
            event_drs = score_event_replanning(
                contract, before, after, semantic_results,
            )
            if contract.get("requires_provisional") is True:
                if _provisional_missing(contract, before):
                    participant_provisional_failure += 1
                else:
                    provisional_established += 1
            event_drs_scores.append(event_drs)
            async_event_drs[event_id] = _event_drs_to_dict(event_drs)
        async_drs = score_async_drs(event_drs_scores)
    dynamic_scenario_qualified = not dynamic_scenario_errors
    dynamic_score = (
        dynamic_control_score(control_flow_results)
        if execution_mode != "async" or dynamic_scenario_qualified
        else None
    )
    critical_control_passed = critical_dynamic_success(control_flow_results)
    dt_score = combine_dt_score(dynamic_score, semantic_score)
    dynamic_passed = dynamic_success(dynamic_score, critical_control_passed)
    semantic_registry_checks = _registry_checks(semantic_registry)
    critical_semantic_ids = {
        str(item.get("id")) for item in semantic_registry_checks
        if item.get("critical") is True
    }
    semantic_by_id = {
        str(item.get("id")): item for item in (semantic_results or [])
    }
    critical_semantic_passed = (
        all(
            semantic_by_id.get(point_id, {}).get("passed") is True
            for point_id in critical_semantic_ids
        )
        if critical_semantic_ids else None
    )
    # Compatibility scalar. Linear reports the unchanged semantic baseline;
    # async reports the secondary 80/20 summary. The v9 leaderboard never uses
    # this alias as its primary metric.
    test_point_pass_rate = dt_score if dynamic_score is not None else semantic_score
    semantic_weighted_counts = _weighted_semantic_counts(
        verifier_summary.get("semantic_check_results"), semantic_registry,
    )
    control_flow_weighted_counts = _weighted_control_flow_counts(control_flow_results)

    # The X denominator is FIXED per (case, execution mode): the registries declare
    # which points apply, so every model under the same mode shares the
    # same applicable-point set, denominator digest and weighted denominator.
    # The runtime trace never changes applicability — a registered point the
    # model fails to exercise is a FAIL, never not_applicable. The digest is
    # written so aggregation can prove cross-model X comparability.
    registry_semantic_checks = semantic_registry_checks
    semantic_fixed_ids = sorted({
        str(item.get("id")) for item in registry_semantic_checks
        if item.get("id") is not None
    })
    if not semantic_fixed_ids:
        semantic_fixed_ids = sorted({
            str(item.get("id")) for item in (verifier_summary.get("semantic_check_results") or [])
            if item.get("id") is not None
        })
    applicable_control_flow_checks = [
        item for item in (control_flow_checks or [])
        if execution_mode in (item.get("execution_modes") or [])
    ]
    applicable_control_flow_ids = sorted({
        str(item.get("id")) for item in applicable_control_flow_checks
        if item.get("id") is not None
    })
    applicable_point_ids = sorted(set(semantic_fixed_ids) | set(applicable_control_flow_ids))
    semantic_weight_by_id = semantic_weight_map(semantic_registry)
    denominator_contract = {
        "score_policy_version": SCORE_POLICY_VERSION,
        "execution_mode": execution_mode,
        "semantic": sorted([
            {
                "id": point_id,
                "measurement_type": "semantic",
                "weight": semantic_weight_by_id.get(point_id, 1),
            }
            for point_id in semantic_fixed_ids
        ], key=lambda item: item["id"]),
        "dynamic_control": sorted([
            {
                "id": str(item.get("id")),
                "measurement_type": "control",
                "dimension": str(item.get("dimension") or ""),
                "decision_group": str(item.get("decision_group") or ""),
                "task_requirement_id": str(item.get("task_requirement_id") or ""),
                "weight": control_flow_weight(item),
                "critical": bool(item.get("critical")),
            }
            for item in applicable_control_flow_checks
        ], key=lambda item: item["id"]),
    }
    denominator_digest = canonical_digest(denominator_contract)
    weighted_denominator = sum(
        semantic_weight_by_id.get(point_id, 1) for point_id in semantic_fixed_ids
    ) + sum(control_flow_weight(item) for item in applicable_control_flow_checks)

    required_checks = set(case_spec.get("reverification_checks", []))
    anchor_contract = case_spec.get("reverification_anchors", {})
    completed_checks = set()
    triggered_checks = set()
    for check_id in required_checks:
        anchor_kinds = list(anchor_contract.get(check_id) or [authoritative_kind])
        anchor_deliveries = [
            max(
                (event for event in deliveries if event.get("result_kind") == result_kind),
                key=lambda event: event["seq"], default=None,
            )
            for result_kind in anchor_kinds
        ]
        if any(event is None for event in anchor_deliveries):
            continue
        triggered_checks.add(check_id)
        anchor_seq = max(event["seq"] for event in anchor_deliveries if event is not None)
        anchor_completion_ids = {
            str(event["completion_id"]) for event in anchor_deliveries if event is not None
        }
        relevant_artifact_seqs = [
            int(final_artifacts[artifact_id]["seq"])
            for artifact_id, checks in revalidation_contract.items()
            if check_id in checks and artifact_id in final_artifacts
        ]
        required_after_seq = max([anchor_seq, *relevant_artifact_seqs])
        if any(
            event.get("check_id") == check_id
            and event["seq"] > required_after_seq
            and event.get("passed") is True
            and event.get("evaluator_owned") is True
            and anchor_completion_ids <= set(event.get("lineage_completion_ids", []))
            for event in verification_events
        ):
            completed_checks.add(check_id)
    reverification_required_count = len(triggered_checks)
    reverification_passed_count = len(triggered_checks & completed_checks)
    reverification_completeness = (
        reverification_passed_count / reverification_required_count
        if reverification_required_count else None
    )

    controlled_deliveries = (
        [event for event in deliveries if event.get("completion_id") in initial_completion_ids]
        if initial_completion_ids is not None else deliveries
    )
    # Fraction of all deliveries accounted for by the fork bundle's controlled
    # initial completions. ``None`` when the episode was not a replay/fork.
    replay_fork_coverage = (
        len(controlled_deliveries) / len(deliveries)
        if initial_completion_ids is not None and deliveries else None
    )
    controlled_order = protocol_valid and (
        all(event.get("controlled_order", False) for event in controlled_deliveries)
        if controlled_deliveries else False
    )
    result_bundle = sorted(
        (e.get("result_kind"), e.get("payload_sha256")) for e in controlled_deliveries
    )
    result_bundle_digest = canonical_digest(result_bundle)
    contract_validations = _events_of(events, "result_contract_validated")
    contract_rejection_reason_counts: dict[str, int] = defaultdict(int)
    for rejection in contract_rejections:
        for reason_code in rejection.get("reason_codes") or []:
            contract_rejection_reason_counts[str(reason_code)] += 1

    # Task 8: mutually exclusive per-attempt terminal classification (one row
    # per spawned child; retry is the ``attempt_number`` facet).  Contract
    # acceptance is the gateway verdict (``gateway_accepted`` on delivery), not
    # whether the main agent later consumed the result (``consumed_by_main``
    # facet).  Verdict acceptance/rejection denominators cover only
    # verdict-bearing submissions (``gateway_accepted`` + ``public_rejection``);
    # sealed-without-verdict, step/safety/no-submission ends, designed
    # terminals, cancels, case-contract and infrastructure failures never enter
    # them.
    child_terminals = classify_child_terminals(events)
    terminal_counts = {cls: 0 for cls in TERMINAL_CLASSES}
    for row in child_terminals:
        terminal_counts[row["terminal_class"]] += 1
    total_attempt_count = len(child_terminals)
    first_attempt_rows = [row for row in child_terminals if not row["retry"]]
    retry_rows = [row for row in child_terminals if row["retry"]]

    def _rate(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None

    sealed_submission_count = sum(1 for row in child_terminals if row["sealed_submission"])
    verdict_rows = [row for row in child_terminals if row["gateway_verdict"]]
    gateway_accepted_rows = [
        row for row in child_terminals if row["terminal_class"] == GATEWAY_ACCEPTED
    ]
    public_rejected_rows = [
        row for row in child_terminals if row["terminal_class"] == PUBLIC_REJECTION
    ]
    sealed_pending_verdict_rows = [
        row for row in child_terminals if row["terminal_class"] == SEALED_PENDING_VERDICT
    ]
    gateway_verdict_count = len(verdict_rows)
    gateway_accepted_count = len(gateway_accepted_rows)
    public_rejected_count = len(public_rejected_rows)
    sealed_pending_verdict_count = len(sealed_pending_verdict_rows)
    submission_acceptance_rate = _rate(gateway_accepted_count, gateway_verdict_count)
    submission_rejection_rate = _rate(public_rejected_count, gateway_verdict_count)

    first_attempt_verdict_count = sum(
        1 for row in first_attempt_rows if row["gateway_verdict"]
    )
    first_attempt_accepted_count = sum(
        1 for row in first_attempt_rows if row["terminal_class"] == GATEWAY_ACCEPTED
    )
    first_attempt_acceptance_rate = _rate(
        first_attempt_accepted_count, first_attempt_verdict_count,
    )
    retry_verdict_count = sum(1 for row in retry_rows if row["gateway_verdict"])
    retry_accepted_count = sum(
        1 for row in retry_rows if row["terminal_class"] == GATEWAY_ACCEPTED
    )
    retry_acceptance_rate = _rate(retry_accepted_count, retry_verdict_count)

    accepted_child_tokens = sum(int(row["tokens"]) for row in gateway_accepted_rows)
    avg_child_tokens_per_gateway_accepted = _rate(
        accepted_child_tokens, gateway_accepted_count,
    )
    # Task 8 P1-19 cost-of-rejection: extra child tokens are what a workstream
    # spent on public rejections *beyond* the accepted one.  Sealed-without-
    # verdict attempts carry no verdict and private-only (case-contract)
    # rejections are benchmark errors, so neither counts as a public rejection.
    extra_child_tokens_from_public_rejections = _extra_tokens_from_public_rejections(
        child_terminals,
    )
    resource_safety_abort_rate_per_attempt = _rate(
        sum(1 for row in child_terminals
            if row["terminal_class"] == RESOURCE_SAFETY_ABORT),
        total_attempt_count,
    )
    child_step_limit_rate_per_attempt = _rate(
        sum(1 for row in child_terminals
            if row["terminal_class"] == STEP_LIMIT_REACHED),
        total_attempt_count,
    )
    no_submission_rate_per_attempt = _rate(
        sum(1 for row in child_terminals if row["terminal_class"] == NO_SUBMISSION),
        total_attempt_count,
    )
    redelegation_attempt_count = len(retry_rows)
    # P0-9: a redelegation that contributes no new evidence is a duplicate
    # evidence retry; the runtime marker (renamed in Task 7 to
    # ``duplicate_evidence_retry_detected``) records each instance.
    invalid_redelegation_count = len(
        _events_of(events, "duplicate_evidence_retry_detected")
    )
    invalid_redelegation_rate = _rate(
        invalid_redelegation_count, redelegation_attempt_count,
    )

    return {
        "test_point_pass_rate": test_point_pass_rate,
        "score_policy_version": SCORE_POLICY_VERSION,
        "semantic_task_score": semantic_score,
        "base_task_score": base_task_score,
        "async_drs": async_drs,
        "async_event_drs": async_event_drs,
        # Delivery-opportunity accounting (spec 3.3 / 9.4): how many declared
        # events reached each lifecycle stage, and how failures split between
        # participant provisional failures and evaluator infrastructure failures.
        "event_opportunity_counts": {
            "declared_events": len(contracts),
            "provisional_established": provisional_established,
            "result_available": sum(
                1 for event in events if event.get("type") == "result_available"
            ),
            "adapter_queued": sum(
                1 for event in events if event.get("type") == "adapter_queued"
            ),
            "result_presented": sum(
                1 for event in events if event.get("type") == "result_presented"
            ),
            "response_window_closed": sum(
                1 for event in events if event.get("type") == "response_window_closed"
            ),
            "participant_provisional_failure": participant_provisional_failure,
            "infrastructure_delivery_failure": sum(
                1 for event in events
                if event.get("type") == "infrastructure_failure"
                and event.get("component") == "delivery_intervention"
            ),
        },
        "dynamic_control_score": dynamic_score,
        "dynamic_process_score": process_dynamic_score,
        "dynamic_scenario_qualified": dynamic_scenario_qualified,
        "dynamic_scenario_errors": dynamic_scenario_errors,
        "dynamic_opportunity_complete": not dynamic_opportunity_errors,
        "dynamic_opportunity_errors": dynamic_opportunity_errors,
        "dynamic_event_exposure": dynamic_event_exposure,
        "dynamic_dimension_scores": dynamic_dimension_rates,
        "dynamic_decision_group_scores": dynamic_group_rates,
        "dt_score": dt_score,
        "critical_dynamic_success": critical_control_passed,
        "critical_semantic_success": critical_semantic_passed,
        "dynamic_success": dynamic_passed,
        "semantic_check_results": verifier_summary.get("semantic_check_results"),
        "semantic_check_counts": verifier_summary.get("semantic_check_counts"),
        "semantic_check_weighted_counts": semantic_weighted_counts,
        "semantic_registry_version": verifier_summary.get("semantic_registry_version"),
        "control_flow_check_results": control_flow_results,
        "control_flow_check_counts": control_flow_counts,
        "control_flow_check_weighted_counts": control_flow_weighted_counts,
        # Fixed per-(case, mode) denominator, so all models under the same mode
        # share an identical X denominator (comparability proof).
        "applicable_point_ids": applicable_point_ids,
        "applicable_control_flow_ids": applicable_control_flow_ids,
        "denominator_digest": denominator_digest,
        "denominator_contract": denominator_contract,
        "weighted_denominator": weighted_denominator,
        "test_pass_fraction": test_pass_fraction,
        "test_counts": test_counts,
        "component_results": verifier_summary.get("component_results"),
        "verifier_bundle_sha256": verifier_summary.get("verifier_bundle_sha256"),
        "protocol_valid": protocol_valid,
        "gateway_control_valid": gateway_control_valid,
        "gateway_violation_count": gateway_violation_count,
        "result_contract_validation_count": len(contract_validations),
        "result_contract_rejected_count": len(contract_rejections),
        # Raw per-completion gateway diagnostic: the paper-facing
        # ``submission_rejection_rate`` below is over verdict-bearing
        # submissions only (gateway_accepted + public_rejection), so step/safety
        # exits, sealed-without-verdict closes, designed terminals, cancels,
        # case-contract and infrastructure failures never enter its denominator.
        "result_contract_rejection_rate": (
            len(contract_rejections) / len(completion_by_id) if completion_by_id else 0.0
        ),
        "result_contract_rejection_reason_counts": dict(contract_rejection_reason_counts),
        # Task 8: mutually exclusive per-attempt terminal classification (one
        # row per spawned child; retry is the attempt_number facet) and
        # gateway-verdict denominators.
        "child_terminal_classifications": child_terminals,
        "child_terminal_counts": terminal_counts,
        "sealed_submission_count": sealed_submission_count,
        "gateway_verdict_count": gateway_verdict_count,
        "gateway_accepted_count": gateway_accepted_count,
        "public_rejected_count": public_rejected_count,
        "sealed_pending_verdict_count": sealed_pending_verdict_count,
        "submission_acceptance_rate": submission_acceptance_rate,
        "submission_rejection_rate": submission_rejection_rate,
        "first_attempt_verdict_count": first_attempt_verdict_count,
        "first_attempt_accepted_count": first_attempt_accepted_count,
        "first_attempt_acceptance_rate": first_attempt_acceptance_rate,
        "retry_verdict_count": retry_verdict_count,
        "retry_accepted_count": retry_accepted_count,
        "retry_acceptance_rate": retry_acceptance_rate,
        "avg_child_tokens_per_gateway_accepted": avg_child_tokens_per_gateway_accepted,
        "extra_child_tokens_from_public_rejections": extra_child_tokens_from_public_rejections,
        "resource_safety_abort_rate_per_attempt": resource_safety_abort_rate_per_attempt,
        "child_step_limit_rate_per_attempt": child_step_limit_rate_per_attempt,
        "no_submission_rate_per_attempt": no_submission_rate_per_attempt,
        "redelegation_attempt_count": redelegation_attempt_count,
        "invalid_redelegation_count": invalid_redelegation_count,
        "invalid_redelegation_rate": invalid_redelegation_rate,
        "completion_replay_count": len(replayed_deliveries),
        "replayed_completion_ids": sorted({
            str(event.get("completion_id")) for event in replayed_deliveries
        }),
        "visibility_leakage_detected": visibility_leakage_detected,
        "scenario_entry": scenario_entry,
        "scenario_entry_components": {
            "two_main_children": len(spawned) >= 2,
            "overlapping_execution": overlap,
            "delivery_while_other_unresolved": delivery_while_unresolved,
            "main_action_while_unresolved": action_while_unresolved,
            "schedule_coverage_valid": schedule_coverage_valid,
            "child_child_overlap": overlap,
            "main_child_overlap": action_while_unresolved,
            "inflight_cancellation_opportunity": (
                bool(cancellation_opportunity_children)
                if measures_inflight_cancellation else None
            ),
        },
        "scenario_constructed": scenario_constructed,
        "scenario_construction_errors": scenario_construction_errors,
        "scenario_exposure_complete": scenario_exposure_complete,
        "scenario_exposure_errors": scenario_exposure_errors,
        "useful_delegation": useful_delegation,
        "delegation_validation_error_count": len(delegation_validation_errors),
        "useful_child_count": len(useful_children),
        "orchestration_success": scenario_entry and useful_delegation,
        "stale_required_count": stale_required_count,
        "stale_retained_count": stale_retained_count,
        "stale_retention_rate": stale_retention_rate,
        "stale_required_completion_ids": sorted(stale_required_completion_ids),
        "stale_retained_completion_ids": sorted(stale_retained_completion_ids),
        "stale_truth_measurable": not stale_truth_unmeasurable,
        "stale_reasons": stale_reasons,
        "recovery_latency_ms": recovery_latency_ms,
        "recovery_required": recovery_required,
        "recovery_status": recovery_status,
        "recovery_unfinished": recovery_status == "unrecovered",
        "recovery_main_actions": recovery_main_actions,
        "recovery_main_turns": recovery_main_turns,
        "obsolete_work_ratio": obsolete_work_ratio,
        "total_tokens": total_tokens,
        "main_tokens": main_tokens,
        "child_tokens": child_tokens,
        "useful_child_tokens": useful_child_tokens,
        "obsolete_child_tokens": obsolete_tokens,
        "cancelled_child_tokens": cancelled_child_tokens,
        "episode_duration_ms": episode_duration_ms,
        "cancellation_opportunity": bool(cancellation_opportunity_children),
        "cancellation_opportunity_count": len(cancellation_opportunity_children),
        "timely_cancellation_count": len(timely_cancelled_children),
        "cancellation_recall": (
            len(timely_cancelled_children) / len(cancellation_opportunity_children)
            if cancellation_opportunity_children else None
        ),
        "unnecessary_cancellation_count": len(cancellations) - len(timely_cancelled_children),
        "redelegation_count": len(redelegation_spawns),
        "redelegated_useful_child_count": len(redelegated_useful_children),
        "redelegation_success": (
            bool(redelegated_useful_children) if redelegation_spawns else None
        ),
        "contract_recovery_required_kind_count": len(rejection_trigger_by_kind),
        "contract_recovery_completed_kind_count": len(contract_recovery_deliveries),
        "promotion_attempt_count": len(promotion_attempts),
        "promotion_result_count": len(promotion_results),
        "promotion_success_count": len(successful_promotions),
        "promotion_failure_count": len(promotion_results) - len(successful_promotions),
        "promotion_unobserved_count": max(0, len(promotion_attempts) - len(promotion_results)),
        "promotion_audit_complete": not promotion_audit_errors,
        "promotion_audit_errors": promotion_audit_errors,
        "reverification_required_count": reverification_required_count,
        "reverification_passed_count": reverification_passed_count,
        "reverification_completeness": reverification_completeness,
        "controlled_order": controlled_order,
        "schedule_coverage_valid": schedule_coverage_valid,
        "declared_async_results": expected_results,
        "observed_completion_order": observed_order,
        "replay_fork_coverage": replay_fork_coverage,
        "result_bundle_digest": result_bundle_digest,
        "controlled_initial_completion_count": len(controlled_deliveries),
        "branch_completion_count": len(deliveries) - len(controlled_deliveries),
    }
