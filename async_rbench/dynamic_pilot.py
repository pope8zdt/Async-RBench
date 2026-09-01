from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from .dynamic_points import (
    participant_leakage_hits, participant_strategy_leakage_hits,
    write_dynamic_registry,
)
from .case_ir import dependency_descendants, write_case_ir
from .evaluation.registry_audit import validate_case_registries
from .spec import load_case, validate_case
from .pilot_case_specialization import (
    specialize_gaia_workflow,
    specialize_multi_source_workflow,
    specialize_nginx_workflow,
    specialize_secure_history_patch,
    specialize_secure_release_deploy,
)


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    """Replace a JSON state artifact atomically within its destination folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    temporary.replace(path)


def _point(
    prefix: str,
    name: str,
    gate: str,
    dimension: str,
    event_id: str,
    gate_args: dict[str, Any],
    anchors: list[str],
    *,
    expected: str,
    forbidden: str,
    evidence: str,
    critical: bool,
    evidence_group: str | None = None,
    required_facts: list[str] | None = None,
) -> dict[str, Any]:
    capability = {
        "event_intake": "async_result_integration",
        "state_revision": "async_dynamic_replanning",
        "plan_revision": "async_dynamic_replanning",
        "closure": "async_consistency_closure",
    }[dimension]
    primary_fact = {
        "wait_for_authority": "authority_consumption",
        "reject_late_stale": "stale_result_decision",
        "resolve_authority": "state_transition",
        "timely_cancellation": "cancellation",
        "selective_replan": "pre_post_replan",
        "rederive_from_authority": "closure_reverification",
    }[gate]
    args_subjects = [
        *list(gate_args.get("artifacts") or []),
        *list(gate_args.get("workstreams") or []),
    ]
    return {
        "id": f"{prefix}.cf.{name}",
        "gate": gate,
        "dimension": dimension,
        "event_id": event_id,
        "decision_group": name,
        "task_requirement_id": f"req.{name}",
        "obligation": name,
        "precondition": "Evaluator-issued event arrives after dependent work has started.",
        "expected_behavior": expected,
        "forbidden_behavior": forbidden,
        "primary_evidence": evidence,
        "mutation_id": f"{prefix}.mutation.{name}",
        "independence_key": f"{prefix}.{dimension}.{name}",
        "evidence_group": evidence_group or f"{prefix}.{primary_fact}.{name}",
        "evidence_spec": {
            "primary_fact": primary_fact,
            "subject": ",".join(map(str, args_subjects)) or name,
        },
        "precondition_contract": {
            "required_facts": required_facts or ["authority_delivery"],
            "on_missing": "fail_point",
        },
        "requires_outcome_anchor": False,
        "gate_args": gate_args,
        "outcome_anchors": anchors,
        "critical": critical,
        "measurement_type": "control",
        "capability_target": capability,
        "relevance_tier": "critical" if critical else "direct",
        "execution_modes": ["async"],
    }


def _gaia_points() -> list[dict[str, Any]]:
    p, event = "sm", "late_zip4_reply"
    return [
        _point(p, "consume_reply_before_saved_list", "wait_for_authority", "event_intake", event,
               {"artifacts": ["saved_list_artifact"], "workstreams": ["reply_monitor"]},
               ["zr.report.authority", "zr.late.remove_four"], critical=True,
               expected="Consume the late group reply before committing the final saved list.",
               forbidden="Finalize the saved list from the initial request only.",
               evidence="saved_list final commit sequence and authority completion lineage"),
        _point(p, "drop_stale_saved_list_lineage", "reject_late_stale", "state_revision", event,
               {"artifacts": ["saved_list_artifact"], "workstreams": ["initial_removal_planner"]},
               ["zr.late.remove_four", "zr.late.preserve_unaffected"], critical=False,
               expected="Remove stale planner lineage from the final saved-list revision.",
               forbidden="Mix superseded and authoritative revisions in the final saved list.",
               evidence="saved_list final lineage intersection with stale completion set",
               required_facts=["stale_completion"]),
        _point(p, "replan_saved_list_preserve_message", "selective_replan", "plan_revision", event,
               {"artifacts": ["saved_list_artifact"], "preserve_artifacts": ["group_message_artifact"], "workstreams": []},
               ["zr.message.preserve_initial", "zr.manifest.action_flags"], critical=False,
               expected="Recompute the invalidated saved list without redoing the unaffected group message.",
               forbidden="Fail to recompute the saved list or unnecessarily resend the group message.",
               evidence="saved-list recommit and group-message pre/post-boundary commit history",
               required_facts=["pre_event_affected_commit", "pre_event_unaffected_commit"]),
        _point(p, "close_saved_list_from_reply", "rederive_from_authority", "closure", event,
               {"artifacts": ["saved_list_artifact"], "workstreams": ["reply_monitor"]},
               ["zr.final.no_targeted_zip", "zr.manifest.revisions"], critical=True,
               expected="Close the saved list after invalidation with authority-derived lineage.",
               forbidden="Close using a pre-reply saved-list revision.",
               evidence="saved_list final authority lineage and invalidation boundary"),
        _point(p, "close_email_from_reply", "rederive_from_authority", "closure", event,
               {"artifacts": ["email_artifact"], "workstreams": ["reply_monitor"]},
               ["zr.email.exactly_one", "zr.manifest.closure"], critical=False,
               expected="Close the conditional email from the authoritative reply state.",
               forbidden="Emit an email without authority lineage or omit required closure.",
               evidence="email final authority lineage and commit after authority"),
    ]


def _nginx_points() -> list[dict[str, Any]]:
    p, event = "np", "np_a_port"
    return [
        _point(p, "consume_port_before_runtime", "wait_for_authority", "event_intake", event,
               {"artifacts": ["runtime_state"], "workstreams": []},
               ["np.authority.receipt", "np.runtime.index"], critical=True,
               expected="Consume the live port authority before committing nginx runtime state.",
               forbidden="Assume port 8080 ownership from configuration alone.",
               evidence="runtime_state commit sequence and port-authority lineage"),
        _point(p, "revise_runtime_owner", "resolve_authority", "state_revision", event,
               {"artifacts": ["runtime_state"], "workstreams": []},
               ["np.authority.conflict_detected", "np.authority.service_replaced"], critical=True,
               expected="Revise runtime ownership to the authority-observed conflict resolution.",
               forbidden="Retain the conflicting service or silently switch ports.",
               evidence="runtime_state pre/post authority transition",
               required_facts=["pre_event_affected_commit"]),
        _point(p, "replan_runtime_preserve_config", "selective_replan", "plan_revision", event,
               {"artifacts": ["runtime_state", "access_log"], "preserve_artifacts": ["nginx_config"], "workstreams": []},
               ["np.authority.service_replaced", "np.preserve.config"], critical=True,
               expected="Restart and reverify affected runtime/log state while preserving valid config.",
               forbidden="Skip runtime recomputation or rewrite unchanged configuration.",
               evidence="runtime/log recommits and nginx_config boundary commit history",
               required_facts=["pre_event_affected_commit", "pre_event_unaffected_commit"]),
        _point(p, "close_runtime_from_authority", "rederive_from_authority", "closure", event,
               {"artifacts": ["runtime_state"], "workstreams": []},
               ["np.runtime.index", "np.runtime.logged_probe"], critical=True,
               expected="Close runtime state after invalidation using authority lineage.",
               forbidden="Close a pre-conflict runtime snapshot.",
               evidence="runtime_state authority lineage and invalidation boundary"),
        _point(p, "close_lineage_from_authority", "rederive_from_authority", "closure", event,
               {"artifacts": ["service_lineage"], "workstreams": []},
               ["np.closure.authority", "np.closure.static_digests"], critical=False,
               expected="Close service lineage after invalidation from the port authority.",
               forbidden="Publish closure without authority-derived revalidation.",
               evidence="service_lineage authority lineage and invalidation boundary"),
    ]


def _multi_source_points() -> list[dict[str, Any]]:
    p, event = "ms", "ms_a_authority"
    return [
        _point(p, "consume_schema_authority", "wait_for_authority", "event_intake", event,
               {"artifacts": ["conflict_report"], "workstreams": ["schema_authority"]},
               ["ms.authority.conflict_schema", "ms.closure.lineage"], critical=True,
               expected="Consume the receipt-bound integer schema authority before final closure.",
               forbidden="Finalize from the provisional string-typed report observation.",
               evidence="conflict_report commit sequence and authority receipt lineage"),
        _point(p, "revise_conflict_schema", "resolve_authority", "state_revision", event,
               {"artifacts": ["conflict_report"], "workstreams": ["schema_authority"]},
               ["ms.authority.conflict_schema", "ms.authority.selection"], critical=True,
               expected="Resolve the provisional string type in favor of integer authority.",
               forbidden="Retain string user IDs or mix provisional and authoritative schemas.",
               evidence="conflict_report pre/post authority transition",
               required_facts=["pre_event_affected_commit"]),
        _point(p, "repair_report_preserve_dataset", "selective_replan", "plan_revision", event,
               {"artifacts": ["conflict_report"], "preserve_artifacts": ["merged_dataset"], "workstreams": []},
               ["ms.authority.conflict_schema", "ms.base.users_types"], critical=True,
               expected="Repair and reverify the report while preserving a correct merged dataset.",
               forbidden="Skip report repair or unnecessarily rebuild the unaffected dataset.",
               evidence="report recommit and dataset boundary digest",
               required_facts=["pre_event_affected_commit", "pre_event_unaffected_commit"]),
        _point(p, "close_report_from_authority", "rederive_from_authority", "closure", event,
               {"artifacts": ["conflict_report"], "workstreams": ["schema_authority"]},
               ["ms.authority.conflict_schema", "ms.authority.selection"], critical=True,
               expected="Close the conflict report from the authority-derived integer schema.",
               forbidden="Close a provisional or unverified conflict report.",
               evidence="final report authority lineage and invalidation boundary"),
        _point(p, "close_merge_lineage", "rederive_from_authority", "closure", event,
               {"artifacts": ["merge_lineage"], "workstreams": ["schema_authority"]},
               ["ms.closure.lineage", "ms.closure.digests"], critical=False,
               expected="Publish receipt-bound final digests after post-authority reverification.",
               forbidden="Publish lineage before authority or with stale digests.",
               evidence="merge_lineage receipt, digests and final commit boundary"),
    ]


def _secure_points() -> list[dict[str, Any]]:
    p, event = "sr", "sr_a_rewrite"
    return [
        _point(p, "consume_rewrite_before_patch", "wait_for_authority", "event_intake", event,
               {"artifacts": ["vulnerability_patch"], "workstreams": []},
               ["sr.stale.pre_rewrite_main_patch_rejected", "sr.patch.main_header_controls"], critical=True,
               expected="Consume sanitized-history authority before committing the final patch.",
               forbidden="Apply a patch tested only against pre-rewrite refs.",
               evidence="vulnerability_patch commit sequence and rewrite authority lineage"),
        _point(p, "reject_pre_rewrite_patch", "reject_late_stale", "state_revision", event,
               {"artifacts": ["vulnerability_patch"], "workstreams": ["security_patch"]},
               ["sr.stale.pre_rewrite_main_patch_rejected", "sr.stale.pre_rewrite_dev_patch_rejected"], critical=True,
               expected="Exclude the superseded security child completion from final patch lineage.",
               forbidden="Retain a pre-rewrite patch completion as authoritative.",
               evidence="vulnerability_patch lineage versus evaluator stale completion set",
               required_facts=["stale_completion"]),
        _point(p, "rebuild_patch_on_authority", "selective_replan", "plan_revision", event,
               {"artifacts": ["vulnerability_patch"], "preserve_artifacts": ["nginx_config"], "workstreams": []},
               ["sr.patch.main_header_controls", "sr.patch.dev_header_controls"], critical=True,
               expected="Rebuild or revalidate the security patch on the rewritten refs.",
               forbidden="Use a patch validated only on the superseded refs.",
               evidence="patch pre/post rewrite commits and preserved nginx digest",
               required_facts=["pre_event_affected_commit", "pre_event_unaffected_commit"]),
        _point(p, "close_patch_from_rewrite", "rederive_from_authority", "closure", event,
               {"artifacts": ["vulnerability_patch"], "workstreams": []},
               ["sr.patch.main_header_controls", "sr.patch.dev_header_controls"], critical=True,
               expected="Re-derive and verify the patch from sanitized final refs.",
               forbidden="Close patch verification from pre-rewrite inputs.",
               evidence="patch authority lineage, final-ref tests and invalidation boundary"),
        _point(p, "close_report_from_rewrite", "rederive_from_authority", "closure", event,
               {"artifacts": ["security_report"], "workstreams": []},
               ["sr.report.cwe93_exact"], critical=False,
               expected="Regenerate the security report from the sanitized and patched final refs.",
               forbidden="Publish a report derived from the superseded repository state.",
               evidence="report authority lineage, report-specific semantic anchors and boundary"),
        _point(p, "close_release_from_rewrite", "rederive_from_authority", "closure", event,
               {"artifacts": ["git_server", "release_manifest"], "workstreams": []},
               ["sr.lineage.sanitized_head_reachable", "sr.lineage.deployed_ref_consistency"], critical=False,
               expected="Close deployment and manifest from sanitized authority state.",
               forbidden="Close release with old refs or before post-rewrite recommit.",
               evidence="git_server/release_manifest authority lineage and invalidation boundary"),
    ]


def _history_patch_points() -> list[dict[str, Any]]:
    p, event = "hp", "hp_a_rewrite"
    return [
        _point(p, "consume_rewrite_before_final_patch", "wait_for_authority", "event_intake", event,
               {"artifacts": ["vulnerability_patch"], "workstreams": []},
               ["hp.authority.final_main_baseline", "hp.patch.main_header_controls"], critical=True,
               expected="Consume rewritten-history authority before the final patch commit.",
               forbidden="Finalize a patch against only the provisional refs.",
               evidence="final patch commit sequence and authoritative completion lineage"),
        _point(p, "revise_patch_for_rewritten_refs", "resolve_authority", "state_revision", event,
               {"artifacts": ["vulnerability_patch"], "workstreams": []},
               ["hp.stale.pre_rewrite_main_patch_rejected", "hp.stale.pre_rewrite_dev_patch_rejected"], critical=True,
               expected="Replace the provisional patch state after rewritten refs arrive.",
               forbidden="Keep the provisional patched refs as final truth.",
               evidence="evaluator-observed patch digest before and after authority",
               required_facts=["pre_event_affected_commit"]),
        _point(p, "rebuild_report_preserve_secret", "selective_replan", "plan_revision", event,
               {"artifacts": ["vulnerability_patch", "security_report"],
                "preserve_artifacts": ["security_test"], "workstreams": []},
               ["hp.report.cwe93_exact", "hp.patch.valid_header_regression"], critical=True,
               expected="Rebuild patch-derived outputs while preserving the independent regression test.",
               forbidden="Skip report rebuilding or overwrite the reusable regression test.",
               evidence="affected recommits and preserved regression-test digest across the event",
               required_facts=["pre_event_affected_commit", "pre_event_unaffected_commit"]),
        _point(p, "close_patch_from_authority", "rederive_from_authority", "closure", event,
               {"artifacts": ["vulnerability_patch"], "workstreams": []},
               ["hp.patch.main_header_controls", "hp.patch.dev_header_controls"], critical=True,
               expected="Verify the final patch on both authoritative refs.",
               forbidden="Close from pre-rewrite verification only.",
               evidence="final patch authority lineage and final-ref tests"),
        _point(p, "close_report_from_authority", "rederive_from_authority", "closure", event,
               {"artifacts": ["security_report"], "workstreams": []},
               ["hp.report.cwe93_exact"], critical=False,
               expected="Close the report from the authoritative patched state.",
               forbidden="Publish only the provisional report revision.",
               evidence="report authority lineage and post-event commit"),
    ]


def _release_deploy_points() -> list[dict[str, Any]]:
    p, event = "rd", "rd_a_authority"
    return [
        _point(p, "consume_authority_before_final_deploy", "wait_for_authority", "event_intake", event,
               {"artifacts": ["git_server", "release_manifest"], "workstreams": []},
               ["rd.authority.final_main_baseline", "rd.remote.final_refs"], critical=True,
               expected="Consume authoritative release refs before final deployment closure.",
               forbidden="Treat the provisional deployment as final.",
               evidence="final deploy/manifest sequence and authority lineage"),
        _point(p, "replace_provisional_deployment", "resolve_authority", "state_revision", event,
               {"artifacts": ["git_server"], "workstreams": []},
               ["rd.stale.old_deployment_rejected", "rd.runtime.http_main"], critical=True,
               expected="Replace provisional bare refs and deployed content after authority.",
               forbidden="Leave the pre-authority refs deployed.",
               evidence="git_server digest transition across authority",
               required_facts=["pre_event_affected_commit"]),
        _point(p, "redeploy_preserve_nginx", "selective_replan", "plan_revision", event,
               {"artifacts": ["git_server", "release_manifest"],
                "preserve_artifacts": ["nginx_config"], "workstreams": []},
               ["rd.remote.final_refs", "rd.support.nginx_config"], critical=True,
               expected="Redeploy changed refs while preserving independent nginx configuration.",
               forbidden="Skip redeployment or unnecessarily rewrite the independent HTTP service.",
               evidence="deploy/manifest recommits and stable nginx digest",
               required_facts=["pre_event_affected_commit", "pre_event_unaffected_commit"]),
        _point(p, "close_runtime_from_authority", "rederive_from_authority", "closure", event,
               {"artifacts": ["git_server"], "workstreams": []},
               ["rd.runtime.http_main", "rd.runtime.http_dev"], critical=True,
               expected="Close HTTPS runtime from final authoritative refs.",
               forbidden="Close runtime from provisional branch contents.",
               evidence="git server authority lineage and live endpoint checks"),
        _point(p, "close_manifest_from_authority", "rederive_from_authority", "closure", event,
               {"artifacts": ["release_manifest"], "workstreams": []},
               ["rd.lineage.deployed_ref_consistency"], critical=False,
               expected="Close manifest with authoritative local and remote refs.",
               forbidden="Retain provisional ref ids in the manifest.",
               evidence="manifest authority lineage and ref consistency"),
    ]


def _event_contract(
    event_id: str, theme: str, *, affected: list[str], unaffected: list[str],
    opportunities: list[str], trigger_after: list[str],
    trigger_after_results: list[str] | None = None,
    observation_mode: str = "gateway_only",
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_theme": theme,
        "track": "dynamic_replanning",
        "authority_source": "evaluator-controlled event delivery",
        "observation_mode": observation_mode,
        "main_visible_before_delivery": observation_mode != "gateway_only",
        "state_delta": {
            "before": f"pre-{event_id} provisional task state",
            "after": f"post-{event_id} authoritative task state",
            "affected_artifacts": affected,
            "unaffected_artifacts": unaffected,
        },
        "arrival_contract": {
            "after_facts": ["provisional affected work is evaluator-observed"],
            "before_facts": ["final closure is evaluator-observed"],
            "after_artifacts": trigger_after,
            "after_results": list(trigger_after_results or []),
        },
        "required_opportunities": opportunities,
    }


def _install_runtime_event_boundaries(
    case_dir: Path, contracts: list[dict[str, Any]],
) -> None:
    """Bind design-time arrival contracts to the private gateway schedule."""
    path = case_dir / "private" / "private_case.yaml"
    private = yaml.safe_load(path.read_text(encoding="utf-8"))
    events = ((private.get("scenarios") or {}).get("async") or {}).get("events") or []
    by_id = {str(event.get("id") or ""): event for event in events}
    missing: list[str] = []
    for contract in contracts:
        event_id = str(contract.get("event_id") or "")
        event = by_id.get(event_id)
        if event is None:
            missing.append(event_id)
            continue
        arrival = contract.get("arrival_contract") or {}
        after_artifacts = list(arrival.get("after_artifacts") or [])
        if not after_artifacts:
            raise ValueError(f"event {event_id!r} has no observable provisional checkpoint")
        event["trigger"] = "after_artifacts_committed"
        event["after_artifacts"] = after_artifacts
        event.pop("after_results", None)
        event.pop("at", None)
    if missing:
        raise ValueError(f"event contracts reference missing private events: {missing!r}")
    path.write_text(
        yaml.safe_dump(private, sort_keys=False, allow_unicode=True), encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha256(value: Any) -> str:
    """Hash a stage record so downstream stages can prove what they consumed."""
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _build_case_ir(
    destination: Path, item: dict[str, Any], case: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bind the reviewed event to task requirements and compile V7 points."""
    semantic_path = destination / "task/tests/semantic_checks.json"
    semantic = json.loads(semantic_path.read_text(encoding="utf-8"))
    semantic_checks = list(semantic.get("checks") or [])
    semantic_by_id = {str(check["id"]): check for check in semantic_checks}
    all_semantic_ids = list(semantic_by_id)
    requirements: list[dict[str, Any]] = []
    requirement_by_point: dict[str, str] = {}
    seen_requirements: set[str] = set()
    for point in item["points"]:
        anchors = list(map(str, point.get("outcome_anchors") or []))
        categories = {
            str(semantic_by_id.get(anchor, {}).get("category") or anchor)
            for anchor in anchors
        }
        category = sorted(categories)[0] if categories else str(point["id"])
        requirement_id = f"req.{category}"
        requirement_by_point[str(point["id"])] = requirement_id
        if requirement_id not in seen_requirements:
            descriptions = [
                str(semantic_by_id.get(anchor, {}).get("description") or anchor)
                for anchor in anchors
            ]
            requirements.append({
                "id": requirement_id,
                "description": "; ".join(descriptions),
                "criticality": "critical" if point.get("critical") else "direct",
                "public_evidence": [{"path": "task/task.yaml", "contains": "task outcome contract"}],
                "observable_probe": anchors,
            })
            seen_requirements.add(requirement_id)
    requirement_groups = {
        str(check.get("id")): f"req.{str(check.get('category') or check.get('id'))}"
        for check in semantic_checks
    }
    for check in semantic_checks:
        check["requirement_group"] = requirement_groups[str(check["id"])]
    semantic_path.write_text(
        json.dumps(semantic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    contract = item["event_contracts"][0]
    delta = contract["state_delta"]
    affected = list(map(str, delta.get("affected_artifacts") or []))
    unaffected = list(map(str, delta.get("unaffected_artifacts") or []))
    artifact_ids = {
        str(artifact.get("id")) for artifact in case.raw.get("artifacts") or []
    }
    node_ids = sorted(artifact_ids | set(affected) | set(unaffected) | seen_requirements)
    edges = []
    for point in item["points"]:
        requirement_id = requirement_by_point[str(point["id"])]
        subjects = list(map(str, (point.get("gate_args") or {}).get("artifacts") or []))
        for subject in subjects:
            if subject in affected:
                edges.append({
                    "source": subject, "target": requirement_id, "relation": "derived_from",
                })
    graph = {
        "nodes": [{
            "id": node_id,
            "kind": "requirement" if node_id.startswith("req.") else "artifact",
        } for node_id in node_ids],
        "edges": edges,
    }
    affected_closure = sorted(dependency_descendants(graph, set(affected)))
    decisions: list[dict[str, Any]] = []
    for point, obligation, mutation_family in zip(
        item["points"], item["obligations"], item["mutation_families"], strict=True,
    ):
        anchors = list(map(str, point.get("outcome_anchors") or []))
        must_still_pass = next(
            (semantic_id for semantic_id in all_semantic_ids if semantic_id not in anchors),
            anchors[0],
        )
        decisions.append({
            "id": str(point["id"]).split(".cf.", 1)[-1],
            "decision_group": obligation,
            "obligation": obligation,
            "stage_tag": point["dimension"],
            "task_requirement_id": requirement_by_point[str(point["id"])],
            "precondition": point["precondition"],
            "required_behavior": point["expected_behavior"],
            "forbidden_behavior": point["forbidden_behavior"],
            "primary_evidence": point["primary_evidence"],
            "outcome_anchors": anchors,
            "must_still_pass": [must_still_pass],
            "mutation_family": mutation_family,
            "gate": point["gate"],
            "gate_args": point["gate_args"],
            "critical": bool(point.get("critical")),
            "required_facts": list(
                (point.get("precondition_contract") or {}).get("required_facts")
                or ["authority_delivery"]
            ),
            "evidence_group": point.get("evidence_group"),
            "evidence_subject": (point.get("evidence_spec") or {}).get("subject"),
        })
    ir = {
        "schema_version": "1",
        "case_id": case.case_id,
        "instance_id": item["pilot_id"],
        "task_archetype": item["task_archetype"],
        "task_requirements": requirements,
        "dependency_graph": graph,
        "event_contract": {
            "event_id": contract["event_id"],
            "primary_event_theme": item["theme"],
            "before_state": delta["before"],
            "after_state": delta["after"],
            "authority": contract["authority_source"],
            "arrival_boundary": contract["arrival_contract"],
            "affected_nodes": affected,
            "unaffected_nodes": unaffected,
            "affected_closure": affected_closure,
        },
        "decision_contracts": decisions,
        "review": {
            "origin": "simulated_pipeline_validation",
            "promotion_eligible": False,
        },
    }
    return ir, write_case_ir(destination, ir, str(item["prefix"]))


def _remove_strategy_hints(case_dir: Path, pilot_id: str) -> None:
    """Remove control-policy coaching while preserving public outcome requirements."""
    task_path = case_dir / "task" / "task.yaml"
    content = task_path.read_text(encoding="utf-8")
    if pilot_id.startswith("pilot-gaia2"):
        content = content.replace(
            "  The benchmark has already started isolated readers, a removal planner and a reply monitor. Their observations may arrive in any order. The initial plan can become stale when the authoritative reply arrives. Preserve the completed group notification and unaffected properties, invalidate only the removal-dependent state, apply the revised prefix, then reopen final-state and conditional-email verification. Do not infer correctness from a preferred child completion order.\n",
            "  The benchmark has already started isolated readers, a removal planner and a reply monitor. Their observations may arrive in any order.\n",
        )
    elif pilot_id.startswith("pilot-nginx"):
        # Rewrite the parsed scalar rather than its serialized YAML. PyYAML may
        # wrap the sentence at a different column, which made the old literal
        # replacement silently retain participant strategy coaching.
        task = yaml.safe_load(content) or {}
        instruction = str(task.get("instruction") or "")
        instruction = instruction.replace(
            " Inspect delivered observations before accepting or promoting their files.",
            "",
        ).replace(
            "\nInspect delivered observations\nbefore accepting or promoting their files.",
            "",
        ).replace(
            " Inspect delivered observations\nbefore accepting or promoting their files.",
            "",
        )
        task["instruction"] = instruction
        task_path.write_text(
            yaml.safe_dump(task, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return
    elif pilot_id.startswith("pilot-secure"):
        content = content.replace(
            "  after the wave starts: wait, accept or reject deliveries, cancel work that is\n"
            "  no longer useful, and use spawn_subagent only to re-delegate a workstream whose\n"
            "  child must be rebuilt. The main agent remains responsible\n",
            "  after the wave starts. The main agent remains responsible\n",
        )
        content = content.replace(
            "  Results may complete in any order. Determine whether each result still\n"
            "  applies from its reported commit ids, tests and produced files; the prompt\n"
            "  does not identify a preferred completion. Preserve independent work and\n"
            "  revise only artifacts whose revision assumptions changed.\n",
            "  Results may complete in any order.\n",
        )
        content = content.replace(
            "  child's isolated inputs directly, so compare reported revisions before\n"
            "  integrating, update the official refs when appropriate, and verify the\n"
            "  security fix against the final refs rather than assuming an earlier test run\n"
            "  still applies.\n",
            "  child's isolated inputs directly. The final outputs must satisfy all public\n"
            "  requirements above.\n",
        )
    task_path.write_text(content, encoding="utf-8")


def _install_portable_case_wrappers(case_dir: Path, case_id: str) -> None:
    """Write wrappers that remain runnable after a case is moved into a batch.

    Candidate packages historically assumed a fixed ``parents[2]`` repository
    layout. Production adds several audit directories, so that assumption turns
    an otherwise valid case into an environment-level unscored episode.
    """
    bootstrap = (
        "from pathlib import Path\nimport sys\n"
        "for parent in Path(__file__).resolve().parents:\n"
        "    if (parent / 'async_rbench').is_dir():\n"
        "        sys.path.insert(0, str(parent))\n"
        "        break\n"
        "else:\n"
        "    raise RuntimeError('cannot locate Async-RBench repository root')\n"
    )
    wrappers = {
        "generate.py": (
            "from async_rbench.docker_case import export_task\n"
            f"if __name__ == '__main__': export_task(Path(__file__).resolve().parent, {case_id!r})\n"
        ),
        "oracle.py": (
            "from async_rbench.docker_case import run_oracle\n"
            f"if __name__ == '__main__': run_oracle({case_id!r})\n"
        ),
        "verify.py": (
            "from async_rbench.docker_case import run_verifier\n"
            f"if __name__ == '__main__': run_verifier({case_id!r})\n"
        ),
    }
    for name, body in wrappers.items():
        (case_dir / name).write_text(bootstrap + body, encoding="utf-8")


def build_dynamic_pilot_batch(
    root: Path, output: Path, human_review_path: Path | None = None,
) -> dict[str, Any]:
    """Build a non-promotable three-family development batch with a full audit trail."""
    if output.exists():
        raise FileExistsError(f"pilot output already exists: {output}")
    screening_dir = output / "01-agent-screening"
    review_dir = output / "02-simulated-human-review"
    production_dir = output / "03-case-production"
    design_dir = production_dir / "designs"
    cases_dir = production_dir / "cases"
    static_dir = output / "04-static-validation"
    for directory in (
        screening_dir, review_dir, production_dir, design_dir, cases_dir, static_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    definitions = [
        {
            "pilot_id": "pilot-gaia2-live-revision-001",
            "source": root / "candidate_instances/gaia2-stockholm-moveout/gaia2-zip-revision-sim-001",
            "source_benchmark": "GAIA2 structured environment",
            "source_trajectory": "pilot-review-008",
            "prefix": "sm",
            "theme": "task_scope_or_dependency_change",
            "scenario_class": "live_eventful",
            "task_archetype": "transactional_information_workflow",
            "experiment_selected": False,
            "specialize": specialize_gaia_workflow,
            "points": _gaia_points(),
            "obligations": [
                "classify_scope_delta", "revise_affected", "preserve_unaffected",
                "verify_closure", "verify_closure",
            ],
            "mutation_families": [
                "ignore_new_requirement", "under_invalidate", "over_invalidate",
                "skip_reverification", "ignore_new_requirement",
            ],
            "event_contracts": [_event_contract(
                "late_zip4_reply", "task_scope_or_dependency_change",
                affected=["saved_list_artifact", "email_artifact"],
                unaffected=["group_message_artifact"],
                opportunities=[
                    "stale_completion", "pre_event_affected_commit",
                    "pre_event_unaffected_commit",
                ],
                trigger_after=["saved_list_artifact", "group_message_artifact"],
            )],
        },
        {
            "pilot_id": "pilot-nginx-live-authority-001",
            "source": root / "candidate_cases/nginx-live-port-conflict",
            "source_benchmark": "Terminal-Bench",
            "source_trajectory": "terminus2-Anthropic__Claude-Sonnet-4-20250514-Thinking-nginx-request-logging-15fdb884",
            "prefix": "np",
            "theme": "conflicting_valid_results",
            "scenario_class": "live_eventful",
            "task_archetype": "systems_operations",
            "experiment_selected": True,
            "specialize": specialize_nginx_workflow,
            "points": _nginx_points(),
            "obligations": [
                "classify_conflict", "arbitrate_conflict", "arbitrate_conflict",
                "verify_closure", "verify_closure",
            ],
            "mutation_families": [
                "blind_first_result", "blind_last_result", "inconsistent_merge",
                "blind_first_result", "inconsistent_merge",
            ],
            "event_contracts": [_event_contract(
                "np_a_port", "conflicting_valid_results",
                affected=["runtime_state", "access_log", "service_lineage"],
                unaffected=["nginx_config", "site_content"],
                opportunities=[
                    "pre_event_affected_commit", "pre_event_unaffected_commit",
                ],
                trigger_after=[
                    "runtime_state", "access_log", "nginx_config", "site_content",
                ],
            )],
        },
        {
            "pilot_id": "pilot-multi-source-late-schema-001",
            "source": root / "upstream/terminal-bench/original-tasks-locked/multi-source-data-merger",
            "source_benchmark": "TraceBench / Terminal-Bench",
            "source_trajectory": "terminus2-DeepSeek__DeepSeek-V3.2-multi-source-data-merger-5ac42476",
            "prefix": "ms",
            "theme": "delayed_authoritative_result",
            "scenario_class": "result_eventful",
            "task_archetype": "data_integration",
            "experiment_selected": True,
            "specialize": specialize_multi_source_workflow,
            "points": _multi_source_points(),
            "obligations": [
                "classify_authority", "revise_affected", "preserve_unaffected",
                "verify_closure", "verify_closure",
            ],
            "mutation_families": [
                "ignore_authority", "retain_provisional", "retain_provisional",
                "skip_reverification", "skip_reverification",
            ],
            "event_contracts": [_event_contract(
                "ms_a_authority", "delayed_authoritative_result",
                affected=["conflict_report", "merge_lineage"],
                unaffected=["merged_dataset"],
                opportunities=["pre_event_affected_commit", "pre_event_unaffected_commit"],
                trigger_after=["merged_dataset", "conflict_report"],
            )],
        },
        {
            "pilot_id": "pilot-secure-history-patch-003",
            "source": root / "cases/secure-release/instances/tracebench-git-recovery-late-authority-001",
            "source_benchmark": "TraceBench / Terminal-Bench (history + patch)",
            "source_trajectory": "terminus2-OpenAI__GPT-5-git-leak-recovery-8156e2df",
            "prefix": "hp",
            "theme": "delayed_authoritative_result",
            "scenario_class": "result_eventful",
            "task_archetype": "repository_security",
            "experiment_selected": True,
            "specialize": specialize_secure_history_patch,
            "points": _history_patch_points(),
            "obligations": [
                "classify_authority", "revise_affected", "preserve_unaffected",
                "verify_closure", "verify_closure",
            ],
            "mutation_families": [
                "ignore_authority", "retain_provisional", "retain_provisional",
                "skip_reverification", "skip_reverification",
            ],
            "event_contracts": [_event_contract(
                "hp_a_rewrite", "late_or_out_of_order_superseded_result",
                affected=["vulnerability_patch", "security_report"],
                unaffected=["security_test"],
                opportunities=[
                    "pre_event_affected_commit", "pre_event_unaffected_commit",
                ],
                trigger_after=["vulnerability_patch", "security_report", "security_test"],
            )],
        },
        {
            "pilot_id": "pilot-secure-release-deploy-002",
            "source": root / "cases/secure-release/instances/tracebench-git-recovery-late-authority-001",
            "source_benchmark": "Terminal-Bench (Git/nginx release)",
            "source_trajectory": "git-multibranch-plus-nginx-request-logging",
            "prefix": "rd",
            "theme": "delayed_authoritative_result",
            "scenario_class": "result_eventful",
            "task_archetype": "release_operations",
            "experiment_selected": True,
            "specialize": specialize_secure_release_deploy,
            "points": _release_deploy_points(),
            "obligations": [
                "classify_authority", "revise_affected", "preserve_unaffected",
                "verify_closure", "verify_closure",
            ],
            "mutation_families": [
                "ignore_authority", "retain_provisional", "retain_provisional",
                "skip_reverification", "skip_reverification",
            ],
            "event_contracts": [_event_contract(
                "rd_a_authority", "delayed_authoritative_result",
                affected=["git_server", "release_manifest"],
                unaffected=["nginx_config"],
                opportunities=["pre_event_affected_commit", "pre_event_unaffected_commit"],
                trigger_after=["git_server", "nginx_config"],
            )],
        },
    ]
    external_reviews: dict[str, dict[str, Any]] | None = None
    if human_review_path is not None:
        review_bundle = json.loads(human_review_path.read_text(encoding="utf-8"))
        review_decisions = list(review_bundle.get("decisions") or [])
        accepted = [
            item for item in review_decisions
            if item.get("decision") == "candidate_confirmed"
        ]
        external_reviews = {
            str(item.get("pilot_id") or ""): item for item in accepted
        }
        if "" in external_reviews or len(external_reviews) != len(accepted):
            raise ValueError("human review has missing or duplicate accepted pilot_id values")
        known = {str(item["pilot_id"]): item for item in definitions}
        unknown = sorted(set(external_reviews) - set(known))
        if unknown:
            raise ValueError(f"human review accepted unknown pilot ids: {unknown}")
        for pilot_id, review in external_reviews.items():
            definition = known[pilot_id]
            if review.get("source_trajectory") != definition.get("source_trajectory"):
                raise ValueError(f"human review source mismatch for {pilot_id!r}")
            checks = review.get("review") or {}
            required_true = (
                "independent_result_source_valid", "prior_work_exists",
                "arrival_order_changes_required_response",
                "observable_semantic_consequence", "observable_control_consequence",
                "source_semantics_preserved",
            )
            if not all(checks.get(field) is True for field in required_true):
                raise ValueError(f"human review did not satisfy production criteria for {pilot_id!r}")
            if checks.get("ordinary_debugging_only") is not False:
                raise ValueError(f"human review marked {pilot_id!r} as ordinary debugging")
        definitions = [known[pilot_id] for pilot_id in external_reviews]
    # Stage 1: the agent screen is completed and persisted before any review or
    # case construction occurs.  The screen selects evidence cards, not cases.
    screening_rows: list[dict[str, Any]] = []
    for item in definitions:
        pilot_id = str(item["pilot_id"])
        screening_rows.append({
            "candidate_id": pilot_id,
            "source_benchmark": item["source_benchmark"],
            "source_trajectory": item["source_trajectory"],
            "hard_conditions": {
                "late_after_work_started": True,
                "independent_async_source": True,
                "plan_change_required": True,
                "observable_control_consequence": True,
                "source_evidence_retained": True,
                "not_ordinary_debugging": True,
            },
            "screening_decision": "review",
        })

    screening_path = screening_dir / "screening.jsonl"
    screening_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in screening_rows),
        encoding="utf-8",
    )

    # Stage 2: simulated human review consumes only agent-screened evidence
    # cards.  A review record is cryptographically bound to its exact input.
    review_rows: list[dict[str, Any]] = []
    for screen in screening_rows:
        candidate_id = str(screen["candidate_id"])
        if screen.get("screening_decision") != "review":
            continue
        hard_conditions = screen.get("hard_conditions") or {}
        confirmed = bool(hard_conditions) and all(
            value is True for value in hard_conditions.values()
        )
        external_review = (external_reviews or {}).get(candidate_id)
        if external_reviews is not None:
            confirmed = confirmed and external_review is not None
        review_rows.append({
            "candidate_id": candidate_id,
            "input_stage": "agent_screening",
            "screening_record_sha256": _json_sha256(screen),
            "review_origin": "simulated_pipeline_validation",
            "answers": {
                "late_after_work_started": "yes",
                "requires_plan_change": "yes",
                "evidence_is_faithful": "yes",
            },
            "decision": "candidate_confirmed" if confirmed else "candidate_rejected",
            "source_human_review_sha256": (
                _json_sha256(external_review) if external_review is not None else None
            ),
            "source_decision_id": (
                external_review.get("decision_id") if external_review is not None else None
            ),
            "promotion_eligible": False,
            "disclosure": "Simulation exercises mechanics only; independent human review is required.",
        })

    review_path = review_dir / "simulated-review.jsonl"
    review_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in review_rows),
        encoding="utf-8",
    )
    confirmed_reviews = {
        str(row["candidate_id"]): row
        for row in review_rows
        if row.get("decision") == "candidate_confirmed"
    }
    if len(confirmed_reviews) != sum(
        row.get("decision") == "candidate_confirmed" for row in review_rows
    ):
        raise ValueError("human review contains duplicate confirmed candidate ids")

    # Stage 3: production is fail-closed and can consume only a confirmed review.
    case_rows: list[dict[str, Any]] = []
    for item in definitions:
        pilot_id = str(item["pilot_id"])
        review = confirmed_reviews.get(pilot_id)
        if review is None:
            continue
        screen = next(
            row for row in screening_rows if row["candidate_id"] == pilot_id
        )
        if review.get("screening_record_sha256") != _json_sha256(screen):
            raise ValueError(
                f"review for {pilot_id!r} is not bound to the agent-screening input"
            )
        destination = cases_dir / pilot_id
        shutil.copytree(
            item["source"], destination,
            ignore=shutil.ignore_patterns(
                "instances", "review_evidence", "__pycache__", "*.pyc",
            ),
        )
        if item.get("specialize"):
            item["specialize"](destination)
        _remove_strategy_hints(destination, pilot_id)
        _install_runtime_event_boundaries(destination, item["event_contracts"])
        case = load_case(destination / "public_case.yaml")
        _install_portable_case_wrappers(destination, case.case_id)
        semantic_point_count = len(json.loads(
            (destination / "task/tests/semantic_checks.json").read_text(encoding="utf-8")
        ).get("checks") or [])
        case_ir, score_plan = _build_case_ir(destination, item, case)
        write_dynamic_registry(
            destination, score_plan["points"], item["event_contracts"],
        )
        design = {
            "schema_version": "dynamic-case-design-1",
            "pilot_id": pilot_id,
            "production_inputs": {
                "agent_screening_sha256": _json_sha256(screen),
                "human_review_sha256": _json_sha256(review),
                "human_review_decision": review["decision"],
            },
            "source_benchmark": item["source_benchmark"],
            "source_trajectory": item["source_trajectory"],
            "event_theme": item["theme"],
            "async_scenario_class": item["scenario_class"],
            "semantic_point_count": semantic_point_count,
            "dynamic_point_count": len(item["points"]),
            "dynamic_dimensions": {
                dimension: sum(point["dimension"] == dimension for point in item["points"])
                for dimension in ("event_intake", "state_revision", "plan_revision", "closure")
            },
            "simulation_only": True,
            "promotion_eligible": False,
            "requires_independent_human_rereview": True,
            "case_ir": case_ir,
            "dynamic_points": score_plan["points"],
            "negative_mutations": score_plan["negative_mutations"],
            "event_contracts": item["event_contracts"],
        }
        design_path = design_dir / f"{pilot_id}.json"
        design_path.write_text(
            json.dumps(design, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        (destination / "simulation_only.json").write_text(json.dumps({
            "simulation_only": True,
            "promotion_eligible": False,
            "requires_independent_human_rereview": True,
            "pilot_id": pilot_id,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        case = load_case(destination / "public_case.yaml")
        registry_errors = validate_case_registries({
            **case.raw,
            "_registry_path": str(destination / "task/tests/semantic_checks.json"),
            "_control_path": str(destination / "task/tests/control_flow_checks.json"),
        }, str(item["prefix"]))
        spec_errors = validate_case(case)
        leaks = participant_leakage_hits(destination, score_plan["points"])
        strategy_leaks = participant_strategy_leakage_hits(destination)
        case_rows.append({
            "pilot_id": pilot_id,
            "case_id": case.case_id,
            "source_benchmark": item["source_benchmark"],
            "source_trajectory": item["source_trajectory"],
            "experiment_selected": bool(item.get("experiment_selected", True)),
            "semantic_points": semantic_point_count,
            "dynamic_points": len(item["points"]),
            "dynamic_dimensions": design["dynamic_dimensions"],
            "registry_valid": not registry_errors,
            "case_contract_valid": not spec_errors,
            "runtime_qualification_status": "pending_new_execution",
            "participant_leakage_hits": leaks,
            "participant_strategy_leakage_hits": strategy_leaks,
            "errors": [*registry_errors, *spec_errors],
            "case_dir": str(destination.resolve()),
            "design_sha256": _sha256(design_path),
            "case_ir_path": str((destination / "private/case_ir.json").resolve()),
            "score_plan_path": str((destination / "private/score_plan.json").resolve()),
            "production_gate": {
                "agent_screened": True,
                "human_review_confirmed": True,
                "screening_record_sha256": _json_sha256(screen),
                "human_review_record_sha256": _json_sha256(review),
            },
        })

    # Stage 4: static validation is downstream of production and has its own
    # auditable artifact. Runtime feasibility and model experiments follow it.
    valid = all(
        row["registry_valid"] and row["case_contract_valid"]
        and not row["participant_leakage_hits"]
        and not row["participant_strategy_leakage_hits"]
        for row in case_rows
    ) and len(case_rows) == len(confirmed_reviews)
    static_report = {
        "schema_version": "dynamic-static-validation-1",
        "input_stage": "case_production",
        "produced_case_count": len(case_rows),
        "confirmed_review_count": len(confirmed_reviews),
        "valid": valid,
        "cases": [{
            "pilot_id": row["pilot_id"],
            "registry_valid": row["registry_valid"],
            "case_contract_valid": row["case_contract_valid"],
            "participant_leakage_hits": row["participant_leakage_hits"],
            "participant_strategy_leakage_hits": row["participant_strategy_leakage_hits"],
        } for row in case_rows],
    }
    static_report_path = static_dir / "static-gate.json"
    static_report_path.write_text(
        json.dumps(static_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = {
        "schema_version": "dynamic-pilot-batch-3",
        "valid": valid,
        "status": (
            "static_design_valid_runtime_qualification_required"
            if valid else "static_design_invalid"
        ),
        "runtime_qualified": False,
        "case_count": len(case_rows),
        "simulated_review": True,
        "promotion_eligible": False,
        "stage_order": [
            "agent_screening",
            "simulated_human_review",
            "case_production",
            "static_validation",
            "runtime_preflight",
            "linear_feasibility",
            "dual_model_experiment",
            "final_audit",
        ],
        "stage_artifacts": {
            "agent_screening": str(screening_path.resolve()),
            "simulated_human_review": str(review_path.resolve()),
            "case_production": str(production_dir.resolve()),
            "static_validation": str(static_report_path.resolve()),
            "runtime_preflight": None,
            "linear_feasibility": None,
            "dual_model_experiment": None,
            "final_audit": None,
        },
        "stage_status": {
            "agent_screening": "passed",
            "simulated_human_review": "passed",
            "case_production": "passed",
            "static_validation": "passed" if valid else "failed",
            "runtime_preflight": "pending",
            "linear_feasibility": "pending",
            "dual_model_experiment": "pending",
            "final_audit": "pending",
        },
        "policy": {
            "trajectory_is_oracle": False,
            "unique_action_sequence_required": False,
            "semantic_score_display_only": True,
            "dynamic_score_primary": True,
            "dynamic_registry_version": "7",
            "case_ir_version": "1",
            "score_unit": "causal_decision_group",
            "independent_human_review_required_before_release": True,
        },
        "cases": case_rows,
    }
    _atomic_write_json(output / "batch-report.json", report)
    return report


def preflight_dynamic_pilot_batch(batch: Path, *, seed: int = 20260829) -> dict[str, Any]:
    """Run the produced cases through build, Oracle and isolated verifier.

    This is a first-class pipeline stage. It consumes only a passing static
    batch, writes one canonical summary, and atomically advances the batch
    manifest so model experiments cannot silently skip runtime qualification.
    """
    report_path = batch / "batch-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("valid") is not True or (report.get("stage_status") or {}).get(
        "static_validation"
    ) != "passed":
        raise ValueError("runtime preflight requires a passing static-validation stage")
    output = batch / "05-runtime-preflight"
    if output.exists():
        existing_summary = output / "runtime-preflight.json"
        if existing_summary.is_file():
            existing = json.loads(existing_summary.read_text(encoding="utf-8"))
            if existing.get("passed") is True:
                report.setdefault("stage_status", {})["runtime_preflight"] = "passed"
                report.setdefault("stage_artifacts", {})["runtime_preflight"] = str(
                    existing_summary.resolve()
                )
                report["runtime_preflight_passed"] = True
                report["status"] = "runtime_preflight_valid_linear_qualification_required"
                _atomic_write_json(report_path, report)
                return existing
    else:
        output.mkdir(parents=True)
    rows: list[dict[str, Any]] = []
    selected = [
        row for row in report.get("cases") or [] if row.get("experiment_selected", True)
    ]
    for case_row in selected:
        pilot_id = str(case_row["pilot_id"])
        case_dir = Path(case_row["case_dir"])
        instance = output / "instances" / pilot_id
        verification = output / "reports" / f"{pilot_id}.json"
        verification.parent.mkdir(parents=True, exist_ok=True)
        commands = [
            [sys.executable, str(case_dir / "generate.py"), "--output", str(instance), "--seed", str(seed)],
            [sys.executable, str(case_dir / "oracle.py"), "--instance", str(instance)],
            [sys.executable, str(case_dir / "verify.py"), "--instance", str(instance), "--output", str(verification)],
        ]
        failed_command: list[str] | None = None
        exit_code: int | None = None
        output_tail = ""
        for command in commands:
            completed = subprocess.run(
                command, text=True, encoding="utf-8", errors="replace",
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            output_tail = completed.stdout[-4000:]
            if completed.returncode != 0:
                failed_command = command
                exit_code = completed.returncode
                break
        verification_report = {}
        if verification.is_file():
            verification_report = json.loads(verification.read_text(encoding="utf-8"))
        passed = failed_command is None and verification_report.get("success") is True
        rows.append({
            "pilot_id": pilot_id,
            "case_id": case_row["case_id"],
            "passed": passed,
            "instance": str(instance.resolve()),
            "verification_report": str(verification.resolve()),
            "verifier_bundle_sha256": verification_report.get("verifier_bundle_sha256"),
            "failed_command": failed_command,
            "exit_code": exit_code,
            "output_tail": output_tail if not passed else None,
        })
    summary = {
        "schema_version": "dynamic-runtime-preflight-1",
        "input_stage": "static_validation",
        "seed": seed,
        "expected_case_count": len(selected),
        "passed_case_count": sum(row["passed"] for row in rows),
        "passed": bool(selected) and all(row["passed"] for row in rows),
        "cases": rows,
    }
    summary_path = output / "runtime-preflight.json"
    _atomic_write_json(summary_path, summary)
    report.setdefault("stage_status", {})["runtime_preflight"] = (
        "passed" if summary["passed"] else "failed"
    )
    report.setdefault("stage_artifacts", {})["runtime_preflight"] = str(
        summary_path.resolve()
    )
    report["runtime_preflight_passed"] = summary["passed"]
    report["status"] = (
        "runtime_preflight_valid_linear_qualification_required"
        if summary["passed"] else "runtime_preflight_invalid"
    )
    by_pilot = {row["pilot_id"]: row for row in rows}
    for case_row in report.get("cases") or []:
        if case_row["pilot_id"] in by_pilot:
            case_row["runtime_qualification_status"] = (
                "preflight_passed" if by_pilot[case_row["pilot_id"]]["passed"]
                else "preflight_failed"
            )
    _atomic_write_json(report_path, report)
    return summary


def _participant_trace_leaks(case_dir: Path, trace_path: Path) -> list[dict[str, Any]]:
    registry = json.loads(
        (case_dir / "task/tests/control_flow_checks.json").read_text(encoding="utf-8")
    )
    needles = {
        str(value)
        for point in registry.get("checks") or []
        for value in (point.get("id"), point.get("mutation_id"))
        if value
    }
    # Only records sent to the participant are scanned. Private evaluator and
    # post-hoc score records coexist in trace.jsonl but are not participant-visible.
    outbound_types = {
        "episode_started", "result_delivered", "result_rejected",
        "capability_response", "verification_result",
    }
    hits: list[dict[str, Any]] = []
    for line_number, line in enumerate(trace_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("type") not in outbound_types:
            continue
        rendered = json.dumps(record, ensure_ascii=False, sort_keys=True)
        for needle in needles:
            if needle in rendered:
                hits.append({"line": line_number, "hidden_identifier": needle})
    return hits


def _causal_interruption_evidence(case_dir: Path, trace_path: Path) -> dict[str, Any]:
    """Prove the async interruption happened around a real committed state.

    A delayed result alone is not a useful benchmark intervention.  For a
    scenario using ``after_artifacts_committed``, every named checkpoint must
    exist before authority, delivery must not be a deadline fallback, and at
    least one invalidated artifact must therefore have a real pre-state. Whether
    the model successfully recommits it afterwards is a scored model outcome,
    not a benchmark-validity condition.
    """
    private = yaml.safe_load(
        (case_dir / "private/private_case.yaml").read_text(encoding="utf-8")
    ) or {}
    authority_kind = str(private.get("authoritative_result_kind") or "")
    events = ((private.get("scenarios") or {}).get("async") or {}).get("events") or []
    authority_event = next(
        (event for event in events if str(event.get("result") or "") == authority_kind),
        None,
    )
    if not authority_event or authority_event.get("trigger") != "after_artifacts_committed":
        return {
            "required": False, "passed": True,
            "reason": "case does not declare a committed-state interruption trigger",
        }
    records = [
        json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    authority = next((
        record for record in records
        if record.get("type") == "result_delivery_evaluator_fact"
        and str(record.get("result_kind") or "") == authority_kind
        and (
            not authority_event.get("id")
            or record.get("benchmark_event_id") == authority_event.get("id")
        )
    ), None)
    required_pre = {str(item) for item in authority_event.get("after_artifacts") or []}
    invalidated = {str(item) for item in authority_event.get("invalidates_artifacts") or []}
    if authority is None:
        return {
            "required": True, "passed": False,
            "reason": "authoritative delivery was not observed",
            "required_pre_artifacts": sorted(required_pre),
        }
    authority_seq = int(authority.get("seq") or 0)
    commits = [record for record in records if record.get("type") == "artifact_committed"]
    pre = {
        str(record.get("artifact_id")): record
        for record in commits if int(record.get("seq") or 0) < authority_seq
    }
    post = {
        str(record.get("artifact_id")): record
        for record in commits if int(record.get("seq") or 0) > authority_seq
    }
    missing_pre = sorted(required_pre - set(pre))
    affected_pre = invalidated & set(pre)
    missing_recommit = sorted(affected_pre - set(post))
    unchanged_recommit = sorted(
        artifact for artifact in affected_pre & set(post)
        if pre[artifact].get("observed_digest") == post[artifact].get("observed_digest")
    )
    fallback = authority.get("delivery_fallback_reason")
    scenario_class = str((private.get("classification") or {}).get("async_scenario_class") or "")
    intervention_contract = authority_event.get("intervention")
    intervention = next((
        record for record in records
        if record.get("type") == "intervention_applied"
        and record.get("benchmark_event_id") == authority_event.get("id")
    ), None)
    reasons: list[str] = []
    if fallback:
        reasons.append(f"authority used delivery fallback: {fallback}")
    if missing_pre:
        reasons.append(f"missing pre-authority checkpoints: {', '.join(missing_pre)}")
    if not affected_pre:
        reasons.append("no invalidated artifact had a pre-authority checkpoint")
    if scenario_class == "live_eventful":
        if not isinstance(intervention_contract, dict):
            reasons.append("live-event case lacks an evaluator-owned intervention contract")
        elif intervention is None:
            reasons.append("live intervention was not applied or observed")
        elif intervention.get("passed") is not True:
            reasons.append("live intervention failed its before/after state-change proof")
        else:
            required_changed = {
                str(value)
                for value in intervention_contract.get("required_changed_artifacts") or []
            }
            observed_changed = {
                str(value) for value in intervention.get("changed_artifacts") or []
            }
            missing_changes = sorted(required_changed - observed_changed)
            if missing_changes:
                reasons.append(
                    "live intervention did not change required state: "
                    + ", ".join(missing_changes)
                )
    return {
        "required": True,
        "passed": not reasons,
        "reason": "; ".join(reasons) if reasons else "real committed pre-state and authority invalidation observed",
        "authority_seq": authority_seq,
        "delivery_fallback_reason": fallback,
        "required_pre_artifacts": sorted(required_pre),
        "observed_pre_artifacts": sorted(pre),
        "invalidated_pre_artifacts": sorted(affected_pre),
        "observed_post_artifacts": sorted(post),
        "model_missing_post_authority_recommits": missing_recommit,
        "model_unchanged_post_authority_recommits": unchanged_recommit,
        "live_intervention_required": scenario_class == "live_eventful",
        "live_intervention_evidence": intervention,
    }


def audit_dynamic_pilot_batch(batch: Path) -> dict[str, Any]:
    """Aggregate GPT-5.4/DeepSeek pairs under the V7 task-causal policy."""
    report_path = batch / "batch-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    preflight_path = batch / "05-runtime-preflight" / "runtime-preflight.json"
    preflight = (
        json.loads(preflight_path.read_text(encoding="utf-8"))
        if preflight_path.is_file() else {}
    )
    preflight_passed = bool(
        preflight.get("passed") is True
        and (report.get("stage_status") or {}).get("runtime_preflight") == "passed"
    )
    model_dirs = {"gpt54": "GPT-5.4", "deepseek": "DeepSeek V4 Flash"}
    rows: list[dict[str, Any]] = []
    selected_cases = [
        row for row in (report.get("cases") or [])
        if row.get("experiment_selected", True)
    ]
    for case_row in selected_cases:
        pilot_id = str(case_row["pilot_id"])
        case_dir = Path(case_row["case_dir"])
        for directory, display_name in model_dirs.items():
            # Stage 5 is the evaluator-owned runtime preflight; real model
            # experiments follow it. Keep a legacy fallback for old pilot
            # batches, but never confuse preflight artifacts with model runs.
            run_root = batch / "06-runs"
            if not run_root.is_dir():
                run_root = batch / "05-runs"
            pair_path = run_root / directory / pilot_id / "pair-results.json"
            if not pair_path.is_file():
                rows.append({
                    "pilot_id": pilot_id, "case_id": case_row["case_id"],
                    "model": display_name, "status": "missing_run",
                })
                continue
            pair = json.loads(pair_path.read_text(encoding="utf-8"))
            score_paths = sorted((pair_path.parent / "episodes").glob("*/score.json"))
            scores = {
                str(score["execution_mode"]): score
                for path in score_paths
                for score in [json.loads(path.read_text(encoding="utf-8"))]
            }
            linear, async_score = scores.get("linear") or {}, scores.get("async") or {}
            trace_paths = sorted((pair_path.parent / "episodes").glob("*/trace.jsonl"))
            trace_leaks = [
                {"trace": str(path), **hit}
                for path in trace_paths for hit in _participant_trace_leaks(case_dir, path)
            ]
            async_trace_path = next(
                (path for path in trace_paths if path.parent.name.endswith("-async")), None,
            )
            causal_interruption = (
                _causal_interruption_evidence(case_dir, async_trace_path)
                if async_trace_path else {
                    "required": True, "passed": False,
                    "reason": "async trace is missing",
                }
            )
            linear_s, async_s = linear.get("semantic_task_score"), async_score.get("semantic_task_score")
            dynamic = async_score.get("dynamic_control_score")
            base_feasible = isinstance(linear_s, (int, float)) and linear_s >= 0.75
            linear_cost_ok = (
                int(linear.get("total_tokens") or 0) <= 500_000
                and float(linear.get("episode_duration_ms") or 0) <= 1_200_000
            )
            async_cost_ok = (
                int(async_score.get("total_tokens") or 0) <= 500_000
                and float(async_score.get("episode_duration_ms") or 0) <= 1_200_000
            )
            runtime_valid = bool(linear and async_score) and all(
                score.get("score_status") == "scored"
                and score.get("scenario_constructed") is True
                and score.get("scenario_exposure_complete") is True
                and score.get("protocol_valid") is True
                and not score.get("infrastructure_failures")
                for score in (linear, async_score)
            ) and async_score.get("dynamic_scenario_qualified") is not False
            runtime_valid = runtime_valid and causal_interruption.get("passed") is True
            dynamic_denominator_valid = (
                (async_score.get("control_flow_check_counts") or {}).get("applicable")
                == case_row["dynamic_points"]
            )
            discriminatory = isinstance(dynamic, (int, float)) and 0.05 < dynamic < 0.95
            if not runtime_valid:
                decision = "reject_or_rerun_runtime_invalid"
            elif not base_feasible or not linear_cost_ok or not async_cost_ok:
                decision = "reject_base_feasibility_or_cost"
            elif dynamic == 0:
                decision = "retain_for_more_models_dynamic_floor_risk"
            elif dynamic == 1:
                decision = "revise_or_test_more_models_ceiling_risk"
            else:
                decision = "retain_for_multi_model_calibration"
            rows.append({
                "pilot_id": pilot_id,
                "case_id": case_row["case_id"],
                "source_benchmark": case_row["source_benchmark"],
                "model": pair.get("model") or display_name,
                "status": pair.get("status"),
                "semantic_registry_points": case_row["semantic_points"],
                "dynamic_registry_points": case_row["dynamic_points"],
                "linear": {
                    "semantic_score": linear_s,
                    "semantic_passed": sum(
                        item.get("passed") is True for item in linear.get("semantic_check_results") or []
                    ),
                    "total_tokens": linear.get("total_tokens"),
                    "duration_ms": linear.get("episode_duration_ms"),
                },
                "async": {
                    "semantic_score": async_s,
                    "semantic_passed": sum(
                        item.get("passed") is True for item in async_score.get("semantic_check_results") or []
                    ),
                    "dynamic_score": dynamic,
                    "dt_score": async_score.get("dt_score"),
                    "dynamic_passed": (async_score.get("control_flow_check_counts") or {}).get("passed"),
                    "dynamic_applicable": (async_score.get("control_flow_check_counts") or {}).get("applicable"),
                    "decision_group_scores": async_score.get("dynamic_decision_group_scores"),
                    "stage_diagnostics": async_score.get("dynamic_dimension_scores"),
                    "total_tokens": async_score.get("total_tokens"),
                    "duration_ms": async_score.get("episode_duration_ms"),
                },
                "gates": {
                    "static_and_prompt_leakage": (
                        case_row["registry_valid"] and not case_row["participant_leakage_hits"]
                        and not case_row["participant_strategy_leakage_hits"]
                    ),
                    "participant_trace_leakage": not trace_leaks,
                    "runtime_valid": runtime_valid,
                    "causal_interruption_constructed": causal_interruption.get("passed") is True,
                    "dynamic_denominator_valid": dynamic_denominator_valid,
                    "linear_base_feasible": base_feasible,
                    "linear_cost_ok": linear_cost_ok,
                    "async_cost_ok": async_cost_ok,
                    "resource_comparable": linear_cost_ok and async_cost_ok,
                    "single_model_discriminatory": discriminatory,
                },
                "participant_trace_leakage_hits": trace_leaks,
                "causal_interruption_evidence": causal_interruption,
                "calibration_decision": decision,
            })
    complete_rows = [row for row in rows if row.get("status") == "completed"]
    qualified_rows = [
        row for row in complete_rows
        if (row.get("gates") or {}).get("runtime_valid") is True
        and (row.get("gates") or {}).get("linear_base_feasible") is True
        and (row.get("gates") or {}).get("linear_cost_ok") is True
        and (row.get("gates") or {}).get("async_cost_ok") is True
    ]
    model_aggregates: list[dict[str, Any]] = []
    for model_name in sorted({str(row["model"]) for row in qualified_rows}):
        model_rows = [row for row in qualified_rows if str(row["model"]) == model_name]

        def numeric_mean(path: tuple[str, str]) -> float | None:
            values = [
                row[path[0]].get(path[1])
                for row in model_rows
                if isinstance(row[path[0]].get(path[1]), (int, float))
            ]
            return sum(values) / len(values) if values else None

        model_aggregates.append({
            "model": model_name,
            "completed_cases": len(model_rows),
            "linear_semantic_macro": numeric_mean(("linear", "semantic_score")),
            "async_semantic_macro": numeric_mean(("async", "semantic_score")),
            "dynamic_macro": numeric_mean(("async", "dynamic_score")),
            "dt_macro": numeric_mean(("async", "dt_score")),
        })
    expected_runtime_rows = len(selected_cases) * len(model_dirs)
    runtime_batch_valid = (
        preflight_passed
        and
        len(rows) == expected_runtime_rows
        and all(
            row.get("status") == "completed"
            and (row.get("gates") or {}).get("runtime_valid") is True
            and (row.get("gates") or {}).get("linear_base_feasible") is True
            and (row.get("gates") or {}).get("linear_cost_ok") is True
            and (row.get("gates") or {}).get("async_cost_ok") is True
            for row in rows
        )
    )
    result = {
        "schema_version": "task-causal-pilot-audit-3",
        "batch_valid": report.get("valid") is True and runtime_batch_valid,
        "static_batch_valid": report.get("valid") is True,
        "runtime_batch_valid": runtime_batch_valid,
        "runtime_preflight_valid": preflight_passed,
        "candidate_case_count": len(report.get("cases") or []),
        "case_count": len(selected_cases),
        "model_case_run_count": len(complete_rows),
        "qualified_model_case_run_count": len(qualified_rows),
        "paper_release_eligible": False,
        "paper_release_blockers": [
            "simulated human review",
            "two pilot models are fewer than the pre-registered three-family minimum",
            "one seed per model is insufficient for score freeze",
        ],
        "calibration_policy": {
            "score_unit": "causal_decision_group",
            "lifecycle_stages_are_diagnostics": True,
            "linear_semantic_minimum": 0.75,
            "linear_total_tokens_maximum": 500_000,
            "linear_duration_ms_maximum": 1_200_000,
            "async_total_tokens_maximum": 500_000,
            "async_duration_ms_maximum": 1_200_000,
            "provisional_dynamic_window": [0.05, 0.95],
            "required_real_models_before_freeze": 5,
            "required_seeds_per_model_before_freeze": 3,
        },
        "model_aggregates": model_aggregates,
        "runs": rows,
    }
    audit_dir = batch / "07-audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    final_results_path = audit_dir / "final-results.json"
    _atomic_write_json(final_results_path, result)
    header = (
        "| Case | Model | Linear S | Async S | D passed | D | DT | Decision groups | Calibration |\n"
        "|---|---|---:|---:|---:|---:|---:|---|---|\n"
    )
    lines = [header]
    for row in rows:
        if row.get("status") != "completed":
            lines.append(f"| {row['pilot_id']} | {row['model']} | — | — | — | — | — | — | {row['status']} |\n")
            continue
        groups = row["async"]["decision_group_scores"] or {}
        dynamic_value = row["async"]["dynamic_score"]
        dt_value = row["async"]["dt_score"]
        dynamic_text = "N/A" if dynamic_value is None else f"{100 * float(dynamic_value):.2f}%"
        dt_text = "N/A" if dt_value is None else f"{100 * float(dt_value):.2f}%"
        group_text = ", ".join(f"{name}={100 * float(value):.0f}%" for name, value in groups.items())
        lines.append(
            f"| {row['pilot_id']} | {row['model']} | "
            f"{100 * float(row['linear']['semantic_score']):.2f}% "
            f"({row['linear']['semantic_passed']}/{row['semantic_registry_points']}) | "
            f"{100 * float(row['async']['semantic_score']):.2f}% "
            f"({row['async']['semantic_passed']}/{row['semantic_registry_points']}) | "
            f"{row['async']['dynamic_passed']}/{row['async']['dynamic_applicable']} | "
            f"{dynamic_text} | {dt_text} | {group_text} | "
            f"{row['calibration_decision']} |\n"
        )
    lines.append(
        "\n## Model macro averages\n\n"
        "| Model | Completed cases | Linear S | Async S | D | DT |\n"
        "|---|---:|---:|---:|---:|---:|\n"
    )
    for aggregate in model_aggregates:
        def percent(value: Any) -> str:
            return "N/A" if value is None else f"{100 * float(value):.2f}%"

        lines.append(
            f"| {aggregate['model']} | {aggregate['completed_cases']} | "
            f"{percent(aggregate['linear_semantic_macro'])} | "
            f"{percent(aggregate['async_semantic_macro'])} | "
            f"{percent(aggregate['dynamic_macro'])} | "
            f"{percent(aggregate['dt_macro'])} |\n"
        )
    (audit_dir / "RESULTS.md").write_text("".join(lines), encoding="utf-8")

    # batch-report.json is the canonical state machine, not a stale build-only
    # snapshot. Finalization is atomic so downstream readers cannot observe a
    # half-updated qualification state.
    stage_status = report.setdefault("stage_status", {})
    stage_status.setdefault("agent_screening", "passed")
    stage_status.setdefault("simulated_human_review", "passed")
    stage_status.setdefault("case_production", "passed")
    stage_status.setdefault(
        "static_validation", "passed" if report.get("valid") is True else "failed",
    )
    stage_status["runtime_preflight"] = "passed" if preflight_passed else "failed"
    complete_experiment = len(complete_rows) == expected_runtime_rows
    stage_status["linear_feasibility"] = (
        "passed" if complete_experiment and all(
            (row.get("gates") or {}).get("linear_base_feasible") is True
            and (row.get("gates") or {}).get("linear_cost_ok") is True
            for row in rows
        ) else "failed"
    )
    stage_status["dual_model_experiment"] = (
        "passed" if complete_experiment else "failed"
    )
    stage_status["final_audit"] = "passed" if result["batch_valid"] else "failed"
    stage_artifacts = report.setdefault("stage_artifacts", {})
    stage_artifacts["runtime_preflight"] = (
        str(preflight_path.resolve()) if preflight_path.is_file() else None
    )
    stage_artifacts["linear_feasibility"] = str(final_results_path.resolve())
    stage_artifacts["dual_model_experiment"] = str((batch / "06-runs").resolve())
    stage_artifacts["final_audit"] = str(final_results_path.resolve())
    report["runtime_qualified"] = result["batch_valid"]
    report["promotion_eligible"] = False
    report["status"] = "audit_valid" if result["batch_valid"] else "audit_invalid"
    stage_order = list(report.get("stage_order") or [])
    if "runtime_preflight" not in stage_order:
        insert_at = (
            stage_order.index("static_validation") + 1
            if "static_validation" in stage_order else len(stage_order)
        )
        stage_order.insert(insert_at, "runtime_preflight")
        report["stage_order"] = stage_order
    report["final_audit_summary"] = {
        "batch_valid": result["batch_valid"],
        "runtime_batch_valid": runtime_batch_valid,
        "qualified_model_case_run_count": len(qualified_rows),
        "expected_model_case_run_count": expected_runtime_rows,
        "artifact": str(final_results_path.resolve()),
    }
    _atomic_write_json(report_path, report)
    return result
