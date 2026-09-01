from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .evaluation.control_flow_gates import GATE_EXECUTION_MODES, GATE_NAMES
from .evaluation.weighting import DYNAMIC_CONTROL_DIMENSIONS, GATE_DYNAMIC_DIMENSIONS


DYNAMIC_REGISTRY_VERSION = "7"
# V6 derives point count from the case's causal structure.  Atomic event cases
# may expose only two independent decisions; main replanning cases must expose
# at least four, but no case gains weight merely by manufacturing more checks.
MIN_DYNAMIC_POINTS = 2
MAX_DYNAMIC_POINTS = 8
MIN_MAIN_TRACK_POINTS = 4
MIN_MAIN_TRACK_DIMENSIONS = 2
MIN_MAIN_TRACK_EVIDENCE_GROUPS = 3
LEGACY_V5_MIN_DYNAMIC_POINTS = 8
LEGACY_V5_MAX_DYNAMIC_POINTS = 12
LEGACY_V5_MIN_POINTS_PER_DIMENSION = 2
DESIGN_FIELDS = (
    "event_id",
    "precondition",
    "expected_behavior",
    "forbidden_behavior",
    "primary_evidence",
    "mutation_id",
    "independence_key",
    "evidence_group",
    "decision_group",
    "task_requirement_id",
    "obligation",
)
EVENT_TRACKS = frozenset({"atomic_event", "dynamic_replanning"})
EVENT_OBSERVATION_MODES = frozenset({"gateway_only", "instrumented_live_source"})
GATE_PRIMARY_FACTS = {
    "wait_for_authority": "authority_consumption",
    "reject_late_stale": "stale_result_decision",
    "resolve_authority": "state_transition",
    "timely_cancellation": "cancellation",
    "selective_replan": "pre_post_replan",
    "rederive_from_authority": "closure_reverification",
    "deduplicate_completion": "idempotency_decision",
    "recover_failed_work": "failure_recovery",
    "arbitrate_conflict": "conflict_resolution",
    "resource_triage": "resource_decision",
}
PROCEDURAL_LEAKAGE_PATTERNS = (
    "before accepting or promoting",
    "invalidate only",
    "reopen final-state",
    "accept or reject deliveries",
    "cancel work that is no longer useful",
    "revise only artifacts whose revision assumptions changed",
    "compare reported revisions before integrating",
    "do not infer correctness from a preferred child completion order",
)


def validate_dynamic_point_plan(
    plan: Any,
    *,
    event_ids: set[str] | None = None,
    expected_prefix: str | None = None,
    registry_version: str = DYNAMIC_REGISTRY_VERSION,
    event_contracts: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Validate the production contract for high-quality dynamic checks.

    A point is a hidden, independently identifiable decision unit.  It must say
    what event opens the opportunity, what behaviour is required/forbidden,
    which evaluator evidence decides it, and which negative mutation challenges
    it.  These fields are design evidence; they are never participant-visible.
    """
    errors: list[str] = []
    if not isinstance(plan, list):
        return ["dynamic_point_plan must be a list"]
    if registry_version == "5":
        point_min, point_max = (
            LEGACY_V5_MIN_DYNAMIC_POINTS, LEGACY_V5_MAX_DYNAMIC_POINTS,
        )
    else:
        point_min, point_max = MIN_DYNAMIC_POINTS, MAX_DYNAMIC_POINTS
    if not point_min <= len(plan) <= point_max:
        errors.append(
            f"dynamic_point_plan must contain {point_min}-{point_max} "
            f"points for registry v{registry_version}, found {len(plan)}"
        )
    ids: set[str] = set()
    mutations: set[str] = set()
    independence_keys: set[str] = set()
    evidence_keys: set[str] = set()
    gate_signatures: set[str] = set()
    dimensions: Counter[str] = Counter()
    evidence_groups: Counter[str] = Counter()
    contracts_by_event = {
        str(contract.get("event_id") or ""): contract
        for contract in (event_contracts or []) if isinstance(contract, dict)
    }
    for index, point in enumerate(plan):
        label = f"dynamic_point_plan[{index}]"
        if not isinstance(point, dict):
            errors.append(f"{label} must be an object")
            continue
        required_fields = DESIGN_FIELDS if registry_version == DYNAMIC_REGISTRY_VERSION else DESIGN_FIELDS[:8]
        missing = [field for field in required_fields if not str(point.get(field) or "").strip()]
        if missing:
            errors.append(f"{label} missing non-empty design fields {missing!r}")
        point_id = str(point.get("id") or "")
        if not point_id or point_id in ids:
            errors.append(f"{label}.id must be non-empty and unique")
        elif expected_prefix and not point_id.startswith(f"{expected_prefix}.cf."):
            errors.append(f"{label}.id must start with {expected_prefix}.cf.")
        ids.add(point_id)
        mutation_id = str(point.get("mutation_id") or "")
        if mutation_id in mutations:
            errors.append(f"{label}.mutation_id must be unique")
        mutations.add(mutation_id)
        independence_key = str(point.get("independence_key") or "")
        if independence_key in independence_keys:
            errors.append(f"{label}.independence_key must be unique")
        independence_keys.add(independence_key)
        evidence = str(point.get("primary_evidence") or "")
        if evidence in evidence_keys:
            errors.append(f"{label}.primary_evidence must be unique")
        evidence_keys.add(evidence)
        if registry_version != "5":
            evidence_group = str(point.get("evidence_group") or "")
            evidence_groups[evidence_group] += 1
            evidence_spec = point.get("evidence_spec")
            if not isinstance(evidence_spec, dict):
                errors.append(f"{label}.evidence_spec must be an object")
            else:
                primary_fact = str(evidence_spec.get("primary_fact") or "")
                if primary_fact != GATE_PRIMARY_FACTS.get(str(point.get("gate") or "")):
                    errors.append(
                        f"{label}.evidence_spec.primary_fact must be "
                        f"{GATE_PRIMARY_FACTS.get(str(point.get('gate') or ''))!r}"
                    )
                if not str(evidence_spec.get("subject") or "").strip():
                    errors.append(f"{label}.evidence_spec.subject is required")
            precondition = point.get("precondition_contract")
            if not isinstance(precondition, dict):
                errors.append(f"{label}.precondition_contract must be an object")
            else:
                required_facts = precondition.get("required_facts")
                if (
                    not isinstance(required_facts, list) or not required_facts
                    or any(not str(value).strip() for value in required_facts)
                ):
                    errors.append(
                        f"{label}.precondition_contract.required_facts must be a "
                        "non-empty string list"
                    )
                on_missing = precondition.get("on_missing")
                anchor_gated = point.get("requires_outcome_anchor") is True
                expected_on_missing = "invalid_episode" if anchor_gated else "fail_point"
                if on_missing != expected_on_missing:
                    errors.append(
                        f"{label}.precondition_contract.on_missing must be "
                        f"{expected_on_missing!r}"
                    )
                contract = contracts_by_event.get(str(point.get("event_id") or ""))
                if contract is not None and isinstance(required_facts, list):
                    guaranteed = {
                        "authority_delivery",
                        *map(str, contract.get("required_opportunities") or []),
                    }
                    unsupported = sorted(set(map(str, required_facts)) - guaranteed)
                    if unsupported:
                        errors.append(
                            f"{label}.precondition_contract requires facts not guaranteed "
                            f"by its event contract: {unsupported!r}"
                        )
            if not isinstance(point.get("requires_outcome_anchor"), bool):
                errors.append(f"{label}.requires_outcome_anchor must be boolean")
        event_id = str(point.get("event_id") or "")
        if event_ids is not None and event_id not in event_ids:
            errors.append(f"{label}.event_id references unknown private event {event_id!r}")
        gate = str(point.get("gate") or "")
        if gate not in GATE_NAMES:
            errors.append(f"{label}.gate is invalid: {gate!r}")
        modes = {str(value) for value in (point.get("execution_modes") or [])}
        if gate in GATE_NAMES and modes != set(GATE_EXECUTION_MODES.get(gate, ())):
            errors.append(f"{label}: gate/execution-mode matrix is not frozen")
        dimension = str(point.get("dimension") or "")
        if dimension != GATE_DYNAMIC_DIMENSIONS.get(gate):
            errors.append(
                f"{label}.dimension must be {GATE_DYNAMIC_DIMENSIONS.get(gate)!r} "
                f"for gate {gate!r}"
            )
        if dimension in DYNAMIC_CONTROL_DIMENSIONS:
            dimensions[dimension] += 1
        signature = json.dumps(
            {"gate": gate, "gate_args": point.get("gate_args") or {}},
            ensure_ascii=False, sort_keys=True,
        )
        if signature in gate_signatures:
            errors.append(
                f"{label}: gate and gate_args duplicate another dynamic decision unit"
            )
        gate_signatures.add(signature)
    if registry_version == "5":
        for dimension in DYNAMIC_CONTROL_DIMENSIONS:
            if dimensions[dimension] < LEGACY_V5_MIN_POINTS_PER_DIMENSION:
                errors.append(
                    f"dynamic dimension {dimension!r} requires at least "
                    f"{LEGACY_V5_MIN_POINTS_PER_DIMENSION} points, found {dimensions[dimension]}"
                )
    else:
        contracts = event_contracts or []
        main_track = any(
            isinstance(contract, dict)
            and contract.get("track") == "dynamic_replanning"
            for contract in contracts
        )
        if main_track and len(plan) < MIN_MAIN_TRACK_POINTS:
            errors.append(
                f"dynamic_replanning track requires at least {MIN_MAIN_TRACK_POINTS} points"
            )
        if main_track and sum(count > 0 for count in dimensions.values()) < MIN_MAIN_TRACK_DIMENSIONS:
            errors.append(
                f"dynamic_replanning track requires at least "
                f"{MIN_MAIN_TRACK_DIMENSIONS} represented dimensions"
            )
        if main_track and len(evidence_groups) < MIN_MAIN_TRACK_EVIDENCE_GROUPS:
            errors.append(
                f"dynamic_replanning track requires at least "
                f"{MIN_MAIN_TRACK_EVIDENCE_GROUPS} primary evidence groups"
            )
        overused = sorted(group for group, count in evidence_groups.items() if count > 2)
        if overused:
            errors.append(
                f"evidence groups may support at most two points each; overused {overused!r}"
            )
    return errors


def validate_event_contracts(
    contracts: Any, *, event_ids: set[str] | None = None,
) -> list[str]:
    """Validate the case-level proof that each scored event is meaningful.

    Static validation cannot prove runtime causality, but it can reject designs
    that omit an explicit before/after delta, arrival boundary, authority mode,
    or the opportunities the scorer must later observe.
    """
    if not isinstance(contracts, list) or not contracts:
        return ["event_contracts must be a non-empty list"]
    errors: list[str] = []
    seen: set[str] = set()
    for index, contract in enumerate(contracts):
        label = f"event_contracts[{index}]"
        if not isinstance(contract, dict):
            errors.append(f"{label} must be an object")
            continue
        event_id = str(contract.get("event_id") or "")
        if not event_id or event_id in seen:
            errors.append(f"{label}.event_id must be non-empty and unique")
        seen.add(event_id)
        if event_ids is not None and event_id not in event_ids:
            errors.append(f"{label}.event_id references unknown event {event_id!r}")
        if not str(contract.get("event_theme") or "").strip():
            errors.append(f"{label}.event_theme is required")
        if contract.get("track") not in EVENT_TRACKS:
            errors.append(f"{label}.track must be one of {sorted(EVENT_TRACKS)!r}")
        observation_mode = contract.get("observation_mode")
        if observation_mode not in EVENT_OBSERVATION_MODES:
            errors.append(
                f"{label}.observation_mode must be one of "
                f"{sorted(EVENT_OBSERVATION_MODES)!r}"
            )
        if not str(contract.get("authority_source") or "").strip():
            errors.append(f"{label}.authority_source is required")
        if observation_mode == "gateway_only" and contract.get("main_visible_before_delivery") is not False:
            errors.append(
                f"{label}.main_visible_before_delivery must be false for gateway_only events"
            )
        delta = contract.get("state_delta")
        if not isinstance(delta, dict):
            errors.append(f"{label}.state_delta must be an object")
        else:
            before = str(delta.get("before") or "").strip()
            after = str(delta.get("after") or "").strip()
            if not before or not after or before == after:
                errors.append(
                    f"{label}.state_delta requires distinct non-empty before and after states"
                )
            affected = delta.get("affected_artifacts")
            if not isinstance(affected, list) or not affected:
                errors.append(f"{label}.state_delta.affected_artifacts must be non-empty")
        arrival = contract.get("arrival_contract")
        if not isinstance(arrival, dict):
            errors.append(f"{label}.arrival_contract must be an object")
        else:
            for field in ("after_facts", "before_facts"):
                values = arrival.get(field)
                if not isinstance(values, list) or not values:
                    errors.append(f"{label}.arrival_contract.{field} must be non-empty")
            after_artifacts = arrival.get("after_artifacts")
            if not isinstance(after_artifacts, list) or not after_artifacts:
                errors.append(
                    f"{label}.arrival_contract.after_artifacts must be a non-empty list"
                )
            elif isinstance(delta, dict):
                declared = {
                    str(value)
                    for field in ("affected_artifacts", "unaffected_artifacts")
                    for value in (delta.get(field) or [])
                }
                unknown = set(map(str, after_artifacts)) - declared
                if unknown:
                    errors.append(
                        f"{label}.arrival_contract.after_artifacts references state outside "
                        f"the delta contract {sorted(unknown)!r}"
                    )
        opportunities = contract.get("required_opportunities")
        if (
            not isinstance(opportunities, list) or not opportunities
            or any(not str(value).strip() for value in opportunities)
        ):
            errors.append(f"{label}.required_opportunities must be a non-empty string list")
        elif isinstance(arrival, dict) and isinstance(delta, dict):
            trigger_artifacts = set(map(str, arrival.get("after_artifacts") or []))
            if (
                "pre_event_affected_commit" in opportunities
                and not trigger_artifacts.intersection(delta.get("affected_artifacts") or [])
            ):
                errors.append(
                    f"{label} requires a pre-event affected commit but its arrival boundary "
                    "contains no affected artifact"
                )
            if (
                "pre_event_unaffected_commit" in opportunities
                and not trigger_artifacts.intersection(delta.get("unaffected_artifacts") or [])
            ):
                errors.append(
                    f"{label} requires a pre-event unaffected commit but its arrival boundary "
                    "contains no unaffected artifact"
                )
    return errors


def participant_leakage_hits(case_dir: Path, points: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Byte-level scan for hidden point/mutation identifiers in participant files."""
    visible = [case_dir / "public_case.yaml", case_dir / "task" / "task.yaml"]
    needles = sorted({
        value
        for point in points
        for value in (str(point.get("id") or ""), str(point.get("mutation_id") or ""))
        if value
    })
    hits: list[dict[str, str]] = []
    for path in visible:
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle in content:
                hits.append({"path": str(path), "hidden_identifier": needle})
    return hits


def participant_strategy_leakage_hits(case_dir: Path) -> list[dict[str, str]]:
    """Reject public prose that directly prescribes hidden control strategy."""
    path = case_dir / "task" / "task.yaml"
    if not path.is_file():
        return []
    content = path.read_text(encoding="utf-8", errors="replace").lower()
    return [
        {"path": str(path), "procedural_hint": pattern}
        for pattern in PROCEDURAL_LEAKAGE_PATTERNS
        if pattern in content
    ]


def write_dynamic_registry(
    case_dir: Path, points: list[dict[str, Any]],
    event_contracts: list[dict[str, Any]],
) -> None:
    """Write the evaluator registry and its private design ledger atomically enough for scaffolding."""
    errors = [
        *validate_event_contracts(event_contracts),
        *validate_dynamic_point_plan(points, event_contracts=event_contracts),
    ]
    if errors:
        raise ValueError(f"invalid dynamic point plan: {errors}")
    registry_path = case_dir / "task" / "tests" / "control_flow_checks.json"
    private_path = case_dir / "private" / "dynamic_point_plan.json"
    private_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": DYNAMIC_REGISTRY_VERSION,
        "event_contracts": event_contracts,
        "checks": points,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    registry_path.write_text(rendered, encoding="utf-8")
    private_path.write_text(rendered, encoding="utf-8")
