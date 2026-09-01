from __future__ import annotations

import time
from typing import Any

from .protocol import (
    ACTOR_BENCHMARK,
    VISIBILITY_KERNEL_PRIVATE,
    VISIBILITY_PUBLIC,
    VISIBILITY_REPLAY,
    canonical_digest,
)
from .case_contract import public_delivery, public_rejection


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
})
_REPLAY_TYPES = frozenset({"event_source_integrity"})


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
    return {
        key: value for key, value in event.items()
        if key not in _ENVELOPE_FIELDS and key not in _KERNEL_PRIVATE_FIELDS
    }


def replay_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Replay an event source and reconstruct delivery/consumption state.

    Purely functional over the ordered event list — the reconstruction must not
    depend on any live gateway object, so a stored source can be audited later.
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
    return state


def event_source_integrity_digest(events: list[dict[str, Any]]) -> str:
    """Deterministic digest of the ordered event source (tamper detection)."""
    return canonical_digest(events)
