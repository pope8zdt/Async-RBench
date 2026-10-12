from __future__ import annotations

import pytest

from async_rbench.evaluation import scoring


def _delivery(seq: int, event_id: str, completion: str = "c", **extra) -> dict:
    return {"type": "result_delivered", "seq": seq, "completion_id": completion,
            "child_id": "child", "benchmark_event_id": event_id, **extra}


def _presentation(seq: int, occurrence: str, completion: str = "c") -> list[dict]:
    return [
        {"type": kind, "seq": seq + offset, "completion_id": completion,
         "delivery_occurrence_id": occurrence, "turn_id": f"turn-{seq}"}
        for offset, kind in enumerate(["result_available", "adapter_queued", "result_presented"])
    ]


def test_target_boundary_is_presentation_not_gateway_delivery() -> None:
    boundaries = scoring._event_presentation_boundaries(
        [_delivery(1, "evt"), *_presentation(3, "occ")], [{"event_id": "evt"}], None,
    )
    assert boundaries == {"evt": 5}


def test_replayed_completion_joins_its_own_presentation_occurrence() -> None:
    events = [
        _delivery(1, "original"), *_presentation(2, "original-occ"),
        _delivery(5, "replay", replayed=True), *_presentation(6, "replay-occ"),
    ]
    boundaries = scoring._event_presentation_boundaries(
        events, [{"event_id": "original"}, {"event_id": "replay"}], None,
    )
    assert boundaries == {"original": 4, "replay": 8}


def test_unrelated_presentation_does_not_reach_target() -> None:
    assert scoring._event_presentation_boundaries(
        [_delivery(1, "unrelated"), *_presentation(2, "other")], [{"event_id": "target"}], None,
    ) == {}


def test_presentation_without_matching_occurrence_is_invalid() -> None:
    with pytest.raises(ValueError, match="presentation"):
        scoring._event_presentation_boundaries(
            [_delivery(1, "evt"), _presentation(2, "missing")[-1]], [{"event_id": "evt"}], None,
        )


def _trace(*, present: bool, restore: bool = False) -> tuple[list[dict], dict, list[dict]]:
    case = {
        "initial_wave": [{"workstream_id": "work"}, {"workstream_id": "other"}],
        "delegation_workstreams": [{"id": "work", "result_kind": "authority"},
                                   {"id": "other", "result_kind": "other"}],
        "authoritative_result_kind": "authority",
        "scenarios": {"async": {"events": [{"id": "evt", "result": "authority"}]}},
        "artifacts": [{"id": "protected"}],
    }
    events = [
        {"type": "child_spawned", "seq": 1, "child_id": "child", "parent_id": "main",
         "work_units": ["work"], "initial_wave": True},
        {"type": "child_started", "seq": 2, "child_id": "child"},
        {"type": "artifact_committed", "seq": 3, "artifact_id": "protected",
         "observed_digest": "a" * 64, "evaluator_observed": True},
        _delivery(4, "evt", result_kind="authority"),
        *_presentation(5, "occ")[:3 if present else 2],
    ]
    if restore:
        events.extend([
            {"type": "artifact_committed", "seq": 8, "artifact_id": "protected",
             "observed_digest": "b" * 64, "evaluator_observed": True},
            {"type": "artifact_committed", "seq": 9, "artifact_id": "protected",
             "observed_digest": "a" * 64, "evaluator_observed": True},
        ])
    events.extend([
        {"type": "finish_invoked", "seq": 10},
        {"type": "episode_ended", "seq": 11, "local_status": "completed"},
        {"type": "verifier_result", "seq": 12, "semantic_check_results": [
            {"id": "out", "score_domain": "async_replanning", "event_id": "evt", "passed": True},
        ]},
    ])
    events.insert(1, {"type": "child_spawned", "child_id": "other-child", "parent_id": "main",
                      "work_units": ["other"], "initial_wave": True})
    events.insert(3, {"type": "child_started", "child_id": "other-child"})
    for seq, event in enumerate(events, start=1):
        event["seq"] = seq
    return events, case, [{"event_id": "evt", "forbidden_changes": ["protected"]}]


def test_delivered_queued_but_unpresented_target_scores_zero() -> None:
    events, case, contracts = _trace(present=False)
    result = scoring.score_trace(events, case, "async", event_contracts=contracts)
    assert result["scenario_constructed"] is True
    assert result["trace_score_status_reason"] is None
    assert result["async_drs"] == 0.0


def test_restored_final_outcome_does_not_erase_forbidden_operation() -> None:
    events, case, contracts = _trace(present=True, restore=True)
    result = scoring.score_trace(events, case, "async", event_contracts=contracts)
    assert result["async_event_drs"]["evt"]["component_scores"]["forbidden_effect_compliance"] == 0.0
    assert result["async_event_drs"]["evt"]["async_outcome"] == 1.0
    assert result["async_drs"] == 0.5


@pytest.mark.parametrize("actor,expected", [("kernel", 1.0), ("adapter", 0.0)])
def test_process_scoring_uses_only_kernel_owned_artifact_snapshots(actor, expected):
    events, case, contracts = _trace(present=True)
    for event in events:
        if event["type"] == "artifact_committed":
            event.update(type="artifact_state_observed", actor=actor)
    result = scoring.score_trace(events, case, "async", event_contracts=contracts)
    assert result["async_event_drs"]["evt"]["component_scores"]["forbidden_effect_compliance"] == expected


def test_finish_with_queued_initial_work_is_measured_not_infrastructure_failure():
    events, case, contracts = _trace(present=False)
    for index in range(4):
        work = f"queued-{index}"
        case["initial_wave"].append({"workstream_id": work})
        case["delegation_workstreams"].append({"id": work, "result_kind": work})
        events.insert(0, {"type": "child_spawned", "child_id": work, "parent_id": "main",
                          "work_units": [work], "initial_wave": True})
    for seq, event in enumerate(events, 1):
        event["seq"] = seq
    result = scoring.score_trace(events, case, "async", event_contracts=contracts)
    assert result["scenario_constructed"] is True
    assert result["async_drs"] == 0.0
