"""Task-causal Case IR and compiler for case-specific score plans.

The IR is the production boundary between trajectory screening/review and the
runtime benchmark bundle.  Event templates contribute obligations and mutation
families; the task graph contributes the actual requirements, affected scope,
preservation boundary and observable evidence.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from .event_policies import EVENT_POLICIES, EVENT_POLICY_VERSION, validate_event_policy_binding


CASE_IR_VERSION = "1"
SCORE_PLAN_VERSION = "1"
STAGE_TAGS = frozenset({"event_intake", "state_revision", "plan_revision", "closure"})


def _ids(items: Any) -> list[str]:
    return [str(item.get("id") or "") for item in items or [] if isinstance(item, dict)]


def dependency_descendants(graph: dict[str, Any], changed: set[str]) -> set[str]:
    children: dict[str, set[str]] = defaultdict(set)
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict) or edge.get("relation") not in {
            "depends_on", "derived_from", "invalidates",
        }:
            continue
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        if source and target:
            children[source].add(target)
    seen = set(changed)
    queue = deque(changed)
    while queue:
        current = queue.popleft()
        for child in children.get(current, set()):
            if child not in seen:
                seen.add(child)
                queue.append(child)
    return seen


def validate_case_ir(ir: Any) -> list[str]:
    if not isinstance(ir, dict):
        return ["case_ir must be an object"]
    errors: list[str] = []
    if str(ir.get("schema_version") or "") != CASE_IR_VERSION:
        errors.append(f"case_ir.schema_version must be {CASE_IR_VERSION!r}")
    for field in ("case_id", "instance_id", "task_archetype"):
        if not str(ir.get(field) or "").strip():
            errors.append(f"case_ir.{field} is required")
    requirements = ir.get("task_requirements")
    if not isinstance(requirements, list) or not requirements:
        errors.append("case_ir.task_requirements must be a non-empty list")
        requirements = []
    requirement_ids = _ids(requirements)
    if any(not value for value in requirement_ids) or len(set(requirement_ids)) != len(requirement_ids):
        errors.append("task requirement ids must be non-empty and unique")
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            continue
        for field in ("description", "public_evidence", "observable_probe"):
            if not requirement.get(field):
                errors.append(f"task_requirements[{index}].{field} is required")

    graph = ir.get("dependency_graph")
    if not isinstance(graph, dict):
        errors.append("case_ir.dependency_graph must be an object")
        graph = {}
    node_ids = _ids(graph.get("nodes"))
    if any(not value for value in node_ids) or len(set(node_ids)) != len(node_ids):
        errors.append("dependency graph node ids must be non-empty and unique")
    node_set = set(node_ids)
    for index, edge in enumerate(graph.get("edges") or []):
        if not isinstance(edge, dict):
            errors.append(f"dependency_graph.edges[{index}] must be an object")
            continue
        endpoints = {str(edge.get("source") or ""), str(edge.get("target") or "")}
        if "" in endpoints or not endpoints <= node_set:
            errors.append(f"dependency_graph.edges[{index}] references unknown nodes")

    event = ir.get("event_contract")
    if not isinstance(event, dict):
        errors.append("case_ir.event_contract must be an object")
        event = {}
    for field in ("event_id", "primary_event_theme", "before_state", "after_state"):
        if not str(event.get(field) or "").strip():
            errors.append(f"event_contract.{field} is required")
    affected = set(map(str, event.get("affected_nodes") or []))
    unaffected = set(map(str, event.get("unaffected_nodes") or []))
    if not affected:
        errors.append("event_contract.affected_nodes must be non-empty")
    if (affected | unaffected) - node_set:
        errors.append("event contract references unknown dependency nodes")
    if affected & unaffected:
        errors.append("affected_nodes and unaffected_nodes must be disjoint")
    closure = dependency_descendants(graph, affected)
    declared_closure = set(map(str, event.get("affected_closure") or []))
    if declared_closure != closure:
        errors.append(
            f"event_contract.affected_closure must equal the computed dependency closure {sorted(closure)!r}"
        )

    decisions = ir.get("decision_contracts")
    if not isinstance(decisions, list) or not decisions:
        errors.append("case_ir.decision_contracts must be a non-empty list")
        decisions = []
    decision_ids = _ids(decisions)
    if any(not value for value in decision_ids) or len(set(decision_ids)) != len(decision_ids):
        errors.append("decision contract ids must be non-empty and unique")
    obligations: set[str] = set()
    mutation_families: set[str] = set()
    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            errors.append(f"decision_contracts[{index}] must be an object")
            continue
        obligations.add(str(decision.get("obligation") or ""))
        mutation_families.add(str(decision.get("mutation_family") or ""))
        for field in (
            "obligation", "stage_tag", "task_requirement_id", "required_behavior",
            "forbidden_behavior", "primary_evidence", "outcome_anchors",
            "mutation_family", "gate", "gate_args",
        ):
            if not decision.get(field):
                errors.append(f"decision_contracts[{index}].{field} is required")
        if decision.get("stage_tag") not in STAGE_TAGS:
            errors.append(f"decision_contracts[{index}].stage_tag is invalid")
        if str(decision.get("task_requirement_id") or "") not in set(requirement_ids):
            errors.append(f"decision_contracts[{index}] references an unknown task requirement")
        if not decision.get("must_still_pass"):
            errors.append(
                f"decision_contracts[{index}].must_still_pass is required to prove mutation locality"
            )
    errors.extend(validate_event_policy_binding(
        str(event.get("primary_event_theme") or ""), obligations,
    ))
    policy = EVENT_POLICIES.get(str(event.get("primary_event_theme") or "")) or {}
    unknown_mutations = sorted(
        mutation_families - set(policy.get("mutation_families") or set())
    )
    if unknown_mutations:
        errors.append(
            f"decision contracts use mutation families outside the event policy: {unknown_mutations!r}"
        )
    return errors


def validate_score_plan(plan: Any) -> list[str]:
    if not isinstance(plan, dict):
        return ["score_plan must be an object"]
    errors: list[str] = []
    points = plan.get("points") or []
    mutations = plan.get("negative_mutations") or []
    point_ids = _ids(points)
    mutation_ids = _ids(mutations)
    if not points or len(set(point_ids)) != len(point_ids):
        errors.append("score plan point ids must be non-empty and unique")
    if len(mutations) != len(points) or len(set(mutation_ids)) != len(mutation_ids):
        errors.append("score plan requires one unique directional mutation per point")
    mutation_by_id = {str(item.get("id")): item for item in mutations if isinstance(item, dict)}
    for point in points:
        mutation_id = str(point.get("mutation_id") or "")
        mutation = mutation_by_id.get(mutation_id)
        if mutation is None:
            errors.append(f"point {point.get('id')!r} has no matching directional mutation")
            continue
        must_fail = set(map(str, mutation.get("must_fail") or []))
        must_still_pass = set(map(str, mutation.get("must_still_pass") or []))
        if str(point.get("id")) not in must_fail:
            errors.append(f"mutation {mutation_id!r} does not target its point")
        if not must_still_pass:
            errors.append(f"mutation {mutation_id!r} has no locality-preservation assertion")
        if must_fail & must_still_pass:
            errors.append(f"mutation {mutation_id!r} has overlapping fail/pass assertions")
    return errors


def compile_score_plan(ir: dict[str, Any], prefix: str) -> dict[str, Any]:
    errors = validate_case_ir(ir)
    if errors:
        raise ValueError(f"invalid Case IR: {errors}")
    event = ir["event_contract"]
    points: list[dict[str, Any]] = []
    mutations: list[dict[str, Any]] = []
    primary_fact_by_gate = {
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
    for decision in ir["decision_contracts"]:
        point_id = f"{prefix}.cf.{decision['id']}"
        mutation_id = f"{prefix}.mutation.{decision['id']}"
        gate = str(decision["gate"])
        points.append({
            "id": point_id,
            "gate": gate,
            "dimension": decision["stage_tag"],
            "event_id": event["event_id"],
            "decision_group": decision.get("decision_group") or decision["obligation"],
            "task_requirement_id": decision["task_requirement_id"],
            "obligation": decision["obligation"],
            "precondition": decision.get("precondition") or "The evaluator-owned event opportunity exists.",
            "expected_behavior": decision["required_behavior"],
            "forbidden_behavior": decision["forbidden_behavior"],
            "primary_evidence": decision["primary_evidence"],
            "mutation_id": mutation_id,
            "independence_key": decision.get("independence_key") or point_id,
            "evidence_group": decision.get("evidence_group") or f"{prefix}.{decision['obligation']}",
            "evidence_spec": {
                "primary_fact": primary_fact_by_gate.get(gate, str(decision.get("primary_fact") or "")),
                "subject": decision.get("evidence_subject") or decision["task_requirement_id"],
            },
            "precondition_contract": {
                "required_facts": decision.get("required_facts") or ["authority_delivery"],
                "on_missing": "fail_point",
            },
            "requires_outcome_anchor": False,
            "gate_args": decision["gate_args"],
            "outcome_anchors": list(decision["outcome_anchors"]),
            "critical": bool(decision.get("critical")),
            "measurement_type": "control",
            # Compatibility-only reporting field; it is not an authoring axis.
            "capability_target": "async_dynamic_replanning",
            "relevance_tier": "critical" if decision.get("critical") else "direct",
            "execution_modes": ["async"],
        })
        mutations.append({
            "id": mutation_id,
            "family": decision["mutation_family"],
            "targets": [point_id, *map(str, decision["outcome_anchors"])],
            "must_fail": [point_id],
            "may_fail": list(map(str, decision.get("may_fail") or [])),
            "must_still_pass": list(map(str, decision["must_still_pass"])),
            "error_mechanism": decision["forbidden_behavior"],
        })
    plan = {
        "schema_version": SCORE_PLAN_VERSION,
        "case_ir_version": CASE_IR_VERSION,
        "event_policy_version": EVENT_POLICY_VERSION,
        "case_id": ir["case_id"],
        "instance_id": ir["instance_id"],
        "primary_event_theme": event["primary_event_theme"],
        "points": points,
        "negative_mutations": mutations,
    }
    plan_errors = validate_score_plan(plan)
    if plan_errors:
        raise ValueError(f"invalid compiled score plan: {plan_errors}")
    return plan


def write_case_ir(case_dir: Path, ir: dict[str, Any], prefix: str) -> dict[str, Any]:
    plan = compile_score_plan(ir, prefix)
    private = case_dir / "private"
    private.mkdir(parents=True, exist_ok=True)
    (private / "case_ir.json").write_text(
        json.dumps(ir, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    (private / "score_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return plan
