from __future__ import annotations

from async_rbench.evaluation.pytest_results import (
    parse_component_summaries,
    parse_pytest_summary,
    parse_semantic_check_results,
)


def test_parse_pytest_summary_across_multiple_invocations() -> None:
    output = """
    .F................... [100%]
    1 failed, 20 passed, 1 deselected, 1 warning in 2.23s
    . [100%]
    1 passed in 0.41s
    """
    result = parse_pytest_summary(output)
    assert result["passed"] == 21
    assert result["failed"] == 1
    assert result["counted"] == 22
    assert result["deselected"] == 1
    assert result["summary_lines"] == 2
    assert result["test_pass_fraction"] == 21 / 22


def test_parse_pytest_summary_counts_errors_but_not_skips_in_denominator() -> None:
    result = parse_pytest_summary("2 passed, 1 error, 3 skipped in 1.00s")
    assert result["counted"] == 3
    assert result["test_pass_fraction"] == 2 / 3


def test_parse_pytest_summary_returns_none_without_a_summary() -> None:
    result = parse_pytest_summary("private verifier timed out")
    assert result["counted"] == 0
    assert result["test_pass_fraction"] is None


def test_parse_independent_component_summaries() -> None:
    output = """
ASYNC_RBENCH_COMPONENT_BEGIN history_clean
3 passed in 0.10s
ASYNC_RBENCH_COMPONENT_END history_clean exit_code=0
ASYNC_RBENCH_COMPONENT_BEGIN nginx_runtime
2 failed, 6 passed in 1.20s
ASYNC_RBENCH_COMPONENT_END nginx_runtime exit_code=1
"""
    result = parse_component_summaries(output)
    assert result["history_clean"]["success"] is True
    assert result["history_clean"]["test_pass_fraction"] == 1.0
    assert result["nginx_runtime"]["success"] is False
    assert result["nginx_runtime"]["test_pass_fraction"] == 0.75


def test_parse_incomplete_component_is_retained() -> None:
    result = parse_component_summaries(
        "ASYNC_RBENCH_COMPONENT_BEGIN deployment_lineage\n1 failed in 0.10s\n"
    )
    assert result["deployment_lineage"]["completed"] is False
    assert result["deployment_lineage"]["success"] is False
    assert result["deployment_lineage"]["exit_code"] is None


def test_semantic_registry_counts_each_frozen_point_once() -> None:
    registry = {
        "version": "7",
        "checks": [
            {"id": "authority", "pytest_node": "test_case.py::test_authority", "category": "replanning",
             "score_domain": "base_task"},
            {"id": "integration", "pytest_node": "test_case.py::test_integration", "category": "integration",
             "score_domain": "async_replanning", "event_id": "evt.authority"},
            {"id": "lineage", "pytest_node": "test_case.py::test_lineage", "category": "lineage"},
        ],
    }
    output = """
PASSED task/tests/test_case.py::test_authority
FAILED task/tests/test_case.py::test_integration - AssertionError
SKIPPED task/tests/test_case.py::test_lineage
1 failed, 1 passed, 1 skipped in 0.20s
"""
    result = parse_semantic_check_results(output, registry)
    assert result is not None
    assert result["registry_version"] == "7"
    assert result["passed"] == 1
    assert result["total"] == 3
    assert result["test_point_pass_rate"] == 1 / 3
    assert [item["status"] for item in result["results"]] == ["passed", "failed", "skipped"]
    by_id = {item["id"]: item for item in result["results"]}
    # The registry score_domain/event_id are copied through to every result row
    # so the headline score consumers can filter on them.
    assert by_id["authority"]["score_domain"] == "base_task"
    assert by_id["authority"]["event_id"] == ""
    assert by_id["integration"]["score_domain"] == "async_replanning"
    assert by_id["integration"]["event_id"] == "evt.authority"
    assert by_id["lineage"]["score_domain"] == ""
    assert by_id["lineage"]["event_id"] == ""


def test_missing_semantic_outcome_is_a_non_pass_not_a_smaller_denominator() -> None:
    registry = {
        "version": "1",
        "checks": [
            {"id": "a", "pytest_node": "test_case.py::test_a"},
            {"id": "b", "pytest_node": "test_case.py::test_b"},
        ],
    }
    result = parse_semantic_check_results("PASSED test_case.py::test_a", registry)
    assert result is not None
    assert result["passed"] == 1
    assert result["total"] == 2
    assert result["test_point_pass_rate"] == 0.5
    assert result["results"][1]["status"] == "missing"
