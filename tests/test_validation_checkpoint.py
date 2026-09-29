from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from async_rbench.evaluation.validation_checkpoint import (
    CHECKPOINT_VERSION,
    ValidationCheckpoint,
    WorkspaceSnapshotReference,
    checkpoint_digest,
    load_checkpoint,
    write_checkpoint,
)


def _checkpoint() -> ValidationCheckpoint:
    return ValidationCheckpoint(
        schema_version=CHECKPOINT_VERSION,
        checkpoint_id="ckpt-0123456789abcdef",
        instance_key="case-a::seed-1",
        model_id="model-a",
        repeat=2026,
        target_event_id="event-authority",
        main_messages=(
            {"role": "system", "content": "system"},
            {"role": "user", "content": "task"},
            {"role": "assistant", "content": "working"},
        ),
        scaffold_state={
            "next_turn_index": 4,
            "action_counter": 2,
            "accepted_state_revision": 1,
            "presentation_queue": {"pending": [], "active_window": None},
            "child_records": [{"child_id": "child-1", "status": "completed"}],
        },
        controller_state={
            "delivered": ["completion-old"],
            "consumed": ["completion-old"],
            "main_actions": 2,
        },
        prefix_trace_sha256="1" * 64,
        main_workspace=WorkspaceSnapshotReference(
            image_id="sha256:" + "2" * 64,
            tree_sha256="3" * 64,
        ),
        child_workspaces=(
            WorkspaceSnapshotReference(
                image_id="sha256:" + "4" * 64,
                tree_sha256="5" * 64,
                child_id="child-1",
            ),
        ),
        target_delivery={
            "type": "result_delivered",
            "benchmark_event_id": "event-authority",
            "delivery_occurrence_id": "occurrence-2",
            "completion_id": "completion-new",
            "payload": {"revision": "v2"},
        },
        completion_bundle=(
            {"type": "child_completed", "completion_id": "completion-new"},
        ),
        remaining_budget={"main_steps": 97, "emergency_tokens": 4990000},
        source_digests={
            "case_bundle_sha256": "6" * 64,
            "profile_sha256": "7" * 64,
            "event_contract_sha256": "8" * 64,
        },
    )


def test_checkpoint_round_trips_with_a_stable_digest(tmp_path: Path) -> None:
    checkpoint = _checkpoint()
    path = tmp_path / "checkpoint.json"

    digest = write_checkpoint(path, checkpoint)
    restored = load_checkpoint(path, expected_digest=digest)

    assert restored == checkpoint
    assert checkpoint_digest(restored) == digest
    assert json.loads(path.read_text(encoding="utf-8"))["checkpoint_sha256"] == digest


def test_checkpoint_rejects_unknown_or_condition_specific_fields(tmp_path: Path) -> None:
    checkpoint = _checkpoint()
    path = tmp_path / "checkpoint.json"
    digest = write_checkpoint(path, checkpoint)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["condition"] = "oracle_replan"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown checkpoint fields.*condition"):
        load_checkpoint(path, expected_digest=digest)


def test_checkpoint_rejects_digest_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    write_checkpoint(path, _checkpoint())

    with pytest.raises(ValueError, match="expected checkpoint digest"):
        load_checkpoint(path, expected_digest="0" * 64)


def test_checkpoint_rejects_target_already_visible_to_model(tmp_path: Path) -> None:
    checkpoint = _checkpoint()
    visible = {
        "role": "user",
        "content": "ASYNC_RBENCH_DELIVERY "
        + json.dumps(checkpoint.target_delivery, sort_keys=True),
    }
    invalid = replace(checkpoint, main_messages=checkpoint.main_messages + (visible,))

    with pytest.raises(ValueError, match="target delivery is already model-visible"):
        write_checkpoint(tmp_path / "checkpoint.json", invalid)


def test_checkpoint_digest_excludes_runtime_container_names() -> None:
    checkpoint = _checkpoint()
    raw = checkpoint.to_dict()

    assert "container_name" not in json.dumps(raw)
    assert "monotonic" not in json.dumps(raw)

