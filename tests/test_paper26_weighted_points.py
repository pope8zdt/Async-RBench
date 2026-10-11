import copy

import pytest

from async_rbench.evaluation.control_flow_gates import score_event_replanning
from async_rbench.evaluation.scoring import score_trace


def _contract():
    return {"event_id": "e", "scoring_points": {
        "required_effect_coverage": [
            {"id": "major", "weight": 9, "artifact_id": "a", "check_id": "major"},
            {"id": "minor", "weight": 1, "artifact_id": "b", "check_id": "minor"},
        ],
        "async_outcome": [
            {"id": "major", "weight": 9, "check_id": "major"},
            {"id": "minor", "weight": 1, "check_id": "minor"},
        ],
    }}


def test_component_points_use_declared_unequal_weights():
    score = score_event_replanning(
        _contract(), {"a": "old", "b": "old"}, {"a": "old", "b": "new"},
        [{"id": "minor", "passed": True, "score_domain": "async_replanning", "event_id": "e"}],
        response_events=[{"type": "verification_requested", "check_id": "minor",
                          "evaluator_owned": True, "passed": True}],
    )
    assert score.component_scores["required_effect_coverage"] == pytest.approx(0.1)
    assert score.async_outcome == pytest.approx(0.1)
    assert score.total == pytest.approx(0.1)


def test_missing_outcome_point_does_not_shrink_denominator():
    registry = {"checks": [
        {"id": name, "score_domain": "async_replanning", "event_id": "e"}
        for name in ("a", "b")
    ]}
    result = score_event_replanning(
        {"event_id": "e", "required_changes": ["a"]}, {}, {"a": "new"},
        [dict(registry["checks"][0], passed=True)], semantic_registry=registry,
    )
    assert result.async_outcome == 0.5


def test_changed_erc_weight_changes_denominator_digest():
    contract = _contract()
    changed = copy.deepcopy(contract)
    changed["scoring_points"]["async_outcome"][0]["weight"] = 3
    first = score_trace([], {}, "async", event_contracts=[contract])
    second = score_trace([], {}, "async", event_contracts=[changed])
    assert first["denominator_digest"] != second["denominator_digest"]


@pytest.mark.parametrize("weight", [0, -1, float("nan"), float("inf"), True, "9"])
def test_invalid_point_weight_is_rejected(weight):
    contract = _contract()
    contract["scoring_points"]["async_outcome"][0]["weight"] = weight
    with pytest.raises(ValueError, match="weight"):
        score_event_replanning(contract, {}, {}, [])


def test_official_preflight_requires_frozen_weights_and_observer_coverage():
    from async_rbench.evaluation.control_flow_gates import validate_drs_registry
    assert validate_drs_registry([{"event_id": "e", "required_changes": ["a"]}], {}, official=True)
    contract = _contract()
    contract["scoring_points"]["forbidden_effect_compliance"] = [
        {"id": "protected", "artifact_id": "protected", "weight": 1}]
    errors = validate_drs_registry([contract], {}, official=True)
    assert any("response-window" in error for error in errors)


def test_unknown_outcome_check_is_rejected_before_run():
    from async_rbench.evaluation.control_flow_gates import validate_drs_registry
    assert validate_drs_registry([_contract()], {"checks": []})


def test_correct_change_without_participant_verification_keeps_change_credit():
    contract = _contract()
    contract["scoring_points"]["closure"] = [{"id": "verify", "check_id": "verify", "weight": 1}]
    results = [{"id": name, "score_domain": "async_replanning", "event_id": "e", "passed": True}
               for name in ("major", "minor")]
    result = score_event_replanning(contract, {"a": "old", "b": "old"},
                                    {"a": "new", "b": "new"}, results, response_events=[])
    assert result.component_scores["required_effect_coverage"] == 1.0
    assert result.component_scores["closure"] == 0.0
    assert result.total == 0.75


def test_outcome_only_contract_cannot_silently_drop_process_denominator():
    from async_rbench.evaluation.control_flow_gates import validate_drs_registry
    contract = {"event_id": "e", "scoring_points": {
        "async_outcome": [{"id": "out", "check_id": "out", "weight": 1}]}}
    registry = {"checks": [{"id": "out", "score_domain": "async_replanning", "event_id": "e"}]}
    errors = validate_drs_registry([contract], registry, official=True)
    assert any("process" in error for error in errors)
    with pytest.raises(ValueError, match="process"):
        score_event_replanning(contract, {}, {}, [])


@pytest.mark.parametrize("defect", ["missing_artifact", "unsupported_observer", "missing_verify_command"])
def test_preflight_rejects_unexecutable_process_bindings(defect):
    from async_rbench.evaluation.control_flow_gates import validate_drs_registry
    contract = _contract()
    contract["scoring_points"]["closure"] = [{"id": "v", "check_id": "verify", "weight": 1}]
    registry = {"checks": [{"id": name, "score_domain": "async_replanning", "event_id": "e"}
                           for name in ("major", "minor", "verify")]}
    case = {"artifacts": [{"id": "a", "path": "/app/a"}, {"id": "b", "path": "/app/b"}],
            "hidden_reverification_commands": {"verify": "python verify.py"}}
    if defect == "missing_artifact":
        case["artifacts"].pop()
    elif defect == "unsupported_observer":
        case["artifacts"][0]["path"] = "runtime:opaque"
    else:
        case["hidden_reverification_commands"] = {}
    assert validate_drs_registry([contract], registry, official=True, case_spec=case)


def test_verify_binding_uses_runtime_command_not_final_semantic_check():
    from async_rbench.evaluation.control_flow_gates import validate_drs_registry
    contract = {"event_id": "e", "scoring_points": {
        "closure": [{"id": "v", "check_id": "verify", "weight": 1}],
        "async_outcome": [{"id": "o", "check_id": "outcome", "weight": 1}]}}
    registry = {"checks": [{"id": "outcome", "event_id": "e", "score_domain": "async_replanning"}]}
    case = {"hidden_reverification_commands": {"verify": "python check_state.py"}}
    assert validate_drs_registry([contract], registry, official=True, case_spec=case) == []
