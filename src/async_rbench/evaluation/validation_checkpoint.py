from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping


CHECKPOINT_VERSION = "drs-validation-checkpoint-1.0"
_HEX = frozenset("0123456789abcdef")
_FORBIDDEN_RUNTIME_KEYS = frozenset(
    {
        "asyncio_task",
        "container_name",
        "condition",
        "event_loop",
        "lock",
        "monotonic",
        "provider_client",
    }
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in _HEX for character in value)


def _assert_no_runtime_keys(value: Any, *, path: str = "checkpoint") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            if key_text in _FORBIDDEN_RUNTIME_KEYS:
                raise ValueError(f"{path} contains forbidden runtime field {key_text!r}")
            _assert_no_runtime_keys(nested, path=f"{path}.{key_text}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _assert_no_runtime_keys(nested, path=f"{path}[{index}]")


@dataclass(frozen=True)
class WorkspaceSnapshotReference:
    image_id: str
    tree_sha256: str
    child_id: str | None = None

    def validate(self) -> None:
        image_digest = self.image_id.removeprefix("sha256:")
        if not _is_sha256(image_digest):
            raise ValueError(f"invalid workspace image id: {self.image_id!r}")
        if not _is_sha256(self.tree_sha256):
            raise ValueError(f"invalid workspace tree digest: {self.tree_sha256!r}")
        if self.child_id is not None and not self.child_id:
            raise ValueError("child workspace child_id cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "image_id": self.image_id,
            "tree_sha256": self.tree_sha256,
        }
        if self.child_id is not None:
            value["child_id"] = self.child_id
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> WorkspaceSnapshotReference:
        allowed = {"image_id", "tree_sha256", "child_id"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"unknown workspace snapshot fields: {unknown}")
        result = cls(
            image_id=str(value.get("image_id", "")),
            tree_sha256=str(value.get("tree_sha256", "")),
            child_id=(str(value["child_id"]) if value.get("child_id") is not None else None),
        )
        result.validate()
        return result


@dataclass(frozen=True)
class ValidationCheckpoint:
    schema_version: str
    checkpoint_id: str
    instance_key: str
    model_id: str
    repeat: int
    target_event_id: str
    main_messages: tuple[dict[str, Any], ...]
    scaffold_state: dict[str, Any]
    controller_state: dict[str, Any]
    prefix_trace_sha256: str
    main_workspace: WorkspaceSnapshotReference
    child_workspaces: tuple[WorkspaceSnapshotReference, ...]
    target_delivery: dict[str, Any]
    completion_bundle: tuple[dict[str, Any], ...]
    remaining_budget: dict[str, Any]
    source_digests: dict[str, str]

    def validate(self) -> None:
        if self.schema_version != CHECKPOINT_VERSION:
            raise ValueError(f"schema_version must be {CHECKPOINT_VERSION}")
        for name, value in (
            ("checkpoint_id", self.checkpoint_id),
            ("instance_key", self.instance_key),
            ("model_id", self.model_id),
            ("target_event_id", self.target_event_id),
        ):
            if not value:
                raise ValueError(f"{name} cannot be empty")
        if self.repeat < 0:
            raise ValueError("repeat must be non-negative")
        if not _is_sha256(self.prefix_trace_sha256):
            raise ValueError("prefix_trace_sha256 must be a SHA-256 digest")
        self.main_workspace.validate()
        for snapshot in self.child_workspaces:
            snapshot.validate()
            if snapshot.child_id is None:
                raise ValueError("child workspace snapshot requires child_id")
        if len({item.child_id for item in self.child_workspaces}) != len(
            self.child_workspaces
        ):
            raise ValueError("child workspace snapshot child_ids must be unique")
        if self.target_delivery.get("type") != "result_delivered":
            raise ValueError("target_delivery must be result_delivered")
        if self.target_delivery.get("benchmark_event_id") != self.target_event_id:
            raise ValueError("target_delivery benchmark_event_id does not match target_event_id")
        for name, digest in self.source_digests.items():
            if not _is_sha256(str(digest)):
                raise ValueError(f"source digest {name!r} is not SHA-256")
        _assert_no_runtime_keys(self.scaffold_state, path="scaffold_state")
        _assert_no_runtime_keys(self.controller_state, path="controller_state")
        _assert_no_runtime_keys(self.remaining_budget, path="remaining_budget")
        self._assert_target_not_visible()

    def _assert_target_not_visible(self) -> None:
        target_occurrence = self.target_delivery.get("delivery_occurrence_id")
        for message in self.main_messages:
            content = message.get("content")
            if not isinstance(content, str) or not content.startswith(
                "ASYNC_RBENCH_DELIVERY "
            ):
                continue
            try:
                delivery = json.loads(content.split(" ", 1)[1])
            except json.JSONDecodeError:
                continue
            if (
                delivery.get("benchmark_event_id") == self.target_event_id
                or (
                    target_occurrence is not None
                    and delivery.get("delivery_occurrence_id") == target_occurrence
                )
            ):
                raise ValueError("target delivery is already model-visible")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "checkpoint_id": self.checkpoint_id,
            "instance_key": self.instance_key,
            "model_id": self.model_id,
            "repeat": self.repeat,
            "target_event_id": self.target_event_id,
            "main_messages": list(self.main_messages),
            "scaffold_state": self.scaffold_state,
            "controller_state": self.controller_state,
            "prefix_trace_sha256": self.prefix_trace_sha256,
            "main_workspace": self.main_workspace.to_dict(),
            "child_workspaces": [item.to_dict() for item in self.child_workspaces],
            "target_delivery": self.target_delivery,
            "completion_bundle": list(self.completion_bundle),
            "remaining_budget": self.remaining_budget,
            "source_digests": self.source_digests,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ValidationCheckpoint:
        allowed = {field.name for field in fields(cls)}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"unknown checkpoint fields: {', '.join(unknown)}")
        missing = sorted(allowed - set(value))
        if missing:
            raise ValueError(f"missing checkpoint fields: {', '.join(missing)}")
        result = cls(
            schema_version=str(value["schema_version"]),
            checkpoint_id=str(value["checkpoint_id"]),
            instance_key=str(value["instance_key"]),
            model_id=str(value["model_id"]),
            repeat=int(value["repeat"]),
            target_event_id=str(value["target_event_id"]),
            main_messages=tuple(dict(item) for item in value["main_messages"]),
            scaffold_state=dict(value["scaffold_state"]),
            controller_state=dict(value["controller_state"]),
            prefix_trace_sha256=str(value["prefix_trace_sha256"]),
            main_workspace=WorkspaceSnapshotReference.from_dict(value["main_workspace"]),
            child_workspaces=tuple(
                WorkspaceSnapshotReference.from_dict(item)
                for item in value["child_workspaces"]
            ),
            target_delivery=dict(value["target_delivery"]),
            completion_bundle=tuple(dict(item) for item in value["completion_bundle"]),
            remaining_budget=dict(value["remaining_budget"]),
            source_digests={
                str(key): str(digest)
                for key, digest in dict(value["source_digests"]).items()
            },
        )
        result.validate()
        return result


def checkpoint_digest(checkpoint: ValidationCheckpoint) -> str:
    return hashlib.sha256(_canonical_json(checkpoint.to_dict())).hexdigest()


def write_checkpoint(path: Path, checkpoint: ValidationCheckpoint) -> str:
    digest = checkpoint_digest(checkpoint)
    document = {**checkpoint.to_dict(), "checkpoint_sha256": digest}
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2, sort_keys=True)
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
    return digest


def load_checkpoint(path: Path, *, expected_digest: str) -> ValidationCheckpoint:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("checkpoint document must be an object")
    allowed = {field.name for field in fields(ValidationCheckpoint)} | {
        "checkpoint_sha256"
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"unknown checkpoint fields: {', '.join(unknown)}")
    stored_digest = str(value.pop("checkpoint_sha256", ""))
    checkpoint = ValidationCheckpoint.from_dict(value)
    actual_digest = checkpoint_digest(checkpoint)
    if stored_digest != actual_digest:
        raise ValueError(
            f"stored checkpoint digest {stored_digest!r} does not match content "
            f"digest {actual_digest}"
        )
    if expected_digest != actual_digest:
        raise ValueError(
            f"expected checkpoint digest {expected_digest!r}, got {actual_digest}"
        )
    return checkpoint

