from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, TYPE_CHECKING

from .validation_checkpoint import (
    ValidationCheckpoint,
    WorkspaceSnapshotReference,
    load_checkpoint,
)
from .workspace_runtime import ValidationWorkspaceSnapshot

if TYPE_CHECKING:
    from ..profiles.reference_scaffold_api.runtime import ReferenceScaffold
    from .presentation import DeliveryOccurrence


ADAPTER_CAPTURE_VERSION = "drs-validation-adapter-capture-1.0"
BRANCH_INVARIANTS = (
    "checkpoint_digest",
    "main_workspace_tree_digest",
    "main_transcript_digest",
    "controller_state_digest",
    "completion_bundle_digest",
    "remaining_budget_digest",
    "target_delivery_digest",
)
EXPECTED_CONDITIONS = frozenset(
    {"oracle_replan", "native_agent", "frozen_plan"}
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


class AdapterPrePresentationCapture:
    """Capture adapter state at the S^- boundary and stop before model input."""

    def __init__(
        self,
        path: Path,
        *,
        target_workstream_id: str,
        checkpoint_id: str | None = None,
    ) -> None:
        if not target_workstream_id:
            raise ValueError("target_workstream_id cannot be empty")
        self.path = path
        self.target_workstream_id = target_workstream_id
        self.checkpoint_id = checkpoint_id
        self.captured = False

    async def __call__(
        self,
        scaffold: ReferenceScaffold,
        occurrence: DeliveryOccurrence,
    ) -> bool:
        if self.captured:
            return False
        if str(occurrence.payload.get("workstream_id") or "") != self.target_workstream_id:
            return False
        scaffold_state = scaffold.export_validation_state()
        capture_event_index = len(scaffold.emitter.events)
        messages = scaffold_state.get("messages") or []
        if any(
            isinstance(message.get("content"), str)
            and message["content"].startswith("ASYNC_RBENCH_DELIVERY ")
            and occurrence.completion_id in message["content"]
            for message in messages
        ):
            raise ValueError("target delivery is already model-visible")
        target_occurrence = scaffold._validation_occurrence_to_dict(occurrence)
        main_workspace = None
        child_workspaces: dict[str, dict[str, str]] = {}
        completion_bundle: list[dict[str, Any]] = []
        kernel_capture = None
        if self.checkpoint_id is not None:
            kernel_capture = (
                await scaffold.workspace.export_validation_controller_state(
                    target_completion_id=occurrence.completion_id,
                )
            )
            snapshot_digest = str(
                getattr(scaffold, "_prepared_snapshot_digest", "") or ""
            )
            if len(snapshot_digest) != 64:
                raise ValueError(
                    "validation capture has no prepared workspace snapshot digest"
                )
            snapshot = await scaffold.workspace.capture_validation_snapshot(
                self.checkpoint_id,
                tree_sha256=snapshot_digest,
            )
            main_workspace = {
                "snapshot_id": snapshot.snapshot_id,
                "image_name": snapshot.image_name,
                "image_id": snapshot.image_id,
                "tree_sha256": snapshot.tree_sha256,
            }
            in_flight_children = [
                child
                for child in list(
                    ((scaffold_state.get("manager") or {}).get("children") or [])
                )
                if str(child.get("status") or "") in {"starting", "running"}
            ]
            tasks = [
                scaffold.manager.children[str(child["child_id"])].asyncio_task
                for child in in_flight_children
                if scaffold.manager.children[str(child["child_id"])].asyncio_task
                is not None
            ]
            if len(tasks) != len(in_flight_children):
                missing = sorted(
                    str(child["child_id"])
                    for child in in_flight_children
                    if scaffold.manager.children[
                        str(child["child_id"])
                    ].asyncio_task
                    is None
                )
                raise ValueError(
                    "in-flight children have no live capture task: "
                    + ", ".join(missing)
                )
            if tasks:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=(
                        scaffold.config.child_timeout_sec
                        + scaffold.config.live_cancellation_grace_sec
                    ),
                )
            in_flight_ids = {
                str(child["child_id"]) for child in in_flight_children
            }
            completion_bundle = [
                dict(event)
                for event in scaffold.emitter.events[capture_event_index:]
                if str(event.get("child_id") or "") in in_flight_ids
                and str(event.get("type") or "")
                in {
                    "child_progress_checkpoint",
                    "child_completed",
                    "child_cancelled",
                    "child_step_limit_reached",
                    "child_resource_safety_abort",
                    "child_no_submission",
                }
            ]
            for child in in_flight_children:
                child_id = str(child.get("child_id") or "")
                final_record = scaffold.manager.children[child_id]
                child_snapshot = (
                    await scaffold.workspace.capture_validation_child_snapshot(
                        self.checkpoint_id,
                        child_id,
                        tree_sha256=_digest(
                            {
                                "child_id": child_id,
                                "status": final_record.status,
                                "completion_id": final_record.completion_id,
                                "payload": final_record.payload,
                            }
                        ),
                    )
                )
                child_workspaces[child_id] = {
                    "snapshot_id": child_snapshot.snapshot_id,
                    "image_name": child_snapshot.image_name,
                    "image_id": child_snapshot.image_id,
                    "tree_sha256": child_snapshot.tree_sha256,
                }
        body = {
            "schema_version": ADAPTER_CAPTURE_VERSION,
            "target_workstream_id": self.target_workstream_id,
            "target_occurrence": target_occurrence,
            "scaffold_state": scaffold_state,
            "main_workspace": main_workspace,
            "child_workspaces": child_workspaces,
            "completion_bundle": completion_bundle,
            "kernel_capture": kernel_capture,
            "main_transcript_digest": _digest(messages),
            "scaffold_state_digest": _digest(scaffold_state),
        }
        document = {**body, "adapter_capture_sha256": _digest(body)}
        _atomic_write_json(self.path, document)
        scaffold.emitter.emit(
            "fork_bundle_captured",
            bundle_id=document["adapter_capture_sha256"],
            completion_payload_digest=_digest(occurrence.payload),
            main_transcript_digest=body["main_transcript_digest"],
        )
        self.captured = True
        return True


def read_adapter_capture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("adapter capture must be a JSON object")
    allowed = {
        "schema_version", "target_workstream_id", "target_occurrence",
        "scaffold_state", "main_transcript_digest", "scaffold_state_digest",
        "main_workspace", "child_workspaces", "completion_bundle",
        "kernel_capture", "adapter_capture_sha256",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError("unknown adapter capture fields: " + ", ".join(unknown))
    if value.get("schema_version") != ADAPTER_CAPTURE_VERSION:
        raise ValueError("unsupported adapter capture schema_version")
    supplied = str(value.get("adapter_capture_sha256") or "")
    body = dict(value)
    body.pop("adapter_capture_sha256", None)
    actual = _digest(body)
    if supplied != actual:
        raise ValueError(
            f"adapter capture digest mismatch: stored {supplied!r}, actual {actual}"
        )
    if str(value.get("main_transcript_digest")) != _digest(
        (value.get("scaffold_state") or {}).get("messages") or []
    ):
        raise ValueError("adapter capture main transcript digest mismatch")
    if str(value.get("scaffold_state_digest")) != _digest(
        value.get("scaffold_state") or {}
    ):
        raise ValueError("adapter capture scaffold state digest mismatch")
    return value


def assert_branch_equivalence(
    branches: Mapping[str, Mapping[str, str]],
) -> None:
    if set(branches) != EXPECTED_CONDITIONS:
        raise ValueError(
            "validation branches must be exactly oracle_replan, native_agent, "
            "and frozen_plan"
        )
    for invariant in BRANCH_INVARIANTS:
        values = {
            condition: str(branches[condition].get(invariant) or "")
            for condition in sorted(branches)
        }
        if any(not value for value in values.values()) or len(set(values.values())) != 1:
            raise ValueError(
                f"branch invariant mismatch for {invariant}: {values}"
            )


def build_validation_checkpoint(
    *,
    checkpoint_id: str,
    instance_key: str,
    model_id: str,
    repeat: int,
    target_event_id: str,
    adapter_capture: Mapping[str, Any],
    controller_state: Mapping[str, Any],
    prefix_trace_sha256: str,
    main_workspace: ValidationWorkspaceSnapshot,
    child_workspaces: Mapping[str, ValidationWorkspaceSnapshot],
    target_delivery: Mapping[str, Any],
    completion_bundle: list[dict[str, Any]],
    remaining_budget: Mapping[str, Any],
    source_digests: Mapping[str, str],
) -> ValidationCheckpoint:
    """Join adapter and kernel state into one strict validation checkpoint."""
    occurrence = dict(adapter_capture.get("target_occurrence") or {})
    target_completion_id = str(target_delivery.get("completion_id") or "")
    if str(occurrence.get("completion_id") or "") != target_completion_id:
        raise ValueError(
            "adapter target occurrence does not match kernel target delivery"
        )
    scaffold_state = dict(adapter_capture.get("scaffold_state") or {})
    manager = dict(scaffold_state.get("manager") or {})
    in_flight = {
        str(child.get("child_id") or "")
        for child in list(manager.get("children") or [])
        if str(child.get("status") or "") in {"starting", "running"}
    }
    terminal_children = {
        str(event.get("child_id") or "")
        for event in completion_bundle
        if str(event.get("type") or "")
        in {"child_completed", "child_cancelled", "child_step_limit_reached"}
    }
    for child_id in sorted(in_flight):
        if child_id not in child_workspaces:
            raise ValueError(
                f"in-flight child {child_id!r} has no workspace snapshot"
            )
        if child_id not in terminal_children:
            raise ValueError(
                f"in-flight child {child_id!r} has no terminal replay event"
            )

    child_references = tuple(
        WorkspaceSnapshotReference(
            image_id=snapshot.image_id,
            tree_sha256=snapshot.tree_sha256,
            child_id=child_id,
        )
        for child_id, snapshot in sorted(child_workspaces.items())
    )
    checkpoint = ValidationCheckpoint(
        schema_version="drs-validation-checkpoint-1.0",
        checkpoint_id=checkpoint_id,
        instance_key=instance_key,
        model_id=model_id,
        repeat=int(repeat),
        target_event_id=target_event_id,
        main_messages=tuple(
            dict(message) for message in list(scaffold_state.get("messages") or [])
        ),
        scaffold_state=scaffold_state,
        controller_state=dict(controller_state),
        prefix_trace_sha256=prefix_trace_sha256,
        main_workspace=WorkspaceSnapshotReference(
            image_id=main_workspace.image_id,
            tree_sha256=main_workspace.tree_sha256,
        ),
        child_workspaces=child_references,
        target_delivery=dict(target_delivery),
        completion_bundle=tuple(dict(event) for event in completion_bundle),
        remaining_budget=dict(remaining_budget),
        source_digests={
            str(key): str(value) for key, value in source_digests.items()
        },
    )
    checkpoint.validate()
    return checkpoint


def replay_completion_bundle(
    scaffold: ReferenceScaffold,
    events: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> None:
    """Apply captured future lifecycle facts to restored in-flight children."""
    for event in events:
        event_type = str(event.get("type") or "")
        child_id = str(event.get("child_id") or "")
        record = scaffold.manager.children.get(child_id)
        if record is None:
            raise ValueError(f"completion replay references unknown child {child_id!r}")
        if event_type == "child_progress_checkpoint":
            record.tokens = max(record.tokens, int(event.get("tokens", 0)))
            continue
        if event_type == "child_completed":
            completion_id = str(event.get("completion_id") or "")
            if not completion_id:
                raise ValueError(f"replayed child {child_id!r} completion has no id")
            record.status = "completed"
            record.completion_id = completion_id
            record.payload = event.get("payload")
            record.tokens = int(event.get("tokens", record.tokens))
            record.asyncio_task = None
            scaffold.manager.completion_to_child[completion_id] = child_id
            continue
        if event_type in {
            "child_cancelled",
            "child_step_limit_reached",
            "child_resource_safety_abort",
            "child_no_submission",
        }:
            record.status = {
                "child_cancelled": "cancelled",
                "child_step_limit_reached": "step_limit_reached",
                "child_resource_safety_abort": "resource_safety_abort",
                "child_no_submission": "no_submission",
            }[event_type]
            record.decision = str(event.get("reason") or event_type)
            record.asyncio_task = None
            continue
        raise ValueError(f"unsupported completion replay event {event_type!r}")


def restore_scaffold_from_checkpoint(
    scaffold: ReferenceScaffold,
    path: Path,
) -> ValidationCheckpoint:
    """Load one sealed checkpoint, restore adapter state, and replay child facts."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw.get("checkpoint_sha256"):
        raise ValueError("validation resume file has no checkpoint_sha256")
    checkpoint = load_checkpoint(
        path,
        expected_digest=str(raw["checkpoint_sha256"]),
    )
    scaffold.restore_validation_state(checkpoint.scaffold_state)
    replay_completion_bundle(scaffold, checkpoint.completion_bundle)
    return checkpoint
