from __future__ import annotations

from typing import Any

import pytest

from async_rbench.evaluation.presentation import (
    DeliveryOccurrence,
    PresentationError,
    PresentationQueue,
    ResponseWindow,
)


def occurrence(
    occurrence_id: str,
    *,
    completion_id: str = "c1",
    receive_seq: int = 1,
    payload: dict[str, Any] | None = None,
    replay_of_occurrence_id: str | None = None,
    benchmark_event_id: str | None = None,
) -> DeliveryOccurrence:
    return DeliveryOccurrence(
        occurrence_id=occurrence_id,
        completion_id=completion_id,
        payload=payload if payload is not None else {"occurrence_id": occurrence_id},
        receive_seq=receive_seq,
        replay_of_occurrence_id=replay_of_occurrence_id,
        benchmark_event_id=benchmark_event_id,
    )


def test_queue_presents_one_occurrence_per_main_request_in_receive_order() -> None:
    queue = PresentationQueue()
    queue.enqueue(occurrence("o2", receive_seq=2))
    queue.enqueue(occurrence("o1", receive_seq=1))
    assert queue.peek().occurrence_id == "o1"
    queue.mark_presented("o1", turn_id="t1", window_id="w1")
    assert queue.peek().occurrence_id == "o2"


def test_same_completion_id_keeps_occurrence_payloads_independent() -> None:
    """A single completion may feed several replay occurrences; each keeps its own
    immutable identity and payload even though they share ``completion_id``."""
    queue = PresentationQueue()
    queue.enqueue(occurrence("o1", completion_id="c1", receive_seq=1, payload={"v": 1}))
    queue.enqueue(
        occurrence("o1-replay", completion_id="c1", receive_seq=2, payload={"v": 2})
    )
    assert queue.peek().occurrence_id == "o1"
    queue.mark_presented("o1", turn_id="t1", window_id="w1")
    head = queue.peek()
    assert head is not None
    assert head.occurrence_id == "o1-replay"
    assert head.completion_id == "c1"
    assert head.payload == {"v": 2}
    # The original occurrence is immutable and unchanged.
    assert queue.presented_occurrence("o1").payload == {"v": 1}


def test_queued_occurrence_blocked_while_response_window_active() -> None:
    queue = PresentationQueue()
    queue.enqueue(occurrence("o1", receive_seq=1))
    queue.enqueue(occurrence("o2", receive_seq=2))
    queue.mark_presented("o1", turn_id="t1", window_id="w1")
    assert queue.active_window is not None
    assert queue.active_window.window_id == "w1"
    # o2 is queued but may not be presented while w1 is active.
    with pytest.raises(PresentationError):
        queue.mark_presented("o2", turn_id="t2", window_id="w2")
    # It stays queued, still the FIFO head.
    assert queue.peek().occurrence_id == "o2"
    # And it is not presentable until the window closes.
    assert queue.peek_presentable() is None


def test_window_requires_at_least_one_main_response() -> None:
    window = ResponseWindow(
        window_id="w1", occurrence_id="o1", min_response_turns=1, max_response_turns=4
    )
    assert window.can_close() is False
    window.settled = True
    # Even settled, zero main responses cannot close (need >= min_response_turns).
    assert window.can_close() is False
    window.record_turn()
    assert window.can_close() is True


def test_max_response_turns_closes_non_settled_window_deterministically() -> None:
    window = ResponseWindow.open(
        window_id="w1",
        occurrence_id="o1",
        min_response_turns=1,
        max_response_turns=4,
    )
    assert window.closed is False
    assert window.settled is False
    for _ in range(4):
        window.record_turn()
    # Not settled, but max_response_turns reached -> can close deterministically.
    assert window.can_close() is True
    window.close()
    assert window.closed is True
    with pytest.raises(PresentationError):
        window.record_turn()


def test_closing_active_window_unseals_next_occurrence() -> None:
    queue = PresentationQueue()
    queue.enqueue(occurrence("o1", receive_seq=1))
    queue.enqueue(occurrence("o2", receive_seq=2))
    queue.mark_presented("o1", turn_id="t1", window_id="w1")
    assert queue.peek_presentable() is None
    for _ in range(4):
        queue.record_turn()
    assert queue.close_active_window() is True
    assert queue.active_window is None
    head = queue.peek_presentable()
    assert head is not None
    assert head.occurrence_id == "o2"
