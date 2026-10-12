import copy
import pytest
from async_rbench.evaluation.control_flow_gates import validate_drs_registry
from async_rbench.evaluation.weighting import SCORE_POLICY_VERSION

from async_rbench import judge


def test_runtime_contract_can_bind_an_existing_unregistered_target():
    public = {"artifacts": [{"id": "result", "path": "/app/result.json"}]}
    private = {"authoritative_result_kind": "late", "classification": {"primary_event_theme": "delayed_authoritative_result"},
               "scenarios": {"async": {"events": [{"id": "event", "result": "late"}]}}}
    semantic = {"checks": [{"id": "goal", "score_domain": "async_replanning", "event_id": "event"}]}
    original = copy.deepcopy((public, private, semantic))
    contract = judge.runtime_event_contract(public, private, {}, semantic)
    assert contract["event_id"] == "event"
    assert contract["required_changes"] == ["result"]
    assert contract["runtime_scoring"]["point_weight"] == 1.0
    assert contract["runtime_scoring"]["observation_scope"] == "command_boundaries"
    assert (public, private, semantic) == original


def test_runtime_contract_preserves_existing_requirements():
    contract = {"event_id": "event", "required_changes": ["a"],
                "required_preservation": ["b"], "forbidden_changes": ["c"],
                "closure_checks": ["validate"]}
    result = judge.runtime_event_contract({}, {}, {"event_contracts": [contract]}, {})
    for key, value in contract.items():
        assert result[key] == value


def test_runtime_contract_refuses_to_guess_between_target_events():
    private = {"authoritative_result_kind": "late", "scenarios": {"async": {"events": [
        {"id": "a", "result": "late"}, {"id": "b", "result": "late"}]}}}
    with pytest.raises(ValueError, match="unique target"):
        judge.runtime_event_contract({}, private, {}, {})


def test_runtime_scoring_metadata_cannot_silently_change_weights():
    contract = judge.runtime_event_contract({}, {}, {"event_contracts": [{
        "event_id": "event", "required_changes": ["a"]}]}, {})
    assert validate_drs_registry([contract], {}) == []
    contract["runtime_scoring"]["point_weight"] = 2.0
    assert any("runtime_scoring" in e for e in validate_drs_registry([contract], {}))


def test_new_runtime_scores_have_a_separate_policy_identity():
    assert SCORE_POLICY_VERSION == "async-rbench-runtime-boundaries-1"


def test_nginx_task_verifier_reaches_checks_when_participant_has_not_installed_service():
    original = '#!/bin/bash\nset -euo pipefail\nnginx -t\nnginx\npython3 -m pytest -q -rA tests\n'
    repaired = judge.runtime_verifier_script(original)
    assert 'if command -v nginx' in repaired
    assert repaired.endswith('python3 -m pytest -q -rA tests\n')
    assert judge.runtime_verifier_script('pytest -q\n') == 'pytest -q\n'
