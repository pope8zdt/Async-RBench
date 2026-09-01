from pathlib import Path

from async_rbench.case_ir import validate_case_ir, validate_score_plan
from async_rbench.case_transformability import build_transformability_audit


ROOT = Path(__file__).resolve().parents[1]


def test_all_607_records_receive_deep_task_specific_transformability_audits():
    audit = build_transformability_audit(ROOT)
    assert audit["summary"]["input_count"] == 607
    assert audit["summary"]["transformable_count"] == 607
    assert audit["summary"]["balanced_450_event_scenario_allocation_feasible"]
    assert audit["summary"]["formal_registry_ready_now_count"] == 0
    assert len(audit["rows"]) == 607
    for row in audit["rows"]:
        assert 1 <= row["composition_plan"]["upstream_task_count"] <= 4
        assert row["composition_plan"]["milestones"]
        assert row["runtime_package_plan"]["docker"]
        assert row["runtime_package_plan"]["event_injection"]
        if row["transformability"]["can_be_formal_case_task"]:
            assert len(row["semantic_score_blueprint"]) >= 4
            assert 2 <= len(row["control_score_blueprint"]) <= 4
            assert row["experiment_standard_audit"]["blueprint_has_independent_evidence_contracts"]
            assert not row["experiment_standard_audit"]["formal_registry_ready_now"]
            assert validate_case_ir(row["case_ir_blueprint"]) == []
            plan = {
                "schema_version": "1",
                "case_ir_version": "1",
                "event_policy_version": "1",
                "case_id": row["case_id"],
                "instance_id": "seed-1",
                "primary_event_theme": row["async_classification_plan"]["primary_event_theme"],
                "points": row["control_score_blueprint"],
                "negative_mutations": row["negative_mutation_blueprint"],
            }
            assert validate_score_plan(plan) == []


def test_score_blueprints_are_not_copied_across_cases():
    audit = build_transformability_audit(ROOT)
    semantic = [row["semantic_design_digest"] for row in audit["rows"]]
    control = [row["control_design_digest"] for row in audit["rows"]]
    assert len(semantic) == len(set(semantic))
    assert len(control) == len(set(control))
