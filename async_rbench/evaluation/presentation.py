"""FIFO presentation queue and response-window gating (spec §5).

A released delivery is pinned to a single immutable ``DeliveryOccurrence`` and
enqueued into a FIFO ordered by the adapter receive sequence.  The main loop
presents at most one occurrence per main-model request: presenting one opens a
``ResponseWindow`` that must receive at least one main response and then either
settle or hit ``max_response_turns`` before the next occurrence may be
presented.  The same ``completion_id`` may feed many replay occurrences; each
keeps its own immutable identity and payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class PresentationError(ValueError):
    """Raised when a presentation-queue transition is illegal."""


@dataclass(frozen=True)
class DeliveryOccurrence:
    """One immutable delivery pinned to a FIFO presentation.

    ``occurrence_id`` distinguishes a single delivery; a single child completion
    (``completion_id``) may feed many occurrences because the same result may be
    presented into several main-model requests.  Replay therefore creates a new
    occurrence, never a new completion.
    """

    occurrence_id: str
    completion_id: str
    payload: dict[str, Any]
    receive_seq: int
    replay_of_occurrence_id: str | None = None
    benchmark_event_id: str | None = None
    scored: bool = False


@dataclass
class ResponseWindow:
    """Bounded response period opened when an occurrence is presented.

    A window must observe at least ``min_response_turns`` main-model responses
    before it can close.  It may close when the followed occurrence settles
    (``settled`` and at least ``min_response_turns`` complete) or deterministically
    once ``max_response_turns`` is reached even if not settled.
    """

    window_id: str
    occurrence_id: str
    min_response_turns: int = 1
    max_response_turns: int = 4
    completed_turns: int = 0
    settled: bool = False
    closed: bool = False

    @classmethod
    def open(
        cls,
        *,
        window_id: str,
        occurrence_id: str,
        min_response_turns: int = 1,
        max_response_turns: int = 4,
    ) -> "ResponseWindow":
        """Start a fresh, open response window for a presented occurrence."""
        window = cls(
            window_id=window_id,
            occurrence_id=occurrence_id,
            min_response_turns=min_response_turns,
            max_response_turns=max_response_turns,
        )
        window.settled = False
        window.closed = False
        return window

    @property
    def active(self) -> bool:
        return not self.closed

    def record_turn(self) -> None:
        """Record one completed main-model response observed in this window."""
        if self.closed:
            raise PresentationError(
                f"response window {self.window_id!r} is already closed"
            )
        self.completed_turns += 1

    def can_close(self) -> bool:
        if self.closed:
            return True
        if self.completed_turns >= self.max_response_turns:
            return True
        return self.settled and self.completed_turns >= self.min_response_turns

    def close(self) -> None:
        self.closed = True


@dataclass
class PresentationQueue:
    """FIFO of delivery occurrences gated by at most one open response window.

    ``enqueue`` keeps a stable receive-order FIFO (sorted by ``receive_seq``).
    ``peek`` returns the FIFO head regardless of any active window; ``peek_presentable``
    additionally seals the head behind an active window so at most one occurrence
    is presented per main-model request.
    """

    _pending: list[DeliveryOccurrence] = field(default_factory=list)
    _presented: dict[str, DeliveryOccurrence] = field(default_factory=dict)
    _active_window: ResponseWindow | None = None

    @property
    def active_window(self) -> ResponseWindow | None:
        return self._active_window

    @property
    def pending_occurrence_ids(self) -> list[str]:
        return [item.occurrence_id for item in self._pending]

    def enqueue(self, occurrence: DeliveryOccurrence) -> None:
        self._pending.append(occurrence)
        self._pending.sort(key=lambda item: item.receive_seq)

    def peek(self) -> DeliveryOccurrence | None:
        return self._pending[0] if self._pending else None

    def peek_presentable(self) -> DeliveryOccurrence | None:
        """Return the head occurrence that may be presented right now.

        Returns ``None`` while a response window is active (later scored
        occurrences stay sealed), otherwise the FIFO head.
        """
        if self._active_window is not None and self._active_window.active:
            return None
        return self.peek()

    def has_pending(self) -> bool:
        return bool(self._pending)

    def mark_presented(
        self, occurrence_id: str, *, turn_id: str, window_id: str,
    ) -> ResponseWindow:
        """Present the FIFO head occurrence and open its response window.

        ``turn_id`` / ``window_id`` bind the presentation to the real started
        main-model request that observed it.  A new occurrence may not be
        presented while an earlier window is still active.
        """
        if self._active_window is not None and self._active_window.active:
            raise PresentationError(
                f"cannot present {occurrence_id!r} while response window "
                f"{self._active_window.window_id!r} is active"
            )
        if not self._pending or self._pending[0].occurrence_id != occurrence_id:
            raise PresentationError(f"occurrence {occurrence_id!r} is not the FIFO head")
        occurrence = self._pending.pop(0)
        self._presented[occurrence_id] = occurrence
        window = ResponseWindow.open(window_id=window_id, occurrence_id=occurrence_id)
        self._active_window = window
        return window

    def presented_occurrence(self, occurrence_id: str) -> DeliveryOccurrence | None:
        return self._presented.get(occurrence_id)

    def record_turn(self) -> None:
        """Record one main-model response against the active window, if any."""
        if self._active_window is not None:
            self._active_window.record_turn()

    def close_active_window(self) -> bool:
        """Close the active window when it can close, sealing nothing and
        unsealing the next occurrence.  Returns True if a window was closed."""
        if self._active_window is None:
            return False
        if self._active_window.can_close():
            self._active_window.close()
            self._active_window = None
            return True
        return False
