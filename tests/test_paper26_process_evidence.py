from __future__ import annotations

import pytest

from async_rbench.evaluation.control_flow_gates import score_event_replanning
from async_rbench.evaluation import scoring


def _outcome() -> list[dict]:
    return [{"id": "out", "event_id": "evt", "score_domain": "async_replanning", "passed": True}]


def test_forbidden_change_then_restore_keeps_process_penalty() -> None:
    result = score_event_replanning(
        {"event_id": "evt", "forbidden_changes": ["protected"]},
        {"protected": "original"}, {"protected": "original"}, _outcome(),
        artifact_history={"protected": [
            {"seq": 3, "observed_digest": "damaged"},
            {"seq": 4, "observed_digest": "original"},
        ]},
    )
    assert result.component_scores["forbidden_effect_compliance"] == 0.0
    assert result.async_outcome == 1.0
    assert result.total == 0.5


def test_missing_artifact_evidence_cannot_earn_preservation_credit() -> None:
    result = score_event_replanning(
        {"event_id": "evt", "required_preservation": ["unknown"], "forbidden_changes": ["unknown"]},
        {}, {}, _outcome(),
    )
    assert result.component_scores["preservation"] == 0.0
    assert result.component_scores["forbidden_effect_compliance"] == 0.0


def test_applicable_unmet_component_keeps_fixed_denominator() -> None:
    result = score_event_replanning(
        {"event_id": "evt", "applicable_components": ["preservation", "closure"],
         "required_preservation": ["protected"]},
        {"protected": "same"}, {"protected": "same"}, _outcome(),
    )
    assert result.component_scores["closure"] == 0.0
    assert result.process_score == 0.5
    assert result.total == 0.75


def test_pre_presentation_validation_does_not_satisfy_verify() -> None:
    result = score_event_replanning(
        {"event_id": "evt", "closure_checks": ["out"]},
        {}, {}, _outcome(), response_events=[],
    )
    assert result.component_scores["closure"] == 0.0
    assert result.async_outcome == 1.0


@pytest.mark.parametrize("evidence", ["omitted", None, []])
def test_final_check_cannot_replace_missing_participant_validation(evidence) -> None:
    kwargs = {} if evidence == "omitted" else {"response_events": evidence}
    result = score_event_replanning(
        {"event_id": "evt", "closure_checks": ["out"]},
        {}, {}, _outcome(), **kwargs,
    )
    assert result.component_scores["closure"] == 0.0
    assert result.async_outcome == 1.0
    assert result.total == 0.5


def test_evaluator_observed_response_validation_satisfies_verify() -> None:
    result = score_event_replanning(
        {"event_id": "evt", "closure_checks": ["out"]}, {}, {}, _outcome(),
        response_events=[{"type": "verification_requested", "check_id": "out",
                          "passed": True, "evaluator_owned": True}],
    )
    assert result.component_scores["closure"] == 1.0


def test_preserved_artifact_without_post_commit_keeps_baseline() -> None:
    before, after = scoring._event_state_snapshots(
        {"protected": [{"seq": 1, "observed_digest": "original"}]}, {"protected"}, 2,
    )
    assert before == {"protected": "original"}
    assert after == {"protected": "original"}


def test_response_history_stops_at_actual_termination() -> None:
    before, after, history = scoring._event_state_evidence(
        {"protected": [
            {"seq": 9, "observed_digest": "repair-after-finish"},
            {"seq": 1, "observed_digest": "original"},
            {"seq": 3, "observed_digest": "damaged"},
        ]}, {"protected"}, boundary_seq=2, terminal_seq=5,
    )
    assert before == {"protected": "original"}
    assert after == {"protected": "damaged"}
    assert [item["seq"] for item in history["protected"]] == [3]
