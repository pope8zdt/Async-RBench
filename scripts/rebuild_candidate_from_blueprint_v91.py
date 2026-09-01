#!/usr/bin/env python3
"""Rebind one runnable candidate to its individualized V9.1 design.

The source-native finalizers produced executable packages, but several copied
the Case IR, semantic IDs, and control registry from their seed package.  This
tool keeps the case-owned runtime/tests and replaces only the authoring layer
with the reviewed per-case blueprint.  It is deliberately one-case-at-a-time
so the production queue can repair, validate, and promote independently.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from async_rbench.event_policies import EVENT_POLICIES, validate_event_policy_binding
from async_rbench.evaluation.weighting import GATE_DYNAMIC_DIMENSIONS
from async_rbench.dynamic_points import GATE_PRIMARY_FACTS
from candidate_write_guard import guard_for_root


ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    return value


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def control_prefix(case_dir: Path) -> str:
    registry = load(case_dir / "task/tests/control_flow_checks.json")
    checks = list(registry.get("checks") or [])
    if not checks:
        digest = hashlib.sha256(case_dir.name.encode()).hexdigest()[:6]
        return f"{slug(case_dir.name)[:15]}_{digest}"
    point_id = str(checks[0].get("id") or "")
    if ".cf." not in point_id:
        raise ValueError(f"{case_dir}: cannot infer control prefix from {point_id!r}")
    return point_id.split(".cf.", 1)[0]


def rebind_semantic_ids(case_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    path = case_dir / "task/tests/semantic_checks.json"
    registry = load(path)
    desired_prefix = slug(case_dir.name)
    mapping: dict[str, str] = {}
    for point in registry.get("checks") or []:
        old = str(point.get("id") or "")
        suffix = old.split(".", 1)[1] if "." in old else old
        new = f"{desired_prefix}.{suffix}"
        mapping[old] = new
        point["id"] = new
    ids = [str(point["id"]) for point in registry.get("checks") or []]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{case_dir}: semantic ID rebinding produced duplicates")
    dump(path, registry)
    return registry, mapping


def semantic_anchor_ids(semantic: dict[str, Any]) -> dict[str, str]:
    ids = [str(point["id"]) for point in semantic.get("checks") or []]
    def find(suffix: str, fallback: int) -> str:
        return next((value for value in ids if value.endswith(suffix)), ids[fallback])
    if not ids:
        raise ValueError("semantic registry has no checks")
    return {
        "event_intake": find(".event.receipt", 0),
        "state_revision": find(".event.probes", min(1, len(ids) - 1)),
        "plan_revision": find(".event.probes", min(1, len(ids) - 1)),
        "preservation": find(".source.pin", len(ids) - 1),
        "closure": find(".closure", min(2, len(ids) - 1)),
    }


def rebind_control_points(
    blueprint_points: list[dict[str, Any]], *, prefix: str, event_id: str,
    anchors: dict[str, str],
) -> list[dict[str, Any]]:
    default_gate_by_dimension = {
        "event_intake": "wait_for_authority",
        "state_revision": "resolve_authority",
        "plan_revision": "selective_replan",
        "closure": "rederive_from_authority",
    }
    points: list[dict[str, Any]] = []
    for index, original in enumerate(blueprint_points, 1):
        point = copy.deepcopy(original)
        old_id = str(point.get("id") or "")
        suffix = old_id.split(".cf.", 1)[1] if ".cf." in old_id else slug(old_id)
        point_id = f"{prefix}.cf.{suffix}"
        point["id"] = point_id
        point["independence_key"] = point_id
        point["mutation_id"] = f"{prefix}.mutation.{suffix}"
        point["event_id"] = event_id
        point["requires_outcome_anchor"] = False
        precondition = dict(point.get("precondition_contract") or {})
        precondition["on_missing"] = "fail_point"
        precondition.setdefault("required_facts", ["authority_delivery"])
        point["precondition_contract"] = precondition
        dimension = str(point.get("dimension") or "")
        if dimension not in {"event_intake", "state_revision", "plan_revision", "closure"}:
            raise ValueError(f"unsupported control-flow dimension: {dimension!r}")
        gate = str(point.get("gate") or "")
        if GATE_DYNAMIC_DIMENSIONS.get(gate) != dimension:
            # Some reviewed blueprints used the conflict-resolution gate for
            # both detecting and resolving a conflict.  The executable gate
            # contract distinguishes those decision stages: intake waits for
            # the competing authority, while arbitration revises state.
            point["gate"] = default_gate_by_dimension[dimension]
        evidence_spec = dict(point.get("evidence_spec") or {})
        evidence_spec["primary_fact"] = GATE_PRIMARY_FACTS[str(point["gate"])]
        point["evidence_spec"] = evidence_spec
        # The executable hidden verifier consumes stage_tag, while the scoring
        # layer groups the same point by dimension.  Keep both fields explicit
        # so a blueprint rebind cannot silently produce unmeasurable controls.
        point["stage_tag"] = dimension
        point["outcome_anchors"] = [anchors.get(dimension, anchors["closure"])]
        point["primary_evidence"] = (
            f"episode_trace:{dimension}:{point.get('obligation') or 'decision'}:{index}"
        )
        args = dict(point.get("gate_args") or {})
        artifact_aliases = {
            "preserve_prior": "preserved_source_facts",
            "preserved_state": "preserved_source_facts",
        }
        for field in ("artifacts", "preserve_artifacts"):
            if field in args:
                args[field] = [
                    artifact_aliases.get(str(value), str(value))
                    for value in args.get(field) or []
                ]
        point["gate_args"] = args
        point.setdefault("execution_modes", ["async"])
        point.setdefault("measurement_type", "control")
        point.setdefault("relevance_tier", "critical" if point.get("critical") else "direct")
        point.setdefault("evidence_group", f"{prefix}:{index}")
        points.append(point)
    ids = [str(point["id"]) for point in points]
    if len(ids) != len(set(ids)):
        raise ValueError("control ID rebinding produced duplicates")
    return points


def case_event_contract(
    candidate_private: dict[str, Any], blueprint_ir: dict[str, Any], points: list[dict[str, Any]],
) -> dict[str, Any]:
    blueprint_event = dict(blueprint_ir["event_contract"])
    prior = dict((candidate_private.get("event_contracts") or [{}])[0])
    theme = str(blueprint_event["primary_event_theme"])
    contract = {
        **prior,
        "event_id": str(blueprint_event["event_id"]),
        "event_theme": theme,
        "track": "dynamic_replanning" if len(points) >= 4 else "atomic_event",
        "observation_mode": "gateway_only",
        "main_visible_before_delivery": False,
        "state_delta": {
            "before": str(blueprint_event["before_state"]),
            "after": str(blueprint_event["after_state"]),
            "affected_artifacts": ["provisional_checkpoint", "final_state"],
            "unaffected_artifacts": ["preserved_source_facts"],
        },
        "required_opportunities": ["authority_delivery"],
    }
    arrival = dict(contract.get("arrival_contract") or {})
    arrival.setdefault("before_facts", ["provisional_checkpoint", "preserved_source_facts"])
    arrival.setdefault("after_facts", ["authority_delivery"])
    arrival.setdefault("after_artifacts", ["provisional_checkpoint", "preserved_source_facts"])
    contract["arrival_contract"] = arrival
    return contract


def rebind_scenario(private: dict[str, Any], *, old_event_id: str, event_id: str) -> None:
    events = list((((private.get("scenarios") or {}).get("async") or {}).get("events") or []))
    authority_kind = str(private.get("authoritative_result_kind") or "")
    old_roots = [event for event in events if str(event.get("id") or "") == old_event_id]
    authorities = [
        event for event in events
        if authority_kind and str(event.get("result") or "") == authority_kind
    ]
    if len(old_roots) != 1 or len(authorities) != 1:
        raise ValueError(
            f"expected one old root and one authority event, found "
            f"{len(old_roots)} and {len(authorities)}"
        )
    old_root, authority = old_roots[0], authorities[0]
    if old_root is not authority:
        # V9.0 sometimes split a non-result scope/resource stimulus from the
        # deliverable authority result. Fold both into one scoreable gateway
        # event while retaining the stimulus as metadata.
        authority_index = events.index(authority)
        merged = dict(authority)
        stimulus_type = str(old_root.get("type") or old_root.get("stimulus_type") or "")
        for key, value in old_root.items():
            if key not in {"id", "type", "result"}:
                merged[key] = value
        if stimulus_type and stimulus_type != "result_delivery":
            merged["stimulus_type"] = stimulus_type
        merged["id"] = old_event_id
        merged["result"] = authority_kind
        events = [event for event in events if event is not old_root and event is not authority]
        events.insert(min(authority_index, len(events)), merged)
    for event in events:
        current = str(event.get("id") or "")
        if current == old_event_id:
            event["id"] = event_id
        elif current.startswith(old_event_id + "."):
            event["id"] = event_id + current[len(old_event_id):]
    roots = [event for event in events if str(event.get("id") or "") == event_id]
    if len(roots) != 1:
        raise ValueError(f"expected one causal root event, found {len(roots)}")
    if authority_kind and str(roots[0].get("result") or "") != authority_kind:
        raise ValueError("causal root is not the authority-bearing result")
    private["scenarios"]["async"]["events"] = events


def negative_blueprint(points: list[dict[str, Any]], semantic: dict[str, Any]) -> list[dict[str, Any]]:
    semantic_ids = [str(item["id"]) for item in semantic.get("checks") or []]
    preservation = next(
        (point_id for point_id in semantic_ids if point_id.endswith(".source.pin")),
        semantic_ids[-1],
    )
    return [
        {
            "id": str(point["mutation_id"]),
            "family": str(point.get("gate") or point.get("obligation") or "control"),
            "error_mechanism": str(point["forbidden_behavior"]),
            "may_fail": [],
            "must_fail": [str(point["id"])],
            "must_still_pass": [preservation],
            "targets": [str(point["id"]), *semantic_ids[:4]],
        }
        for point in points
    ]


def mutation_suite(case_id: str, prefix: str, semantic: dict[str, Any], controls: list[dict[str, Any]]) -> dict[str, Any]:
    families: list[dict[str, Any]] = []
    for index, point in enumerate([*(semantic.get("checks") or []), *controls], 1):
        point_id = str(point["id"])
        label = slug(point_id.split(".")[-1])[:28] or f"point_{index:02d}"
        basis = str(point.get("description") or point.get("expected_behavior") or point_id)
        if point.get("measurement_type") == "control":
            kind = slug(str(point.get("gate") or point.get("obligation") or "control"))
            operation = f"mutate_control_{kind}"
            variants = [
                f"omit_{kind}_decision", f"apply_{kind}_to_wrong_scope",
                f"use_stale_evidence_for_{kind}", f"declare_{kind}_without_observation",
            ]
        else:
            kind = slug(str(point.get("category") or "semantic"))
            operation = f"mutate_semantic_{kind}"
            variants = [
                f"omit_{label}_evidence", f"corrupt_{label}_value",
                f"replay_stale_{label}_state", f"satisfy_manifest_without_{label}_behavior",
            ]
        families.append({
            "id": f"{prefix}.mut.{index:02d}_{label}", "case_id": case_id,
            "operation": operation, "description": f"Directly challenge: {basis}",
            "variants": variants, "must_fail": [point_id],
        })
        if point.get("critical") is True:
            families.append({
                "id": f"{prefix}.mut.{index:02d}_{label}_crosscheck", "case_id": case_id,
                "operation": f"cross_corrupt_{kind}_evidence",
                "description": f"Cross-check independent evidence for: {basis}",
                "variants": [
                    f"manifest_green_{label}_red", f"artifact_green_{label}_stale",
                    f"receipt_valid_{label}_foreign", f"partial_closure_hides_{label}_failure",
                ],
                "must_fail": [point_id],
            })
    return {"version": "1", "families": families}


def update_quality_contract(case_dir: Path, semantic: dict[str, Any], controls: list[dict[str, Any]]) -> None:
    path = case_dir / "private/quality_contract.yaml"
    quality = load(path)
    requirements = list(quality.get("requirements") or [])
    if not requirements:
        raise ValueError("quality contract has no requirements")
    covers = dict(requirements[0].get("covers") or {})
    covers["semantic_checks"] = [str(point["id"]) for point in semantic.get("checks") or []]
    covers["dynamic_control_checks"] = [str(point["id"]) for point in controls]
    requirements[0]["covers"] = covers
    semantic_ids = covers["semantic_checks"]
    receipt = next((value for value in semantic_ids if value.endswith(".event.receipt")), semantic_ids[0])
    closure = next((value for value in semantic_ids if value.endswith(".closure")), semantic_ids[-1])
    negatives = list(quality.get("negative_mutations") or [])
    if len(negatives) < 2:
        raise ValueError("quality contract must keep two executable negative mutations")
    if not negatives[0].get("must_fail"):
        negatives[0]["must_fail"] = [receipt]
    if not negatives[1].get("must_fail"):
        negatives[1]["must_fail"] = [closure]
    quality["negative_mutations"] = negatives
    quality["requirements"] = requirements
    dump(path, quality)


def rebuild(case_id: str, *, case_local_repair: bool = False, dry_run: bool = False) -> dict[str, Any]:
    guard = guard_for_root(ROOT, case_id, case_local_repair=case_local_repair)
    if dry_run:
        return {**guard, "dry_run": True, "writes_performed": False}
    case_dir = ROOT / "candidate_cases" / case_id
    blueprint_candidates = [
        ROOT / "candidate_cases/rebuild-to-100/blueprints" / case_id,
        ROOT / "candidate_cases/rebuild-to-200/blueprints" / case_id,
    ]
    blueprint = next((path for path in blueprint_candidates if path.is_dir()), blueprint_candidates[-1])
    if not case_dir.is_dir() or not blueprint.is_dir():
        raise FileNotFoundError(f"candidate or blueprint missing for {case_id}")
    semantic, semantic_mapping = rebind_semantic_ids(case_dir)
    prefix = control_prefix(case_dir)
    candidate_private = load(case_dir / "private/private_case.yaml")
    blueprint_ir = load(blueprint / "private/case_ir.json")
    blueprint_score = load(blueprint / "private/score_plan.json")
    declared = str((candidate_private.get("classification") or {}).get("primary_event_theme") or "")
    designed = str((blueprint_ir.get("event_contract") or {}).get("primary_event_theme") or "")
    if declared != designed:
        raise ValueError(f"semantic review required: runtime theme {declared!r} != blueprint {designed!r}")
    event_id = str(blueprint_ir["event_contract"]["event_id"])
    blueprint_points = list(
        blueprint_score.get("control_points") or blueprint_score.get("points") or []
    )
    points = rebind_control_points(
        blueprint_points, prefix=prefix,
        event_id=event_id, anchors=semantic_anchor_ids(semantic),
    )
    policy_errors = validate_event_policy_binding(
        declared, {str(point.get("obligation") or "") for point in points},
    )
    if policy_errors:
        raise ValueError("; ".join(policy_errors))
    old_event_id = str((candidate_private.get("event_contracts") or [{}])[0].get("event_id") or "")
    event_contract = case_event_contract(candidate_private, blueprint_ir, points)
    rebind_scenario(candidate_private, old_event_id=old_event_id, event_id=event_id)
    candidate_private["event_contracts"] = [event_contract]
    candidate_private["classification"]["primary_event_theme"] = declared
    dump(case_dir / "private/private_case.yaml", candidate_private)

    # Keep Case IR task-specific and align its decision contracts with the
    # executable control registry.
    case_ir = copy.deepcopy(blueprint_ir)
    case_ir["case_id"] = case_id
    for decision, point in zip(case_ir.get("decision_contracts") or [], points):
        decision["outcome_anchors"] = list(point["outcome_anchors"])
        decision["primary_evidence"] = str(point.get("primary_evidence") or "")
        decision["stage_tag"] = str(point["stage_tag"])
        decision["gate"] = str(point["gate"])
        decision["gate_args"] = copy.deepcopy(point.get("gate_args") or {})
    dump(case_dir / "private/case_ir.json", case_ir)

    negatives = negative_blueprint(points, semantic)
    score = {
        "semantic_points": list(semantic.get("checks") or []),
        "control_points": points,
        "negative_mutations": negatives,
    }
    dump(case_dir / "private/score_plan.json", score)
    control_registry = {
        "version": "7", "checks": points, "event_contracts": [event_contract],
    }
    dump(case_dir / "private/dynamic_point_plan.json", control_registry)
    dump(case_dir / "task/tests/control_flow_checks.json", control_registry)
    dump(case_dir / "mutation_families.json", mutation_suite(case_id, prefix, semantic, points))
    update_quality_contract(case_dir, semantic, points)

    # Keep authoring metadata honest after changing the package.
    status_path = case_dir / "STATUS.json"
    status = load(status_path)
    status.update({
        "status": "v9.1_design_rebound_pending_fresh_quality_validation",
        "v9_1_design_rebound": True,
        "quality_execution_passed": False,
        "fresh_quality_report": None,
    })
    dump(status_path, status)
    return {
        "case_id": case_id,
        "control_prefix": prefix,
        "theme": declared,
        "semantic_ids_rebound": len(semantic_mapping),
        "semantic_point_count": len(semantic.get("checks") or []),
        "control_point_count": len(points),
        "event_id": event_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--dry-run", action="store_true", help="check conflicts without writing")
    parser.add_argument("--case-local-repair", action="store_true", help="allow an unpublished, unconsumed existing candidate")
    parser.add_argument("--confirm-write", action="store_true", help="required for non-dry-run writes")
    args = parser.parse_args()
    if not args.dry_run and not args.confirm_write:
        parser.error("writing requires --confirm-write; use --dry-run to inspect")
    print(json.dumps(rebuild(args.case_id, case_local_repair=args.case_local_repair, dry_run=args.dry_run), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
