"""P1-17: mutually exclusive per-attempt terminal classification.

Every spawned child attempt receives exactly one class from
``termination.TERMINAL_CLASSES``; first-attempt vs retry is a facet dimension
(``attempt_number`` / ``retry``), not a duplicated counter.  The classifier is
mode-free: it never reads ``execution_mode`` (P1-16), so both arms classify
identically from the same child-level events.
"""

from __future__ import annotations

from async_rbench.evaluation.case_contract import PUBLIC_RESULT_REJECTION_CODES
from async_rbench.evaluation.termination import (
    ACCEPTED,
    CANCEL,
    CRASH,
    INFRASTRUCTURE_FAILURE,
    IN_FLIGHT,
    PRIVATE_REJECTION,
    PUBLIC_REJECTION,
    RESOURCE_EXHAUSTED,
    SEALED,
    SUBMISSION_CLASSES,
    TERMINAL_CLASSES,
    TIMEOUT,
    classify_child_terminals,
)


def _spawn(child_id: str, workstream: str = "ws-a", seq: int = 1) -> dict:
    return {
        "type": "child_spawned", "event_id": f"ep:{seq}", "seq": seq,
        "child_id": child_id, "parent_id": "main", "work_units": [workstream],
    }


def _completed(child_id: str, completion_id: str, seq: int = 2) -> dict:
    return {
        "type": "child_completed", "event_id": f"ep:{seq}", "seq": seq,
        "child_id": child_id, "completion_id": completion_id, "payload": {"x": 1},
    }


def _delivered(child_id: str, completion_id: str, seq: int = 3, **extra) -> dict:
    return {
        "type": "result_delivered", "event_id": f"ep:{seq}", "seq": seq,
        "child_id": child_id, "completion_id": completion_id, "payload": {"x": 1},
        "workstream_id": "ws-a", **extra,
    }


def _rejected(child_id: str, completion_id: str, codes: list[str], seq: int = 3) -> dict:
    return {
        "type": "result_rejected", "event_id": f"ep:{seq}", "seq": seq,
        "child_id": child_id, "completion_id": completion_id,
        "reason_codes": codes, "workstream_id": "ws-a",
    }


def _consumed(completion_id: str, seq: int = 4) -> dict:
    return {
        "type": "result_consumed", "event_id": f"ep:{seq}", "seq": seq,
        "completion_id": completion_id, "action_id": "a1",
    }


def _cancelled(child_id: str, initiated_by: str = "main", seq: int = 5, reason: str = "r") -> dict:
    return {
        "type": "child_cancelled", "event_id": f"ep:{seq}", "seq": seq,
        "child_id": child_id, "initiated_by": initiated_by, "reason": reason,
    }


def _rows(events: list[dict]) -> dict[str, dict]:
    return {
        row["child_id"]: row for row in classify_child_terminals(events)
    }


def test_every_class_maps_to_a_distinct_terminal() -> None:
    assert len(TERMINAL_CLASSES) == 10
    assert len(set(TERMINAL_CLASSES)) == len(TERMINAL_CLASSES)
    assert TERMINAL_CLASSES.index(ACCEPTED) < TERMINAL_CLASSES.index(PUBLIC_REJECTION)
    assert set(SUBMISSION_CLASSES) == {ACCEPTED, PUBLIC_REJECTION, PRIVATE_REJECTION, SEALED}


def test_helper_events_are_valid_public_codes() -> None:
    # Pin the fixture contract: report codes are public, validator codes are not.
    assert "report_file_missing" in PUBLIC_RESULT_REJECTION_CODES
    assert "validator_command_failed" not in PUBLIC_RESULT_REJECTION_CODES


def test_accepted() -> None:
    rows = _rows([
        _spawn("c1"), _completed("c1", "p1"),
        _delivered("c1", "p1"), _consumed("p1"),
    ])
    assert rows["c1"]["terminal_class"] == ACCEPTED
    assert rows["c1"]["sealed_submission"] is True
    assert rows["c1"]["attempt_number"] == 1
    assert rows["c1"]["retry"] is False


def test_public_rejection_carries_actionable_codes() -> None:
    rows = _rows([
        _spawn("c1"), _completed("c1", "p1"),
        _rejected("c1", "p1", ["report_file_missing", "validator_command_failed"]),
    ])
    assert rows["c1"]["terminal_class"] == PUBLIC_REJECTION
    assert rows["c1"]["sealed_submission"] is True
    # The rejected attempt still sealed; both code sets are exposed separately.
    assert rows["c1"]["reason_codes"] == ["report_file_missing", "validator_command_failed"]
    assert rows["c1"]["public_codes"] == ["report_file_missing"]
    assert rows["c1"]["contract_part"] == "report_file"


def test_private_rejection_has_no_public_feedback() -> None:
    rows = _rows([
        _spawn("c1"), _completed("c1", "p1"),
        _rejected("c1", "p1", ["validator_command_failed"]),
    ])
    assert rows["c1"]["terminal_class"] == PRIVATE_REJECTION
    assert rows["c1"]["sealed_submission"] is True
    assert rows["c1"]["public_codes"] == []
    assert rows["c1"]["contract_part"] == "submission"


def test_sealed_never_delivered() -> None:
    # The child sealed, but the episode closed before the gateway processed it.
    rows = _rows([_spawn("c1"), _completed("c1", "p1")])
    assert rows["c1"]["terminal_class"] == SEALED
    assert rows["c1"]["sealed_submission"] is True


def test_sealed_delivered_but_never_accepted() -> None:
    # The gateway accepted the contract (delivered), but the participant never
    # acknowledged a use decision: no verdict, so still "sealed", not "accepted".
    rows = _rows([
        _spawn("c1"), _completed("c1", "p1"), _delivered("c1", "p1"),
    ])
    assert rows["c1"]["terminal_class"] == SEALED


def test_resource_exhausted_is_not_a_submission() -> None:
    rows = _rows([
        _spawn("c1"),
        {"type": "child_resource_exhausted", "event_id": "ep:2", "seq": 2,
         "child_id": "c1", "pool": "episode", "remaining": 0},
    ])
    assert rows["c1"]["terminal_class"] == RESOURCE_EXHAUSTED
    assert rows["c1"]["sealed_submission"] is False


def test_designed_timeout_terminal() -> None:
    rows = _rows([
        _spawn("c1"),
        _delivered("c1", "terminal:ev-1", terminal_outcome="timeout",
                   evaluator_terminal_reason="designed child timeout"),
    ])
    assert rows["c1"]["terminal_class"] == TIMEOUT
    assert rows["c1"]["completion_id"] == "terminal:ev-1"
    assert rows["c1"]["terminal_outcome"] == "timeout"
    assert rows["c1"]["sealed_submission"] is False


def test_designed_crash_terminal() -> None:
    rows = _rows([
        _spawn("c1"),
        _delivered("c1", "terminal:ev-2", terminal_outcome="crash"),
    ])
    assert rows["c1"]["terminal_class"] == CRASH
    assert rows["c1"]["terminal_outcome"] == "crash"


def test_main_cancel_beats_episode_shutdown_delivery() -> None:
    rows = _rows([
        _spawn("c1"),
        _cancelled("c1", initiated_by="main", reason="redundant"),
        _cancelled("c1", initiated_by="scaffold_shutdown", reason="episode ended"),
    ])
    assert rows["c1"]["terminal_class"] == CANCEL
    assert rows["c1"]["detail"] == "redundant"
    assert rows["c1"]["sealed_submission"] is False


def test_infrastructure_failure() -> None:
    rows = _rows([
        _spawn("c1"),
        {"type": "infrastructure_failure", "event_id": "ep:2", "seq": 2,
         "child_id": "c1", "component": "child_workspace", "detail": "no disk"},
        _cancelled("c1", initiated_by="infrastructure", reason="workspace"),
    ])
    assert rows["c1"]["terminal_class"] == INFRASTRUCTURE_FAILURE
    assert rows["c1"]["sealed_submission"] is False


def test_infrastructure_cancelled_child_failure() -> None:
    # A bare infrastructure-initiated cancellation (child agent raised) is also
    # an infrastructure failure: the benchmark failed, not the model.
    rows = _rows([
        _spawn("c1"),
        _cancelled("c1", initiated_by="infrastructure", reason="child failure: boom"),
    ])
    assert rows["c1"]["terminal_class"] == INFRASTRUCTURE_FAILURE


def test_in_flight_at_episode_close() -> None:
    rows = _rows([_spawn("c1")])
    assert rows["c1"]["terminal_class"] == IN_FLIGHT
    assert rows["c1"]["sealed_submission"] is False


def test_in_flight_with_shutdown_cancel() -> None:
    rows = _rows([
        _spawn("c1"),
        _cancelled("c1", initiated_by="scaffold_shutdown", reason="episode ended"),
    ])
    assert rows["c1"]["terminal_class"] == IN_FLIGHT
    assert rows["c1"]["detail"] == "episode ended"


def test_attempt_numbers_are_per_workstream_spawn_order() -> None:
    rows = _rows([
        _spawn("c1", "ws-a", seq=1), _spawn("c2", "ws-a", seq=2),
        _spawn("c3", "ws-b", seq=3), _spawn("c4", "ws-a", seq=4),
    ])
    assert (rows["c1"]["attempt_number"], rows["c1"]["retry"]) == (1, False)
    assert (rows["c2"]["attempt_number"], rows["c2"]["retry"]) == (2, True)
    assert (rows["c3"]["attempt_number"], rows["c3"]["retry"]) == (1, False)
    assert (rows["c4"]["attempt_number"], rows["c4"]["retry"]) == (3, True)


def test_rejection_reenforces_attempt_order() -> None:
    events = [
        _spawn("c1", "ws-a", seq=1), _completed("c1", "p1"),
        _rejected("c1", "p1", ["report_file_missing"]),
        _spawn("c2", "ws-a", seq=5), _completed("c2", "p2"),
        _delivered("c2", "p2"), _consumed("p2"),
    ]
    rows = _rows(events)
    assert rows["c1"]["terminal_class"] == PUBLIC_REJECTION
    assert rows["c1"]["attempt_number"] == 1
    assert rows["c2"]["terminal_class"] == ACCEPTED
    assert rows["c2"]["attempt_number"] == 2


def test_designed_terminal_wins_over_a_late_sealed_submission() -> None:
    # A designed terminal delivery comes at child_started; a child that keeps
    # running afterwards can still seal a real completion.  The attempt ends at
    # the designed terminal: the terminal class wins regardless of the late
    # completion/consumption.
    rows = _rows([
        _spawn("c1"),
        _delivered("c1", "terminal:ev-1", terminal_outcome="timeout"),
        _completed("c1", "p1"), _delivered("c1", "p1"), _consumed("p1"),
    ])
    assert rows["c1"]["terminal_class"] == TIMEOUT
    assert rows["c1"]["completion_id"] == "terminal:ev-1"
    assert rows["c1"]["sealed_submission"] is False


def test_child_tokens_are_summed_per_child() -> None:
    events = [
        _spawn("c1"),
        {"type": "agent_progress", "event_id": "ep:1a", "seq": 1,
         "role": "child:c1", "phase": "model_call_finished", "tokens": 120},
        {"type": "agent_progress", "event_id": "ep:1b", "seq": 2,
         "role": "child:c1", "phase": "model_call_finished", "tokens": 80},
        # Main-side and non-finished phases are not child spend.
        {"type": "agent_progress", "event_id": "ep:2", "seq": 3,
         "role": "main", "phase": "model_call_finished", "tokens": 999},
        {"type": "agent_progress", "event_id": "ep:3", "seq": 4,
         "role": "child:c1", "phase": "model_call_started", "tokens": 999},
    ]
    rows = _rows(events)
    assert rows["c1"]["tokens"] == 200


def test_classifier_is_mode_free() -> None:
    # The function signature takes events only: no execution_mode key anywhere.
    import inspect
    assert "execution_mode" not in inspect.signature(classify_child_terminals).parameters


def test_single_class_per_child_on_a_mixed_trace() -> None:
    events = [
        _spawn("c1", "ws-a", seq=1), _completed("c1", "p1"),
        _rejected("c1", "p1", ["report_file_missing"]),
        _spawn("c2", "ws-a", seq=5), _completed("c2", "p2"),
        _delivered("c2", "p2"), _consumed("p2"),
        _spawn("c3", "ws-b", seq=9),
        {"type": "child_resource_exhausted", "event_id": "ep:10", "seq": 10,
         "child_id": "c3", "pool": "episode", "remaining": 0},
        _spawn("c4", "ws-b", seq=11),
        _delivered("c4", "terminal:ev-3", terminal_outcome="timeout"),
        _spawn("c5", "ws-c", seq=13),
        _cancelled("c5", initiated_by="main", reason="stale"),
    ]
    rows = _rows(events)
    assert {row["child_id"]: row["terminal_class"] for row in rows.values()} == {
        "c1": PUBLIC_REJECTION, "c2": ACCEPTED, "c3": RESOURCE_EXHAUSTED,
        "c4": TIMEOUT, "c5": CANCEL,
    }
    assert all(row["terminal_class"] in TERMINAL_CLASSES for row in rows.values())
