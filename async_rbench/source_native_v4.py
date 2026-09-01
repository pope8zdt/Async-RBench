"""Source-native v4 contracts and event lifecycle.

Unlike the v2/v3 symbolic capsules, this module never exposes expected action
IDs.  A native producer returns raw environment evidence; the original
benchmark evaluator scores the persisted final environment state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Lifecycle(str, Enum):
    CREATED = "created"
    WORKER_RUNNING = "worker_running"
    CHECKPOINT_COMMITTED = "checkpoint_committed"
    RESULT_DELIVERED = "result_delivered"
    FINALIZED = "finalized"


@dataclass
class NativeEventBroker:
    """Enforce treatment timing without putting answers in the prompt."""

    mode: str
    state: Lifecycle = Lifecycle.CREATED
    result: dict[str, Any] | None = None
    audit: list[dict[str, Any]] = field(default_factory=list)
    baseline_revision: str | None = None
    audit_chain_head: str = "0" * 64

    def _record(self, event: str, **details: Any) -> None:
        record = {"event": event, **details, "previous_sha256": self.audit_chain_head}
        record["record_sha256"] = canonical_hash(record)
        self.audit_chain_head = record["record_sha256"]
        self.audit.append(record)

    def launch(self, baseline_revision: str) -> None:
        if self.state is not Lifecycle.CREATED:
            raise RuntimeError("native worker can only launch once")
        if not baseline_revision:
            raise ValueError("launch requires the reset native state revision")
        self.baseline_revision = baseline_revision
        self.state = Lifecycle.WORKER_RUNNING
        self._record("worker_launched", baseline_revision=baseline_revision)

    def complete_worker(self, raw_result: dict[str, Any]) -> None:
        if self.state not in {Lifecycle.WORKER_RUNNING, Lifecycle.CHECKPOINT_COMMITTED}:
            raise RuntimeError("worker result arrived in an invalid lifecycle state")
        if any(key.endswith("action_ids") or key.startswith("expected_") for key in raw_result):
            raise ValueError("native event payload contains forbidden answer-bearing fields")
        self.result = json.loads(json.dumps(raw_result))
        self._record("worker_completed", payload_sha256=canonical_hash(raw_result))

    def commit_checkpoint(self, native_state_revision: str) -> None:
        if self.mode != "async":
            raise RuntimeError("only async mode has an interrupted checkpoint")
        if self.state is not Lifecycle.WORKER_RUNNING:
            raise RuntimeError("checkpoint requires a running independent worker")
        if not native_state_revision:
            raise ValueError("checkpoint must identify a persisted native state revision")
        if native_state_revision == self.baseline_revision:
            raise ValueError("async checkpoint must differ from the reset native state")
        self.state = Lifecycle.CHECKPOINT_COMMITTED
        self._record("checkpoint_committed", native_state_revision=native_state_revision)

    def deliver(self) -> dict[str, Any]:
        if self.result is None:
            raise RuntimeError("independent worker has not completed")
        if self.mode == "async" and self.state is not Lifecycle.CHECKPOINT_COMMITTED:
            raise RuntimeError("async result cannot be delivered before a persisted checkpoint")
        if self.mode in {"linear", "react"} and self.state is not Lifecycle.WORKER_RUNNING:
            raise RuntimeError("blocking result must be delivered before dependent work")
        self.state = Lifecycle.RESULT_DELIVERED
        self._record("result_delivered", mode=self.mode)
        return json.loads(json.dumps(self.result))

    def finalize(self, native_state_revision: str) -> None:
        if self.state is not Lifecycle.RESULT_DELIVERED:
            raise RuntimeError("finalization requires delivered native evidence")
        if not native_state_revision:
            raise ValueError("final native state revision is required")
        self.state = Lifecycle.FINALIZED
        self._record("finalized", native_state_revision=native_state_revision)


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def common_protocol() -> dict[str, Any]:
    return {
        "react": {
            "agents": 1,
            "concurrent_subagents": 0,
            "evidence_delivery": "same native evidence producer awaited synchronously",
        },
        "linear": {
            "agents": 1,
            "concurrent_subagents": 0,
            "evidence_delivery": "same native evidence is materialized before dependent work",
        },
        "async": {
            "concurrent_subagents": 1,
            "evidence_delivery": "raw result delivered only after a persisted native-state checkpoint",
            "checkpoint_is_stateful": True,
            "final_response_cannot_replace_checkpoint_history": True,
        },
        "prompt_privacy": {
            "expected_action_ids_exposed": False,
            "candidate_action_catalogue_exposed": False,
            "stale_action_ids_exposed": False,
            "closure_hash_exposed": False,
        },
        "score_policy": "the unchanged source-native evaluator scores final persisted state in every mode",
    }
