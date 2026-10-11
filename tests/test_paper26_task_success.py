from __future__ import annotations

import pytest

from async_rbench.evaluation.control_flow_gates import score_base_task
from async_rbench.evaluation.pytest_results import parse_semantic_check_results


def _check(check_id: str, passed: bool, domain: str = "base_task") -> dict:
    return {"id": check_id, "score_domain": domain, "passed": passed}


def test_partial_task_completion_is_not_a_success() -> None:
    assert score_base_task([_check("a", True), _check("b", False)]) == 0.0


@pytest.mark.parametrize("registry_as_list", [False, True])
@pytest.mark.parametrize(
    ("results", "expected"),
    [
        ([_check("a", True), _check("b", True)], 1.0),
        ([_check("a", True), _check("b", False)], 0.0),
        ([_check("a", True)], 0.0),
        ([], 0.0),
        ([_check("a", True), _check("b", True), _check("b", False)], 0.0),
        ([_check("a", True), _check("b", True, "async_replanning")], 0.0),
        ([_check("a", True), _check("b", True), _check("event", False, "async_replanning")], 1.0),
    ],
)
def test_base_task_success_requires_all_registered_checks(
    results: list[dict], expected: float, registry_as_list: bool,
) -> None:
    checks = [{"id": name, "score_domain": "base_task"} for name in ("a", "b")]
    registry = checks if registry_as_list else {"checks": checks}
    assert score_base_task(results, semantic_registry=registry) == expected


@pytest.mark.parametrize("status", ["FAILED", "ERROR", "SKIPPED", "XFAIL", "XPASS", None])
def test_incomplete_registered_check_is_not_task_success(status: str | None) -> None:
    registry = {"checks": [
        {"id": "a", "score_domain": "base_task", "pytest_node": "test_task.py::test_a"},
        {"id": "b", "score_domain": "base_task", "pytest_node": "test_task.py::test_b"},
    ]}
    output = "PASSED test_task.py::test_a\n"
    if status:
        output += f"{status} test_task.py::test_b\n"
    parsed = parse_semantic_check_results(output, registry)
    assert parsed is not None
    assert score_base_task(parsed["results"], semantic_registry=registry) == 0.0


def test_no_registered_task_goal_cannot_earn_task_success() -> None:
    assert score_base_task([_check("unregistered", True)], semantic_registry={"checks": []}) is None
    assert score_base_task(None) is None
