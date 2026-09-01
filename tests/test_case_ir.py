from __future__ import annotations

from async_rbench.case_ir import (
    compile_score_plan, dependency_descendants, validate_case_ir,
    validate_score_plan,
)
from async_rbench.event_policies import EVENT_POLICIES


def _ir():
    return {
        "schema_version": "1",
        "case_id": "demo",
        "instance_id": "demo-001",
        "task_archetype": "data_recovery",
        "task_requirements": [
            {
                "id": "req.final",
                "description": "final data is complete",
                "public_evidence": [{"path": "task/task.yaml", "contains": "complete"}],
                "observable_probe": ["d.final.complete"],
            },
        ],
        "dependency_graph": {
            "nodes": [
                {"id": "partial", "kind": "fact"},
                {"id": "final", "kind": "artifact"},
                {"id": "req.final", "kind": "requirement"},
            ],
            "edges": [
                {"source": "partial", "target": "final", "relation": "derived_from"},
                {"source": "final", "target": "req.final", "relation": "derived_from"},
            ],
        },
        "event_contract": {
            "event_id": "complete-arrives",
            "primary_event_theme": "partial_then_complete_result",
            "before_state": "partial result",
            "after_state": "complete result",
            "affected_nodes": ["partial"],
            "unaffected_nodes": [],
            "affected_closure": ["final", "partial", "req.final"],
        },
        "decision_contracts": [
            {
                "id": "classify",
                "obligation": "classify_completeness",
                "stage_tag": "event_intake",
                "task_requirement_id": "req.final",
                "required_behavior": "recognize completeness",
                "forbidden_behavior": "treat partial as final",
                "primary_evidence": "authority consumption",
                "outcome_anchors": ["d.final.complete"],
                "must_still_pass": ["d.permissions.preserved"],
                "mutation_family": "treat_partial_as_final",
                "gate": "wait_for_authority",
                "gate_args": {"artifacts": ["final"]},
            },
            {
                "id": "revise",
                "obligation": "revise_affected",
                "stage_tag": "plan_revision",
                "task_requirement_id": "req.final",
                "required_behavior": "rebuild affected output",
                "forbidden_behavior": "retain partial output",
                "primary_evidence": "pre/post artifact commits",
                "outcome_anchors": ["d.final.complete"],
                "must_still_pass": ["d.permissions.preserved"],
                "mutation_family": "drop_confirmed_partial",
                "gate": "selective_replan",
                "gate_args": {"artifacts": ["final"]},
            },
            {
                "id": "close",
                "obligation": "verify_closure",
                "stage_tag": "closure",
                "task_requirement_id": "req.final",
                "required_behavior": "verify complete output",
                "forbidden_behavior": "skip final verification",
                "primary_evidence": "post-authority verification",
                "outcome_anchors": ["d.final.complete"],
                "must_still_pass": ["d.permissions.preserved"],
                "mutation_family": "skip_reverification",
                "gate": "rederive_from_authority",
                "gate_args": {"artifacts": ["final"]},
            },
        ],
    }


def test_all_eight_event_policies_are_authoring_templates():
    assert len(EVENT_POLICIES) == 8
    assert all(policy["required_obligations"] for policy in EVENT_POLICIES.values())
    assert all(policy["mutation_families"] for policy in EVENT_POLICIES.values())


def test_dependency_closure_drives_affected_scope():
    graph = _ir()["dependency_graph"]
    assert dependency_descendants(graph, {"partial"}) == {"partial", "final", "req.final"}


def test_case_ir_compiles_task_specific_points_and_local_mutations():
    ir = _ir()
    assert validate_case_ir(ir) == []
    plan = compile_score_plan(ir, "d")
    assert validate_score_plan(plan) == []
    assert {point["decision_group"] for point in plan["points"]} == {
        "classify_completeness", "revise_affected", "verify_closure",
    }
    assert all(mutation["must_still_pass"] for mutation in plan["negative_mutations"])


def test_case_ir_rejects_incorrect_dependency_closure():
    ir = _ir()
    ir["event_contract"]["affected_closure"] = ["partial"]
    assert any("computed dependency closure" in error for error in validate_case_ir(ir))
