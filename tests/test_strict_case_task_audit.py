from pathlib import Path

from async_rbench.strict_case_task_audit import build_strict_case_task_audit

from author_local import requires_author_local


ROOT = Path(__file__).resolve().parents[1]
pytestmark = requires_author_local("artifacts/source-native-v4/native_manifest.jsonl")


def test_strict_audit_keeps_generation_family_separate_from_async_classification():
    audit = build_strict_case_task_audit(ROOT)
    generated = audit["generated_case_tasks"]
    assert generated["summary"]["input_count"] == 607
    assert generated["summary"]["strictly_selected_count"] == 0
    assert generated["summary"]["async_classification_counts"] == {
        "formally_classified": 0,
        "unclassified_generated_shell": 607,
    }
    assert all(row["primary_event_theme"] is None for row in generated["rows"])
    assert all(row["legacy_generation_family"] for row in generated["rows"])


def test_registered_tasks_are_technical_but_not_currently_publication_ready():
    audit = build_strict_case_task_audit(ROOT)
    registered = audit["registered_case_tasks"]
    assert registered["summary"]["technical_registry_valid"] is True
    assert registered["summary"]["task_count"] == 201
    assert registered["summary"]["publication_ready_count"] == 22
    assert sum(registered["summary"]["primary_event_theme_counts"].values()) == 201
    assert registered["summary"]["async_scenario_class_counts"] == {
        "live_eventful": 39,
        "resource_eventful": 16,
        "result_eventful": 146,
    }
    transformed = [row for row in registered["rows"] if row["publication_ready"]]
    assert sorted(row["semantic_check_count"] for row in transformed) == [
        5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 6, 6, 7, 9, 10, 10, 11, 12, 13, 16,
    ]
    assert sorted(row["control_flow_check_count"] for row in transformed) == [
        3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4,
    ]
