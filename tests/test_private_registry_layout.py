import json

from async_rbench.private_eval import _load_semantic_registry
from async_rbench.private_eval import verifier_bundle_sha256


def test_split_judge_loads_registry_from_evaluator_directory(tmp_path):
    (tmp_path / "tests").mkdir()
    evaluator = tmp_path / "evaluator"
    evaluator.mkdir()
    registry = {"version": "3", "checks": [{"id": "goal", "pytest_node": "test_goal.py::test_goal"}]}
    (evaluator / "semantic_checks.json").write_text(json.dumps(registry), encoding="utf-8")
    assert _load_semantic_registry(tmp_path) == registry


def test_conflicting_private_registry_copies_are_rejected(tmp_path):
    import pytest
    for directory, version in (("tests", "1"), ("evaluator", "2")):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "semantic_checks.json").write_text(
            json.dumps({"version": version, "checks": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="conflicting semantic registries"):
        _load_semantic_registry(tmp_path)


def test_verifier_digest_includes_split_registry_inputs(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_goal.py").write_text('def test_goal(): pass', encoding="utf-8")
    (tmp_path / "run-tests.sh").write_text('pytest -q', encoding="utf-8")
    (tmp_path / "evaluator").mkdir()
    path = tmp_path / "evaluator/control_flow_checks.json"
    path.write_text('{"checks": []}', encoding="utf-8")
    before = verifier_bundle_sha256(tmp_path)
    path.write_text('{"checks": [{"id": "changed"}]}', encoding="utf-8")
    assert verifier_bundle_sha256(tmp_path) != before
