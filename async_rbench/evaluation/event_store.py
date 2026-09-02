from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .protocol import (
    ACTOR_BENCHMARK,
    VISIBILITY_KERNEL_PRIVATE,
    VISIBILITY_PUBLIC,
    VISIBILITY_REPLAY,
    ProtocolError,
    canonical_digest,
)
from .case_contract import assert_participant_safe, public_delivery, public_rejection


# Fields that belong to the envelope (identity/timing/membership) or the legacy
# trace stamp, and must never reach the adapter.
_ENVELOPE_FIELDS = frozenset({
    "event_id", "parent_event_id", "episode_id", "timestamp",
    "seq", "elapsed_ms", "actor", "visibility", "source",
})

# Hidden evaluator truth fields that live on kernel-private records. They must
# never leak into the adapter stream.
_KERNEL_PRIVATE_FIELDS = frozenset({
    "evaluator_stale", "evaluator_stale_measurable", "evaluator_stale_reason",
    "replayed", "replay_of_completion_id",
    # Task 9 designed-terminal classification is scoring-only: the participant
    # sees the observable ``terminal_outcome`` (which ``public_delivery``
    # projects), never whether the failure was designed vs infrastructure nor the
    # private reason.
    "evaluator_designed_failure", "evaluator_terminal_reason",
})

# Event types whose default stream is not public. Used by ``classify_visibility``
# and ``EventStore.from_records``; explicit callers may still pass any visibility.
_KERNEL_PRIVATE_TYPES = frozenset({
    "run_metadata", "protocol_violation", "episode_timeout", "adapter_stderr",
    "verifier_result", "delegation_gate_fallback",
    "result_held", "result_contract_validated",
    "child_terminal_started", "child_terminal_finished",
    "verification_requested", "verification_passed", "verification_failed",
    "result_delivery_evaluator_fact", "result_rejection_evaluator_fact",
    "intervention_applied",
    # The evaluator prepares a before-snapshot and authorizes a presentation; the
    # snapshot digest and source case event id are evaluator-private, so this
    # event never reaches a model, and may carry them without leaking.
    "presentation_prepared",
})
_REPLAY_TYPES = frozenset({"event_source_integrity"})


@dataclass
class DeliveryOccurrence:
    """Reconstructed state of one delivery occurrence (spec §3.3).

    Each delivery uses a unique ``delivery_occurrence_id``; the originating child
    completion keeps its own ``completion_id``. A single completion may feed many
    occurrences (delivered into several turns/windows), so occurrences are keyed by
    ``delivery_occurrence_id`` and never share their identity with a completion.
    """

    occurrence_id: str
    completion_id: str | None = None
    available: bool = False
    queued: bool = False
    prepared: bool = False
    presented: bool = False
    presented_turn_id: str | None = None
    presented_window_id: str | None = None
    main_action_started: bool = False
    main_action_finished: bool = False
    main_turn_completed: bool = False
    window_closed: bool = False


class EventStore:
    """Normalised, immutable-append event source for one episode.

    Every recorded event is an envelope record: the typed event payload merged
    with ``event_id`` / ``parent_event_id`` / ``episode_id`` / ``timestamp`` /
    ``elapsed_ms`` / ``seq`` / ``actor`` / ``visibility``.
    """

    def __init__(self, episode_id: str, start_ns: int | None = None) -> None:
        self.episode_id = episode_id
        self._start_ns = start_ns if start_ns is not None else time.monotonic_ns()
        self.events: list[dict[str, Any]] = []

    def append(
        self,
        event: dict[str, Any],
        *,
        actor: str,
        visibility: str,
        parent_event_id: str | None = None,
    ) -> dict[str, Any]:
        seq = len(self.events) + 1
        record = dict(event)
        record.update({
            "event_id": f"{self.episode_id}:{seq}",
            "parent_event_id": parent_event_id,
            "episode_id": self.episode_id,
            "timestamp": time.time(),
            "elapsed_ms": round((time.monotonic_ns() - self._start_ns) / 1_000_000, 3),
            "seq": seq,
            "actor": actor,
            "visibility": visibility,
        })
        self.events.append(record)
        return record

    def stream(self, visibility: str) -> list[dict[str, Any]]:
        return [event for event in self.events if event.get("visibility") == visibility]

    def public_stream(self) -> list[dict[str, Any]]:
        return self.stream(VISIBILITY_PUBLIC)

    def kernel_private_stream(self) -> list[dict[str, Any]]:
        return self.stream(VISIBILITY_KERNEL_PRIVATE)

    def replay_stream(self) -> list[dict[str, Any]]:
        return self.stream(VISIBILITY_REPLAY)

    def integrity_digest(self) -> str:
        return event_source_integrity_digest(self.events)

    @classmethod
    def from_records(cls, events: list[dict[str, Any]], episode_id: str) -> "EventStore":
        """Wrap already-stamped legacy trace records into an EventStore.

        Infers ``actor`` from the legacy ``source`` stamp and ``visibility`` from
        the event type, preserving each record's own ``seq`` / ``elapsed_ms`` /
        ``episode_id`` when present.
        """
        store = cls(episode_id)
        for index, event in enumerate(events):
            record = dict(event)
            record.setdefault("event_id", f"{episode_id}:{index + 1}")
            record.setdefault("parent_event_id", None)
            record.setdefault("timestamp", time.time())
            record.setdefault("seq", index + 1)
            record.setdefault("elapsed_ms", 0.0)
            record.setdefault("episode_id", episode_id)
            actor = record.pop("source", None) or ACTOR_BENCHMARK
            record.setdefault("actor", actor)
            record.setdefault("visibility", classify_visibility(event.get("type"), actor))
            store.events.append(record)
        return store


def classify_visibility(event_type: str, actor: str | None = None) -> str:
    """Default stream for an event type when the caller does not say explicitly."""
    if event_type in _REPLAY_TYPES:
        return VISIBILITY_REPLAY
    if event_type in _KERNEL_PRIVATE_TYPES:
        return VISIBILITY_KERNEL_PRIVATE
    return VISIBILITY_PUBLIC


def public_presentation(event: dict[str, Any]) -> dict[str, Any]:
    """Project a ``result_presented`` record to the auditable public surface.

    Preserves the four identity fields plus the presented payload while dropping
    every evaluator-private fact: result role, schedule/disposition, authority and
    supersede labels, snapshot digests and source case event ids. The event is
    public/auditable — an observer may confirm a result was bound to a real main
    request — but its private expected effect stays hidden.
    """
    result = {
        "type": "result_presented",
        "delivery_occurrence_id": str(event.get("delivery_occurrence_id", "")),
        "completion_id": str(event.get("completion_id", "")),
        "turn_id": str(event.get("turn_id", "")),
        "window_id": str(event.get("window_id", "")),
        "payload": event.get("payload"),
        "payload_sha256": str(event.get("payload_sha256", "")),
    }
    assert_participant_safe(result, surface="public result presentation")
    return result


def strip_for_adapter(event: dict[str, Any]) -> dict[str, Any]:
    """Project a recorded event down to what an adapter may see.

    Drops every envelope/stamp field and every hidden evaluator-truth field.
    The target design moves the hidden truth into separate ``kernel_private``
    events, at which point this becomes a pure envelope strip; for now it also
    scrubs the inline ``evaluator_stale*`` fields the legacy delivery carries.
    """
    event_type = event.get("type")
    if event_type == "result_delivered":
        return public_delivery(event)
    if event_type == "result_rejected":
        return public_rejection(event)
    if event_type == "result_presented":
        return public_presentation(event)
    return {
        key: value for key, value in event.items()
        if key not in _ENVELOPE_FIELDS and key not in _KERNEL_PRIVATE_FIELDS
    }


def _occurrence_of(state: dict[str, Any], event: dict[str, Any], *, create: bool) -> DeliveryOccurrence:
    """Fetch the delivery occurrence for an event, creating it only if allowed."""
    occurrence_id = event.get("delivery_occurrence_id")
    event_type = event.get("type")
    if occurrence_id is None:
        raise ProtocolError(f"{event_type}: missing delivery_occurrence_id")
    existing = state["occurrences"].get(occurrence_id)
    if existing is not None:
        return existing
    if not create:
        raise ProtocolError(
            f"{event_type}: delivery_occurrence_id {occurrence_id!r} was never made available"
        )
    occurrence = DeliveryOccurrence(occurrence_id)
    state["occurrences"][occurrence_id] = occurrence
    return occurrence


def _apply_result_available(state: dict[str, Any], event: dict[str, Any]) -> None:
    occurrence = _occurrence_of(state, event, create=True)
    if occurrence.available:
        raise ProtocolError(f"duplicate delivery_occurrence_id: {occurrence.occurrence_id!r}")
    completion_id = event.get("completion_id")
    if completion_id is None:
        raise ProtocolError("result_available: missing completion_id")
    occurrence.completion_id = completion_id
    occurrence.available = True
    state["held"].discard(completion_id)


def _apply_adapter_queued(state: dict[str, Any], event: dict[str, Any]) -> None:
    occurrence = _occurrence_of(state, event, create=False)
    if not occurrence.available:
        raise ProtocolError(f"{event['type']} before result_available")
    occurrence.queued = True


def _apply_presentation_prepared(state: dict[str, Any], event: dict[str, Any]) -> None:
    occurrence = _occurrence_of(state, event, create=False)
    occurrence.prepared = True


def _apply_result_presented(state: dict[str, Any], event: dict[str, Any]) -> None:
    occurrence = _occurrence_of(state, event, create=False)
    if not occurrence.queued:
        raise ProtocolError("result_presented before adapter_queued")
    turn_id = event.get("turn_id")
    window_id = event.get("window_id")
    if turn_id is None:
        raise ProtocolError("result_presented: missing turn_id")
    if window_id is None:
        raise ProtocolError("result_presented: missing window_id")
    occurrence.presented = True
    occurrence.presented_turn_id = turn_id
    occurrence.presented_window_id = window_id
    state["open_windows"].add(window_id)


def _apply_main_action(state: dict[str, Any], event: dict[str, Any], *, started: bool) -> None:
    occurrence_id = event.get("delivery_occurrence_id")
    occurrence = state["occurrences"].get(occurrence_id) if occurrence_id is not None else None
    if occurrence is None:
        return
    if started:
        occurrence.main_action_started = True
    else:
        occurrence.main_action_finished = True


def _apply_main_turn_completed(state: dict[str, Any], event: dict[str, Any]) -> None:
    occurrence_id = event.get("delivery_occurrence_id")
    occurrence = state["occurrences"].get(occurrence_id) if occurrence_id is not None else None
    if occurrence is not None:
        occurrence.main_turn_completed = True


def _apply_response_window_closed(state: dict[str, Any], event: dict[str, Any]) -> None:
    window_id = event.get("window_id")
    if window_id is None:
        raise ProtocolError("response_window_closed: missing window_id")
    if window_id not in state["open_windows"]:
        raise ProtocolError(f"closing unknown window: {window_id!r}")
    state["open_windows"].discard(window_id)
    occurrence_id = event.get("delivery_occurrence_id")
    occurrence = state["occurrences"].get(occurrence_id) if occurrence_id is not None else None
    if occurrence is not None:
        occurrence.window_closed = True


def replay_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Replay an event source and reconstruct delivery/consumption state.

    Purely functional over the ordered event list — the reconstruction must not
    depend on any live gateway object, so a stored source can be audited later.

    Also reconstructs the delivery-occurrence lifecycle (spec §3.3) and rejects
    impossible transitions: presenting before an occurrence was queued, a duplicate
    ``delivery_occurrence_id``, or closing a window that was never opened.
    """
    state: dict[str, Any] = {
        "spawned": set(),
        "completions": {},
        "delivered": [],
        "consumed": set(),
        "held": set(),
        "artifacts": [],
        "verifications": [],
        "violations": [],
        "occurrences": {},
        "open_windows": set(),
    }
    for event in events:
        event_type = event.get("type")
        if event_type == "child_spawned":
            state["spawned"].add(event.get("child_id"))
        elif event_type == "child_completed":
            state["completions"][event["completion_id"]] = event
            state["held"].add(event["completion_id"])
        elif event_type == "result_delivered":
            state["delivered"].append(event["completion_id"])
            state["held"].discard(event["completion_id"])
        elif event_type == "result_rejected":
            state.setdefault("rejected", []).append(event["completion_id"])
            state["held"].discard(event["completion_id"])
        elif event_type == "result_consumed":
            state["consumed"].add(event["completion_id"])
        elif event_type == "artifact_committed":
            state["artifacts"].append(event)
        elif event_type == "verification_requested":
            state["verifications"].append(event)
        elif event_type == "protocol_violation":
            state["violations"].append(event)
        elif event_type == "result_available":
            _apply_result_available(state, event)
        elif event_type == "adapter_queued":
            _apply_adapter_queued(state, event)
        elif event_type == "presentation_prepared":
            _apply_presentation_prepared(state, event)
        elif event_type == "result_presented":
            _apply_result_presented(state, event)
        elif event_type == "main_action_started":
            _apply_main_action(state, event, started=True)
        elif event_type == "main_action_finished":
            _apply_main_action(state, event, started=False)
        elif event_type == "main_turn_completed":
            _apply_main_turn_completed(state, event)
        elif event_type == "response_window_closed":
            _apply_response_window_closed(state, event)
    return state


def event_source_integrity_digest(events: list[dict[str, Any]]) -> str:
    """Deterministic digest of the ordered event source (tamper detection)."""
    return canonical_digest(events)
