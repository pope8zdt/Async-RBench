from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# --- Event-source envelope (Step 2) ------------------------------------------

VISIBILITY_PUBLIC = "public"
VISIBILITY_KERNEL_PRIVATE = "kernel_private"
VISIBILITY_REPLAY = "replay"
VISIBILITIES = (VISIBILITY_PUBLIC, VISIBILITY_KERNEL_PRIVATE, VISIBILITY_REPLAY)

ACTOR_ADAPTER = "adapter"
ACTOR_GATEWAY = "gateway"
ACTOR_VERIFIER = "verifier"
ACTOR_KERNEL = "kernel"
ACTOR_BENCHMARK = "benchmark"
ACTORS = (ACTOR_ADAPTER, ACTOR_GATEWAY, ACTOR_VERIFIER, ACTOR_KERNEL, ACTOR_BENCHMARK)

# Core event types introduced by the event-source protocol. The legacy names
# (`episode_start`, `result_delivery`, `verification`, `episode_end`,
# `fork_bundle_ready`) were removed at the protocol-2.0 clean break; only the
# canonical names below are emitted or accepted.
new_core_event_types = (
    "episode_started", "adapter_registered", "profile_selected",
    "result_held", "result_delivered", "result_rejected",
    "verification_requested", "verification_passed", "verification_failed",
    "episode_ended", "fork_bundle_captured", "fork_bundle_replayed",
)

# Delivery-occurrence and main-observation event types (spec §3.3). These split
# the single legacy ``result_delivered`` fact into three distinct causal
# boundaries: R_i gateway release (``result_available``), A_i adapter queue
# (``adapter_queued``), and O_i main-model presentation (``result_presented``).
# ``result_delivered`` remains a documented compatibility alias only; the events
# below are first-class.
delivery_occurrence_event_types = (
    "result_available", "adapter_queued", "presentation_prepared",
    "result_presented", "main_action_started", "main_action_finished",
    "main_turn_completed", "response_window_closed",
)

# Identity fields carried by delivery-occurrence events. ``delivery_occurrence_id``
# distinguishes one delivery (an occurrence may be presented into several turns);
# ``completion_id`` is the originating child completion; ``turn_id``/``window_id``
# bind a presentation to the real started main-model request that observed it.
delivery_occurrence_identity_fields = (
    "delivery_occurrence_id", "completion_id", "turn_id", "window_id",
)

# Gateway-produced specialised-stimulus event types (Task 9). These are
# benchmark-owned audit facts: the gateway (not the adapter) decides when and how
# a designed timeout/crash, an implicit error, a live scope/dependency revision,
# a resource-pressure boundary, or a deadline update is produced and recorded.
# They are never adapter-emitted, so ``validate_adapter_event`` never sees them;
# ``validate_gateway_event`` checks their private evaluator structure before the
# kernel persists them as kernel_private facts.
GATEWAY_STIMULUS_EVENT_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "task_scope_revision": (
        "revision_id", "before_digest", "after_digest", "changed",
        "participant_visible", "expected_response_preserved",
    ),
    "dependency_graph_revision": (
        "revision_id", "before_digest", "after_digest", "changed",
        "affected_edges", "participant_visible", "expected_response_preserved",
    ),
    "resource_pressure": (
        "straggler_child_id", "applied", "active_children", "active_count",
        "resource", "concurrency_limit", "pool_remaining",
    ),
    "deadline_update": (
        "before_deadline", "after_deadline", "applied_before_response_window",
        "response_window_active", "reason",
    ),
    "child_terminal_outcome": (
        "child_id", "completion_id", "outcome", "designed", "was_in_flight",
        "detail",
    ),
}


# Capability RPC wire message types. These are *transport*, not adapter events:
# the adapter requests a kernel capability on stdout and the kernel answers on
# stdin. Raw transport messages never enter the event source and are never
# scored. The kernel may derive private audit events from capability execution
# (notably child_terminal_started/finished) without retaining the RPC envelope.
CAPABILITY_REQUEST = "capability_request"
CAPABILITY_RESPONSE = "capability_response"


@dataclass(frozen=True)
class EventEnvelope:
    """Immutable envelope stamped onto every event in the source.

    ``event`` is the underlying typed event payload; the envelope fields carry
    identity, causal link, timing, and stream membership. ``to_record`` flattens
    both into the JSONL object persisted to ``event_source.jsonl``.
    """

    event: dict[str, Any]
    event_id: str
    parent_event_id: str | None
    episode_id: str
    timestamp: float
    elapsed_ms: float
    seq: int
    actor: str
    visibility: str

    def to_record(self) -> dict[str, Any]:
        record = dict(self.event)
        record.update({
            "event_id": self.event_id,
            "parent_event_id": self.parent_event_id,
            "episode_id": self.episode_id,
            "timestamp": self.timestamp,
            "elapsed_ms": self.elapsed_ms,
            "seq": self.seq,
            "actor": self.actor,
            "visibility": self.visibility,
        })
        return record


ADAPTER_EVENT_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "participant_metadata": ("backend", "main_model", "child_model", "workspace_mode", "config_sha256"),
    "participant_runtime_metadata": ("model_observations",),
    "agent_progress": ("phase", "role"),
    "infrastructure_failure": ("component", "detail"),
    "ready": (),
    "fork_bundle_captured": ("bundle_id", "completion_payload_digest", "main_transcript_digest"),
    "child_spawned": ("child_id", "parent_id", "work_units"),
    "child_started": ("child_id",),
    "child_progress_checkpoint": ("child_id", "phase", "tokens"),
    # Result role is evaluator-owned. The kernel binds a completion to the
    # private workstream role from child_id; adapters cannot self-classify it.
    "child_completed": ("child_id", "completion_id", "payload"),
    "child_cancelled": ("child_id", "reason"),
    "child_token_budget_exhausted": ("child_id", "reason", "pool"),
    "child_turn_limit_exhausted": ("child_id", "reason", "pool"),
    "child_no_submission": ("child_id", "reason"),
    "delegation_validation_error": ("requested_workstream", "reason", "budget_consumed"),
    "main_action": ("action_id", "kind"),
    "child_path_promotion_result": (
        "action_id", "completion_id", "child_id", "source_path",
        "destination_path", "success", "exit_code",
    ),
    "result_consumed": ("completion_id", "action_id"),
    # Adapter-observed delivery-occurrence boundary (spec §3.3): the adapter
    # records a delivery once it has enqueued the occurrence and again once the
    # result is bound to a real started main-model request. Both carry the
    # occurrence/completion identity; presentation additionally binds turn/window.
    "adapter_queued": ("delivery_occurrence_id", "completion_id"),
    "result_presented": (
        "delivery_occurrence_id", "completion_id", "turn_id", "window_id",
    ),
    "artifact_committed": (
        "artifact_id", "version", "lineage_completion_ids", "observed_digest",
        "observed_path", "evaluator_observed",
    ),
    "episode_ended": (),
}


class ProtocolError(ValueError):
    pass


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def validate_adapter_event(event: dict[str, Any]) -> None:
    event_type = event.get("type")
    if event_type not in ADAPTER_EVENT_REQUIREMENTS:
        raise ProtocolError(f"unknown adapter event type: {event_type!r}")
    missing = [key for key in ADAPTER_EVENT_REQUIREMENTS[event_type] if key not in event]
    if missing:
        raise ProtocolError(f"{event_type}: missing required fields {missing}")
    if event_type == "child_spawned":
        if event["parent_id"] != "main":
            raise ProtocolError("scenario-eligible children must be created by parent_id='main'")
        if not isinstance(event["work_units"], list) or len(event["work_units"]) != 1:
            raise ProtocolError("child_spawned.work_units must contain exactly one explicit workstream")
    if event_type == "child_progress_checkpoint":
        if event["phase"] != "first_model_turn_finished":
            raise ProtocolError("child_progress_checkpoint.phase is invalid")
        if not isinstance(event["tokens"], int) or isinstance(event["tokens"], bool) or event["tokens"] < 0:
            raise ProtocolError("child_progress_checkpoint.tokens must be a non-negative integer")
    if event_type == "artifact_committed" and not isinstance(event["lineage_completion_ids"], list):
        raise ProtocolError("artifact lineage must be a list")
    if event_type == "artifact_committed":
        digest = str(event.get("observed_digest", ""))
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
            raise ProtocolError("artifact_committed.observed_digest must be SHA-256")
        if event.get("evaluator_observed") is not True:
            raise ProtocolError("artifact commit must be evaluator-observed")
    if event_type == "child_path_promotion_result":
        if not isinstance(event.get("success"), bool):
            raise ProtocolError("child_path_promotion_result.success must be boolean")
        exit_code = event.get("exit_code")
        if exit_code is not None and (
            not isinstance(exit_code, int) or isinstance(exit_code, bool)
        ):
            raise ProtocolError("child_path_promotion_result.exit_code must be integer or null")
    if event_type == "episode_ended":
        local_status = event.get("local_status")
        if local_status is not None and local_status not in {
            "completed", "incomplete", "budget_exhausted",
        }:
            raise ProtocolError("episode_ended.local_status is invalid")
        declared_success = event.get("declared_task_success")
        if declared_success is not None and not isinstance(declared_success, bool):
            raise ProtocolError("episode_ended.declared_task_success must be boolean")


def validate_gateway_event(event: dict[str, Any]) -> list[str]:
    """Validate a gateway-produced specialised-stimulus audit fact.

    Returns a list of error strings (empty when valid).  The gateway audit facts
    are kernel-private and never reach the participant, but their structure is
    protocol-checked so scoring/audit can rely on the before/after digests and
    in-flight proofs being present.
    """
    event_type = event.get("type")
    requirements = GATEWAY_STIMULUS_EVENT_REQUIREMENTS.get(str(event_type))
    if requirements is None:
        return []
    errors: list[str] = []
    missing = [key for key in requirements if key not in event]
    if missing:
        errors.append(f"{event_type}: missing required fields {missing}")
    if event_type == "dependency_graph_revision":
        edges = event.get("affected_edges")
        if not isinstance(edges, dict) or not edges:
            errors.append("dependency_graph_revision.affected_edges must be a non-empty dict")
        else:
            for edge_id, entry in edges.items():
                if not isinstance(entry, dict):
                    errors.append(f"dependency_graph_revision affected edge {edge_id!r} is not an object")
                    continue
                for key in ("before_digest", "after_digest"):
                    digest = str(entry.get(key, ""))
                    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                        errors.append(f"dependency_graph_revision edge {edge_id!r} {key} must be SHA-256")
    if event_type == "resource_pressure" and event.get("applied") is True:
        if event.get("straggler_child_id") not in event.get("active_children", []):
            errors.append("resource_pressure.straggler_child_id is not in active_children")
    return errors


@dataclass
class TraceRecorder:
    episode_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    _start_ns: int = field(default_factory=time.monotonic_ns)

    def record(self, event: dict[str, Any], source: str) -> dict[str, Any]:
        item = dict(event)
        item["source"] = source
        item["seq"] = len(self.events) + 1
        item["elapsed_ms"] = round((time.monotonic_ns() - self._start_ns) / 1_000_000, 3)
        item["episode_id"] = self.episode_id
        self.events.append(item)
        return item

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in self.events), encoding="utf-8")


def load_trace(path: Path) -> list[dict[str, Any]]:
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"{path}:{line_number}: {exc}") from exc
    return events
