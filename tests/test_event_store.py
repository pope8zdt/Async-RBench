from __future__ import annotations

import pytest

from async_rbench.evaluation.event_store import (
    EventStore,
    classify_visibility,
    event_source_integrity_digest,
    replay_events,
    strip_for_adapter,
)
from async_rbench.evaluation.protocol import (
    VISIBILITY_KERNEL_PRIVATE,
    VISIBILITY_PUBLIC,
    VISIBILITY_REPLAY,
    ProtocolError,
)


def test_append_stamps_full_envelope():
    store = EventStore("ep-1")
    record = store.append(
        {"type": "child_spawned", "child_id": "c1"},
        actor="adapter",
        visibility=VISIBILITY_PUBLIC,
    )
    assert record["event_id"] == "ep-1:1"
    assert record["seq"] == 1
    assert record["episode_id"] == "ep-1"
    assert record["actor"] == "adapter"
    assert record["visibility"] == VISIBILITY_PUBLIC
    assert record["parent_event_id"] is None
    assert "timestamp" in record and "elapsed_ms" in record


def test_append_tracks_parent_event_id_and_sequence():
    store = EventStore("ep-1")
    first = store.append({"type": "child_completed", "completion_id": "k1"},
                         actor="adapter", visibility=VISIBILITY_PUBLIC)
    second = store.append({"type": "result_consumed", "completion_id": "k1"},
                          actor="adapter", visibility=VISIBILITY_PUBLIC,
                          parent_event_id=first["event_id"])
    assert second["event_id"] == "ep-1:2"
    assert second["parent_event_id"] == first["event_id"]


def test_streams_filter_by_visibility():
    store = EventStore("ep-1")
    store.append({"type": "child_spawned", "child_id": "c1"},
                 actor="adapter", visibility=VISIBILITY_PUBLIC)
    store.append({"type": "result_held", "completion_id": "k1"},
                 actor="gateway", visibility=VISIBILITY_KERNEL_PRIVATE)
    store.append({"type": "event_source_integrity", "digest": "d1"},
                 actor="kernel", visibility=VISIBILITY_REPLAY)
    assert [e["type"] for e in store.public_stream()] == ["child_spawned"]
    assert [e["type"] for e in store.kernel_private_stream()] == ["result_held"]
    assert [e["type"] for e in store.replay_stream()] == ["event_source_integrity"]


def test_classify_visibility_defaults():
    assert classify_visibility("child_spawned") == VISIBILITY_PUBLIC
    assert classify_visibility("verifier_result") == VISIBILITY_KERNEL_PRIVATE
    assert classify_visibility("result_held") == VISIBILITY_KERNEL_PRIVATE
    assert classify_visibility("episode_started") == VISIBILITY_PUBLIC
    assert classify_visibility("event_source_integrity") == VISIBILITY_REPLAY


def test_strip_for_adapter_drops_envelope_and_hidden_fields():
    record = {
        "type": "result_delivered",
        "completion_id": "k1",
        "payload": {"rows": 11},
        "evaluator_stale": True,
        "evaluator_stale_measurable": True,
        "evaluator_stale_reason": "stale",
        "event_id": "ep:1",
        "parent_event_id": None,
        "episode_id": "ep",
        "timestamp": 1.0,
        "seq": 1,
        "elapsed_ms": 1.0,
        "actor": "gateway",
        "visibility": "public",
        "source": "gateway",
    }
    assert strip_for_adapter(record) == {
        "type": "result_delivered",
        "child_id": "",
        "completion_id": "k1",
        "workstream_id": None,
        "payload": {"rows": 11},
        "payload_sha256": "",
    }


def test_public_completion_does_not_gain_evaluator_result_kind() -> None:
    record = {
        "type": "child_completed",
        "child_id": "child-1",
        "completion_id": "completion-1",
        "payload": {"summary": "done"},
    }
    assert "result_kind" not in strip_for_adapter(record)


def test_replay_reconstructs_delivery_state():
    events = [
        {"type": "child_spawned", "child_id": "c1"},
        {"type": "child_completed", "child_id": "c1", "completion_id": "k1",
         "result_kind": "wal", "payload": {}},
        {"type": "result_delivered", "completion_id": "k1"},
        {"type": "result_consumed", "completion_id": "k1", "action_id": "a1"},
    ]
    state = replay_events(events)
    assert state["spawned"] == {"c1"}
    assert "k1" in state["completions"]
    assert state["delivered"] == ["k1"]
    assert state["consumed"] == {"k1"}
    assert state["held"] == set()


def test_replay_tracks_held_before_delivery():
    events = [
        {"type": "child_completed", "child_id": "c1", "completion_id": "k1",
         "result_kind": "wal", "payload": {}},
    ]
    state = replay_events(events)
    assert state["held"] == {"k1"}
    assert state["delivered"] == []
    assert state["consumed"] == set()


def test_integrity_digest_detects_tamper():
    events = [{"type": "child_spawned", "child_id": "c1"}]
    digest = event_source_integrity_digest(events)
    tampered = [{"type": "child_spawned", "child_id": "c2"}]
    assert event_source_integrity_digest(tampered) != digest


def test_from_records_infers_actor_and_visibility():
    store = EventStore.from_records(
        [
            {"type": "child_spawned", "child_id": "c1", "source": "adapter", "seq": 1},
            {"type": "verifier_result", "success": True, "source": "benchmark", "seq": 2},
        ],
        "ep-1",
    )
    assert store.events[0]["actor"] == "adapter"
    assert store.events[0]["visibility"] == VISIBILITY_PUBLIC
    assert store.events[1]["actor"] == "benchmark"
    assert store.events[1]["visibility"] == VISIBILITY_KERNEL_PRIVATE


def test_delivery_occurrence_events_preserve_distinct_causal_boundaries():
    records = replay_events([
        {"type": "result_available", "delivery_occurrence_id": "o1", "completion_id": "c1"},
        {"type": "adapter_queued", "delivery_occurrence_id": "o1", "completion_id": "c1"},
        {"type": "result_presented", "delivery_occurrence_id": "o1", "completion_id": "c1",
         "turn_id": "t2", "window_id": "w1"},
    ])
    occ = records["occurrences"]["o1"]
    assert occ.available
    assert occ.queued
    assert occ.presented_turn_id == "t2"


def test_second_occurrence_can_share_completion_id_without_overwriting():
    records = replay_events([
        {"type": "result_available", "delivery_occurrence_id": "o1", "completion_id": "c1"},
        {"type": "adapter_queued", "delivery_occurrence_id": "o1", "completion_id": "c1"},
        {"type": "result_available", "delivery_occurrence_id": "o2", "completion_id": "c1"},
        {"type": "adapter_queued", "delivery_occurrence_id": "o2", "completion_id": "c1"},
    ])
    assert set(records["occurrences"]) == {"o1", "o2"}
    assert records["occurrences"]["o1"].available
    assert records["occurrences"]["o2"].available
    assert records["occurrences"]["o1"].presented_turn_id is None


def test_replay_full_delivery_occurrence_lifecycle():
    records = replay_events([
        {"type": "result_available", "delivery_occurrence_id": "o1", "completion_id": "c1"},
        {"type": "adapter_queued", "delivery_occurrence_id": "o1", "completion_id": "c1"},
        {"type": "presentation_prepared", "delivery_occurrence_id": "o1", "completion_id": "c1"},
        {"type": "result_presented", "delivery_occurrence_id": "o1", "completion_id": "c1",
         "turn_id": "t1", "window_id": "w1"},
        {"type": "main_action_started", "delivery_occurrence_id": "o1", "turn_id": "t1"},
        {"type": "main_action_finished", "delivery_occurrence_id": "o1", "turn_id": "t1"},
        {"type": "main_turn_completed", "delivery_occurrence_id": "o1", "turn_id": "t1"},
        {"type": "response_window_closed", "delivery_occurrence_id": "o1", "window_id": "w1"},
    ])
    occ = records["occurrences"]["o1"]
    assert occ.available and occ.queued and occ.prepared and occ.presented
    assert occ.presented_turn_id == "t1"
    assert occ.presented_window_id == "w1"
    assert occ.main_action_started and occ.main_action_finished
    assert occ.main_turn_completed and occ.window_closed


def test_replay_rejects_result_presented_before_queued():
    with pytest.raises(ProtocolError):
        replay_events([
            {"type": "result_available", "delivery_occurrence_id": "o1", "completion_id": "c1"},
            {"type": "result_presented", "delivery_occurrence_id": "o1", "completion_id": "c1",
             "turn_id": "t1", "window_id": "w1"},
        ])


def test_replay_rejects_duplicate_delivery_occurrence_id():
    with pytest.raises(ProtocolError):
        replay_events([
            {"type": "result_available", "delivery_occurrence_id": "o1", "completion_id": "c1"},
            {"type": "result_available", "delivery_occurrence_id": "o1", "completion_id": "c1"},
        ])


def test_replay_rejects_closing_unknown_window():
    with pytest.raises(ProtocolError):
        replay_events([
            {"type": "response_window_closed", "delivery_occurrence_id": "o1", "window_id": "w999"},
        ])
