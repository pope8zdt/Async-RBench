from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

from .protocol import canonical_digest
from .workspace_runtime import state_snapshot_digest

# Schedule-row kinds that govern the delivery of a *real* completion: a real
# ``child_completed`` whose ``result_kind`` matches a row of one of these kinds
# is delivered only when that row's trigger boundary is met (``_drain``).
# ``result_delivery`` / ``implicit_error_result`` are pure delivery rows;
# revision / pressure kinds carry a ``result`` role when the specialised
# stimulus is attached to a delivery (the in-tree after_artifacts authority
# rows).  Terminal kinds (``child_timeout`` / ``child_crash``) fabricate their
# own completion at the consumption seam and never govern a real completion.
DELIVERY_ROW_KINDS = frozenset({
    "result_delivery", "implicit_error_result",
    "task_scope_revision", "dependency_graph_revision", "resource_pressure",
})


@dataclass
class DeliveryController:
    execution_mode: str
    case_spec: dict[str, Any]
    min_initial_children: int = 2
    spawned: dict[str, dict[str, Any]] = field(default_factory=dict)
    completions: dict[str, dict[str, Any]] = field(default_factory=dict)
    delivered: set[str] = field(default_factory=set)
    consumed: set[str] = field(default_factory=set)
    replayed_schedule_events: set[str] = field(default_factory=set)
    delivery_order: list[str] = field(default_factory=list)
    committed_artifacts: set[str] = field(default_factory=set)
    main_actions: int = 0
    completion_action_ordinals: dict[str, int] = field(default_factory=dict)
    completion_held_at_monotonic: dict[str, float] = field(default_factory=dict)
    protocol_notes: list[str] = field(default_factory=list)
    # --- Real specialized-event mechanism state (Task 9) -------------------
    # Child lifecycle tracking so the gateway can *prove* a child was in flight
    # when a designed timeout/crash or resource-pressure boundary fires.
    running_children: set[str] = field(default_factory=set)
    # Pool/concurrency accounting observed at pressure boundaries.
    concurrency_limit: int | None = None
    child_pool_remaining: int | None = None
    # Evaluator-owned live-revision state (frozen scope + dependency graph).
    scope_snapshot: dict[str, Any] = field(default_factory=dict)
    dependency_graph_edges: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Effective benchmark-owned deadline (absolute wall clock) applied to a
    # response window, plus a public edge counter used for gateway occurrence ids.
    _effective_deadline_wall: float | None = None
    _response_window_active: bool = False
    _occurrence_ordinal: int = 0
    _delivery_occurrence_of_completion: dict[str, str] = field(default_factory=dict)
    # Designed-terminal stimuli declared in the case schedule that have already
    # been fired, so a child_started event can never double-fire a stimulus.
    _fired_stimulus_event_ids: set[str] = field(default_factory=set)
    # Kernel-private audit trails the runner materialises as private facts.
    revision_audits: list[dict[str, Any]] = field(default_factory=list)
    pressure_audits: list[dict[str, Any]] = field(default_factory=list)
    deadline_audits: list[dict[str, Any]] = field(default_factory=list)
    terminal_outcomes: list[dict[str, Any]] = field(default_factory=list)
    infrastructure_failures: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.execution_mode not in {"linear", "async"}:
            raise ValueError(f"unknown execution mode {self.execution_mode}")
        self.schedule = list(
            ((self.case_spec.get("scenarios") or {}).get(self.execution_mode) or {}).get("events", [])
        )

    @property
    def gate_open(self) -> bool:
        return self.execution_mode == "linear" or len(self.spawned) >= self.min_initial_children

    def on_spawn(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        # Linear uses the same initial spawn interface as async execution;
        # the scaffold queues those children and limits actual child_started
        # intervals to one. Queued spawn requests are not execution overlap.
        self.spawned[event["child_id"]] = event
        return self._drain()

    def on_child_started(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Record that an isolated child workspace is live and in flight.

        The gateway uses this proof to gate designed terminal outcomes and
        resource-pressure activation: a designed ``child_timeout`` /
        ``child_crash`` / ``resource_pressure`` stimulus is only valid for a
        child that actually left ``starting`` into ``running``.
        """
        child_id = str(event.get("child_id") or "")
        if child_id:
            self.running_children.add(child_id)
        return []

    def on_complete(
        self, event: dict[str, Any], contract_validation: Any | None = None,
    ) -> list[dict[str, Any]]:
        event = dict(event)
        event["payload_sha256"] = canonical_digest(event["payload"])
        event["_contract_valid"] = bool(
            contract_validation is None or contract_validation.valid
        )
        event["_contract_reason_codes"] = list(
            getattr(contract_validation, "reason_codes", ())
        )
        self.completions[event["completion_id"]] = event
        self.completion_action_ordinals[event["completion_id"]] = self.main_actions
        self.completion_held_at_monotonic[event["completion_id"]] = time.monotonic()
        # A completion is no longer a running child; a later designed terminal
        # outcome must not be attached to an already-resolved child.
        self.running_children.discard(str(event.get("child_id") or ""))
        return self._drain()

    def inject_evaluator_result(
        self, *, injection_id: str, result_kind: str, payload: Any,
    ) -> list[dict[str, Any]]:
        """Register a case-private receipt for later gateway delivery.

        The evaluator owns the receipt file and creates this completion before
        the adapter starts.  It remains held by the normal schedule and reaches
        the participant only as a public ``result_delivered`` message.
        """
        if not injection_id or not result_kind:
            raise ValueError("evaluator injection requires id and result_kind")
        return self.on_complete({
            "type": "evaluator_completed",
            "child_id": "evaluator",
            "completion_id": f"evaluator:{injection_id}",
            "result_kind": result_kind,
            "payload": payload,
        })

    # --- Real specialized-event mechanisms (Task 9) -------------------------
    #
    # These are the gateway-owned interfaces that *produce* the specialised
    # stimuli.  The gateway is the only actor allowed to classify a child
    # outcome as designed vs infrastructure, to own live scope/dependency state,
    # and to prove a child is in flight before applying pressure.

    def apply_child_terminal_outcome(
        self, *, child_id: str, completion_id: str, result_kind: str,
        payload: Any, outcome: str, detail: str, designed: bool,
        benchmark_event_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Produce a model-visible terminal outcome for an in-flight child.

        ``outcome`` is ``"timeout"`` or ``"crash"``.  A *designed* termination is
        a scored, model-visible stimulus: the child was running, the terminal
        outcome is benchmark-owned, and it is delivered to the main model.  An
        infrastructure termination (provider outage / workspace start failure) is
        recorded as an unscored ``infrastructure_failure`` and never delivered —
        the benchmark failed, not the model.  A designed outcome additionally
        requires the gateway to have observed the child in flight (spec §6.2).
        """
        child_id = str(child_id)
        was_in_flight = child_id in self.running_children
        if not designed:
            self.running_children.discard(child_id)
            self.infrastructure_failures.append({
                "type": "infrastructure_failure",
                "component": "child_terminal",
                "child_id": child_id,
                "outcome": outcome,
                "detail": detail,
            })
            return []
        if not was_in_flight:
            self.protocol_notes.append(
                f"designed {outcome} refused: child {child_id!r} was not in flight"
            )
            self.terminal_outcomes.append({
                "type": "child_terminal_outcome",
                "child_id": child_id, "completion_id": completion_id,
                "outcome": outcome, "designed": True, "was_in_flight": False,
                "detail": detail,
            })
            return []
        self.running_children.discard(child_id)
        completion = {
            "type": "child_completed",
            "child_id": child_id,
            "completion_id": completion_id,
            "result_kind": result_kind,
            "payload": payload,
            "payload_sha256": canonical_digest(payload),
            "_contract_valid": True,
            "_contract_reason_codes": (),
        }
        self.completions[completion_id] = completion
        self.completion_action_ordinals[completion_id] = self.main_actions
        self.completion_held_at_monotonic[completion_id] = time.monotonic()
        schedule_event = {"stimulus_type": "result_delivery", "result": result_kind}
        if benchmark_event_id:
            schedule_event["id"] = benchmark_event_id
        delivery = self._delivery(completion, schedule_event, False)
        delivery["evaluator_designed_failure"] = True
        delivery["terminal_outcome"] = outcome
        delivery["evaluator_terminal_reason"] = detail
        self.terminal_outcomes.append({
            "type": "child_terminal_outcome",
            "child_id": child_id, "completion_id": completion_id,
            "outcome": outcome, "designed": True, "was_in_flight": True,
            "detail": detail,
        })
        return [delivery]

    def consume_declared_stimuli(
        self, event: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Fire the live stimuli a case declares in its schedule (spec §6.2).

        This is the consumption seam the runner drives from ``run_episode`` on
        each ``child_started``.  Two families of schedule row exist:

        * **Delivery rows** — rows carrying a declared ``result`` role
          (``result_delivery``, ``implicit_error_result``, and the revision /
          pressure rows the swe/tbn cases stamp onto their after_artifacts
          authority results) are governed by ``_drain``/``_delivery`` and are
          ignored here.
        * **Live rows** — rows with no result role — are consumed at the child
          boundary: ``child_timeout`` / ``child_crash`` fire on the named
          child's ``child_started``; ``resource_pressure`` fires when its
          designated straggler starts; ``task_scope_revision`` /
          ``dependency_graph_revision`` and ``deadline_update`` fire once at the
          first child boundary (there is no later live boundary in this seam).

        Every declared row fires at most once, keyed by its ``id``; repeated
        ``child_started`` events are therefore idempotent.  A malformed
        ``deadline_update`` (missing or non-numeric ``deadline_wall``) is
        consumed once under its id and recorded as a protocol note rather than
        crashing the episode (see ``validate_scenario_events`` for the
        taxonomy-side numeric requirement).
        """
        if self.execution_mode != "async" or event.get("type") != "child_started":
            return []
        child_id = str(event.get("child_id") or "")
        deliveries: list[dict[str, Any]] = []
        for schedule_event in self.schedule:
            event_type = str(schedule_event.get("stimulus_type") or "")
            if event_type not in {
                "child_timeout", "child_crash", "resource_pressure",
                "task_scope_revision", "dependency_graph_revision", "deadline_update",
            }:
                continue
            # A result-bearing non-terminal row is a delivery row (see docstring).
            if event_type in DELIVERY_ROW_KINDS and schedule_event.get("result") is not None:
                continue
            event_id = str(schedule_event.get("id") or "")
            if event_id in self._fired_stimulus_event_ids:
                continue
            if event_type in {"child_timeout", "child_crash"}:
                if str(schedule_event.get("child_id") or "") != child_id:
                    continue
            elif event_type == "resource_pressure":
                if str(schedule_event.get("straggler_child_id") or "") != child_id:
                    continue
            if event_type == "deadline_update":
                # A deadline_update row is consumed at most once under its declared
                # id.  A malformed declaration degrades to a single protocol note
                # (recorded under the id so it is not re-evaluated on every child
                # boundary) instead of crashing the episode with a bare float().
                if event_id:
                    self._fired_stimulus_event_ids.add(event_id)
                deadline_wall_raw = schedule_event.get("deadline_wall")
                if deadline_wall_raw is None:
                    self.protocol_notes.append(
                        f"declared deadline_update {event_id!r} ignored: missing deadline_wall"
                    )
                    continue
                try:
                    deadline_wall = float(deadline_wall_raw)
                except (TypeError, ValueError):
                    self.protocol_notes.append(
                        f"declared deadline_update {event_id!r} ignored: "
                        f"deadline_wall {deadline_wall_raw!r} is not numeric"
                    )
                    continue
                self.apply_deadline_update(
                    deadline_wall=deadline_wall,
                    reason=str(schedule_event.get("reason") or "case_declared"),
                )
                continue
            self._fired_stimulus_event_ids.add(event_id)
            completion_id = str(schedule_event.get(
                "completion_id", f"terminal:{event_id}",
            ))
            result_kind = str(schedule_event.get("result") or schedule_event.get("result_kind") or "")
            payload = schedule_event.get("payload") or {}
            detail = str(schedule_event.get("outcome_detail") or "designed child terminal")
            if event_type == "child_timeout":
                deliveries.extend(self.apply_child_terminal_outcome(
                    child_id=child_id, completion_id=completion_id,
                    result_kind=result_kind, payload=payload, outcome="timeout",
                    detail=detail, designed=True, benchmark_event_id=event_id,
                ))
            elif event_type == "child_crash":
                deliveries.extend(self.apply_child_crash(
                    child_id=child_id, completion_id=completion_id,
                    result_kind=result_kind, payload=payload,
                    crash_source=str(schedule_event.get("crash_source") or "case_designed"),
                    detail=detail, benchmark_event_id=event_id,
                ))
            elif event_type == "resource_pressure":
                self.apply_resource_pressure(
                    straggler_child_id=child_id,
                    resource=str(schedule_event.get("resource") or "concurrency_slot"),
                    limit=schedule_event.get("limit"),
                    pool_remaining=schedule_event.get("pool_remaining"),
                )
            elif event_type == "task_scope_revision":
                self.apply_task_scope_revision(
                    revision_id=str(schedule_event.get("revision_id") or event_id),
                    new_scope=dict(schedule_event.get("new_scope") or {}),
                    participant_visible_fields=dict(
                        schedule_event.get("participant_visible_fields") or {}
                    ),
                    expected_response=schedule_event.get("expected_response"),
                )
            elif event_type == "dependency_graph_revision":
                self.apply_dependency_graph_revision(
                    revision_id=str(schedule_event.get("revision_id") or event_id),
                    new_edges={
                        str(edge): tuple(value)
                        for edge, value in dict(schedule_event.get("new_edges") or {}).items()
                    },
                    participant_visible_fields=dict(
                        schedule_event.get("participant_visible_fields") or {}
                    ),
                    expected_response=schedule_event.get("expected_response"),
                )
        return deliveries

    def apply_child_crash(
        self, *, child_id: str, completion_id: str, result_kind: str,
        payload: Any, crash_source: str, detail: str,
        benchmark_event_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Produce a designed child-crash stimulus, or park an infra crash.

        ``crash_source == "case_designed"`` means the crash is part of the case
        scenario: it is scored and delivered.  Any provider/workspace/infrastructure
        crash is converted to an unscored infrastructure failure instead.
        """
        return self.apply_child_terminal_outcome(
            child_id=child_id, completion_id=completion_id,
            result_kind=result_kind, payload=payload, outcome="crash",
            detail=detail, designed=str(crash_source) == "case_designed",
            benchmark_event_id=benchmark_event_id,
        )

    def apply_task_scope_revision(
        self, *, revision_id: str, new_scope: dict[str, Any],
        participant_visible_fields: dict[str, Any],
        expected_response: Any,
    ) -> list[dict[str, Any]]:
        """Revise the frozen scope state while work is in flight.

        Records the before/after scope digest, exposes only the participant-visible
        revised information, and preserves the private expected response untouched.
        """
        before_digest = state_snapshot_digest(self.scope_snapshot)
        self.scope_snapshot = dict(new_scope)
        after_digest = state_snapshot_digest(self.scope_snapshot)
        self.revision_audits.append({
            "type": "task_scope_revision",
            "revision_id": revision_id,
            "before_digest": before_digest,
            "after_digest": after_digest,
            "changed": before_digest != after_digest,
            "participant_visible": dict(participant_visible_fields),
            "expected_response_digest": canonical_digest(expected_response),
            "expected_response_preserved": True,
            "private_expected_response_hidden": not any(
                str(expected_response) in str(value)
                for value in participant_visible_fields.values()
            ),
        })
        return []

    def apply_dependency_graph_revision(
        self, *, revision_id: str, new_edges: dict[str, tuple[str, ...]],
        participant_visible_fields: dict[str, Any],
        expected_response: Any,
    ) -> list[dict[str, Any]]:
        """Revise the dependency graph and record per-edge before/after digests.

        Only the affected edges are reported with a before/after digest; untouched
        edges are omitted so the revision surfaces exactly what changed.
        """
        before_digest = canonical_digest(self.dependency_graph_edges)
        affected: dict[str, dict[str, str]] = {}
        for edge_id, new_value in dict(new_edges).items():
            old_value = self.dependency_graph_edges.get(edge_id, ())
            affected[edge_id] = {
                "before_digest": canonical_digest(old_value),
                "after_digest": canonical_digest(new_value),
                "changed": canonical_digest(old_value) != canonical_digest(new_value),
            }
        self.dependency_graph_edges = dict(new_edges)
        after_digest = canonical_digest(self.dependency_graph_edges)
        self.revision_audits.append({
            "type": "dependency_graph_revision",
            "revision_id": revision_id,
            "before_digest": before_digest,
            "after_digest": after_digest,
            "changed": before_digest != after_digest,
            "affected_edges": affected,
            "new_edges": {edge: list(value) for edge, value in dict(new_edges).items()},
            "participant_visible": dict(participant_visible_fields),
            "expected_response_digest": canonical_digest(expected_response),
            "expected_response_preserved": True,
        })
        return []

    def apply_resource_pressure(
        self, *, straggler_child_id: str, resource: str = "concurrency_slot",
        limit: int | None = None, pool_remaining: int | None = None,
    ) -> list[dict[str, Any]]:
        """Activate resource pressure only when the designated straggler is live.

        The gateway must prove the straggler is still in flight (spec §6.2).
        Records active children, the pool remaining, the concurrency limit, and
        the before/after pressure values.  A straggler that already resolved
        cannot be under pressure, so the activation is refused.
        """
        straggler = str(straggler_child_id)
        active = sorted(self.running_children)
        if straggler not in self.running_children:
            self.pressure_audits.append({
                "type": "resource_pressure", "applied": False,
                "straggler_child_id": straggler, "straggler_in_flight": False,
                "active_children": active, "active_count": len(active),
                "resource": resource, "concurrency_limit": limit,
                "pool_remaining": pool_remaining,
                "before_concurrency_limit": self.concurrency_limit,
                "before_pool_remaining": self.child_pool_remaining,
                "reason": "straggler was not in flight",
            })
            return []
        before_limit, before_pool = self.concurrency_limit, self.child_pool_remaining
        self.concurrency_limit = limit
        self.child_pool_remaining = pool_remaining
        self.pressure_audits.append({
            "type": "resource_pressure", "applied": True,
            "straggler_child_id": straggler, "straggler_in_flight": True,
            "active_children": active, "active_count": len(active),
            "resource": resource, "concurrency_limit": limit,
            "pool_remaining": pool_remaining,
            "before_concurrency_limit": before_limit,
            "after_concurrency_limit": limit,
            "before_pool_remaining": before_pool,
            "after_pool_remaining": pool_remaining,
        })
        return []

    def apply_deadline_update(
        self, *, deadline_wall: float, reason: str,
    ) -> list[dict[str, Any]]:
        """Apply a new benchmark-owned deadline before a response window.

        Records the before/after deadline and whether the update was applied
        before any response window opened.  A deadline update that fires after a
        response window is already open is still recorded but carries the
        ``applied_before_response_window`` flag as False, exposing that the
        participant saw the previous deadline for the open window.
        """
        before = self._effective_deadline_wall
        self._effective_deadline_wall = float(deadline_wall)
        self.deadline_audits.append({
            "type": "deadline_update",
            "before_deadline": before,
            "after_deadline": self._effective_deadline_wall,
            "applied_before_response_window": self._response_window_active is False,
            "response_window_active": self._response_window_active,
            "reason": reason,
        })
        return []

    def on_response_window(self, active: bool) -> list[dict[str, Any]]:
        """Track response-window liveness for the deadline-update boundary."""
        self._response_window_active = bool(active)
        return []

    def on_main_action(self, _: dict[str, Any]) -> list[dict[str, Any]]:
        self.main_actions += 1
        return self._drain()

    def on_observation(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Advance evaluator-owned delivery boundaries from protocol facts.

        Dynamic events may be held until the participant has produced a real
        provisional state.  The trigger is tied to artifact commits rather
        than wall-clock time or a model-specific action ordinal, making the
        same causal boundary reproducible across models and repeat runs.
        """
        if event.get("type") == "artifact_committed":
            artifact_id = str(event.get("artifact_id") or "")
            if artifact_id:
                self.committed_artifacts.add(artifact_id)
        return self._drain()

    def on_consumed(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Record that main explicitly accepted a delivered completion for use.

        Consumed state lives on the controller so the gateway, scoring, and
        replay all read the same authoritative set instead of each re-deriving
        it from ``result_consumed`` events.
        """
        completion_id = str(event["completion_id"])
        already_consumed = completion_id in self.consumed
        self.consumed.add(completion_id)
        if already_consumed or self.execution_mode != "async":
            return []
        completion = self.completions.get(completion_id)
        if completion is None or not completion.get("_contract_valid", True):
            return []
        deliveries: list[dict[str, Any]] = []
        for schedule_event in self.schedule:
            if str(schedule_event.get("stimulus_type") or "result_delivery") != "completion_replay":
                continue
            event_id = str(schedule_event.get("id") or "")
            if event_id in self.replayed_schedule_events:
                continue
            if schedule_event.get("trigger") != "after_consumed":
                continue
            if str(schedule_event.get("replay_of_result") or "") != str(
                completion.get("result_kind") or ""
            ):
                continue
            self.replayed_schedule_events.add(event_id)
            deliveries.append(self._replay_delivery(completion, schedule_event))
        return deliveries

    def force_release(self) -> list[dict[str, Any]]:
        deliveries = self._drain(force=True)
        if len(self.delivered) != len(self.completions):
            self.protocol_notes.append("not all child completions were deliverable under the requested schedule")
        return deliveries

    def deadline_release(self) -> list[dict[str, Any]]:
        """Release held results at a registered benchmark-owned deadline.

        This differs from shutdown force-release: the adapter is still alive,
        the result is sent to the participant, and the ordering remains an
        evaluator-controlled part of the designed scenario.
        """
        return self._drain(
            force=True, force_controlled=True,
            fallback_reason="max_hold_seconds",
        )

    @staticmethod
    def _payload_field(completion: dict[str, Any] | None, field_name: str) -> str | None:
        if not completion:
            return None
        payload = completion.get("payload")
        if not isinstance(payload, dict):
            return None
        for container in (payload.get("evidence"), payload):
            if isinstance(container, dict) and container.get(field_name) is not None:
                value = str(container[field_name]).strip()
                return value or None
        return None

    @staticmethod
    def _same_revision(left: str, right: str) -> bool:
        left = left.strip().lower()
        right = right.strip().lower()
        if left == right:
            return True
        hexadecimal = set("0123456789abcdef")
        if (
            len(left) >= 7 and len(right) >= 7
            and set(left) <= hexadecimal and set(right) <= hexadecimal
        ):
            return left.startswith(right) or right.startswith(left)
        return False

    @staticmethod
    def _evidence_value(completion: dict[str, Any], field_name: str) -> Any:
        payload = completion.get("payload")
        if not isinstance(payload, dict):
            return None
        evidence = payload.get("evidence")
        if not isinstance(evidence, dict):
            return None
        return evidence.get(field_name)

    def _implicit_error_truth(
        self, completion: dict[str, Any], schedule_event: dict[str, Any],
    ) -> tuple[bool | None, str]:
        """Decide whether an ``implicit_error_result`` delivery hides a failure.

        The payload is structurally valid (it already passed the completion
        contract; ``_contract_valid`` is true), so the delivery is model-visible.
        The *private* signal that the reported result is actually a failure comes
        either from the case's ``implicit_error_predicate`` or, when no predicate
        is declared, from the schedule event's declared stimulus kind itself being
        the private signal.
        """
        if str(schedule_event.get("stimulus_type") or "result_delivery") != "implicit_error_result":
            return None, "not an implicit error schedule event"
        spec = self.case_spec.get("implicit_error_predicate") or {}
        field_name = str(spec.get("evidence_field") or "")
        if spec.get("type") != "evidence_marker" or not field_name:
            return True, "implicit_error_result schedule event"
        value = self._evidence_value(completion, field_name)
        if value is None:
            return None, f"missing implicit failure evidence field {field_name!r}"
        marker = spec.get("marker")
        if marker is True:
            return value is True, f"evidence {field_name} is truthy"
        if isinstance(marker, (int, float)) and not isinstance(marker, bool):
            numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
            return bool(numeric and value == marker), f"evidence {field_name} == {marker}"
        return str(value) == str(marker), f"evidence {field_name} == {marker!r}"

    def _dynamic_stale_truth(
        self, completion: dict[str, Any], schedule_event: dict[str, Any],
    ) -> tuple[bool | None, str]:
        predicate = self.case_spec.get("stale_predicate") or {}
        superseded_kind = self.case_spec.get("superseded_result_kind")
        delivered_authorities = [
            self.completions[completion_id]
            for completion_id in self.delivery_order
            if self.completions[completion_id].get("result_kind")
            == self.case_spec.get("authoritative_result_kind")
            and self.completions[completion_id].get("_contract_valid", True)
        ]
        compare_revision = bool(
            predicate
            and self.execution_mode == "async"
            and completion.get("result_kind") == superseded_kind
            and delivered_authorities
        )
        if not compare_revision:
            return bool(schedule_event.get("stale", False)), "scheduled event truth"
        if predicate.get("type") != "revision_mismatch":
            return None, "unsupported evaluator stale predicate"
        authoritative = delivered_authorities[-1]
        authoritative_fields = list(predicate.get("authoritative_fields") or [])
        superseded_fields = list(predicate.get("superseded_fields") or [])
        if len(authoritative_fields) != len(superseded_fields) or not authoritative_fields:
            return None, "malformed revision comparison contract"
        comparisons = []
        for authority_field, superseded_field in zip(authoritative_fields, superseded_fields):
            authority_value = self._payload_field(authoritative, str(authority_field))
            superseded_value = self._payload_field(completion, str(superseded_field))
            if authority_value is None or superseded_value is None:
                return None, f"missing observed revision fields {authority_field}/{superseded_field}"
            comparisons.append((authority_field, authority_value, superseded_field, superseded_value))
        mismatches = [
            f"{superseded_field}={superseded_value} != {authority_field}={authority_value}"
            for authority_field, authority_value, superseded_field, superseded_value in comparisons
            if not self._same_revision(authority_value, superseded_value)
        ]
        return bool(mismatches), "; ".join(mismatches) if mismatches else "observed revisions match"

    def _delivery(
        self, completion: dict[str, Any], schedule_event: dict[str, Any] | None,
        controlled: bool, fallback_reason: str | None = None,
    ) -> dict[str, Any]:
        completion_id = completion["completion_id"]
        self.delivered.add(completion_id)
        self.delivery_order.append(completion_id)
        schedule_event = schedule_event or {}
        stale_truth, stale_reason = self._dynamic_stale_truth(completion, schedule_event)
        replacement_is_latent = bool(
            not schedule_event
            and self.execution_mode == "async"
            and completion.get("result_kind") == self.case_spec.get("superseded_result_kind")
        )
        stale_visibility = str(schedule_event.get(
            "stale_visibility", "latent" if replacement_is_latent else "explicit"
        ))
        if not completion.get("_contract_valid", True):
            rejected = {
                "type": "result_rejected",
                "child_id": completion["child_id"],
                "completion_id": completion_id,
                "result_kind": completion["result_kind"],
                "reason_codes": list(completion.get("_contract_reason_codes") or []),
                "benchmark_event_id": schedule_event.get("id"),
                "controlled_order": controlled,
            }
            if fallback_reason:
                rejected["delivery_fallback_reason"] = fallback_reason
            return rejected
        delivered = {
            "type": "result_delivered",
            "child_id": completion["child_id"],
            "completion_id": completion_id,
            "result_kind": completion["result_kind"],
            "payload": completion["payload"],
            "payload_sha256": completion["payload_sha256"],
            "stale": bool(stale_truth) if stale_visibility == "explicit" else False,
            "stale_visibility": stale_visibility,
            "evaluator_stale": stale_truth,
            "evaluator_stale_measurable": stale_truth is not None,
            "evaluator_stale_reason": stale_reason,
            "benchmark_event_id": schedule_event.get("id"),
            "invalidates_artifacts": list(schedule_event.get("invalidates_artifacts", [])),
            "reopens_milestones": list(schedule_event.get("reopens_milestones", [])),
            "controlled_order": controlled,
        }
        if fallback_reason:
            delivered["delivery_fallback_reason"] = fallback_reason
        # Gateway-owned occurrence identity (spec §3.3): one delivery occurrence
        # per released delivery. Replay creates a *new* occurrence under the same
        # completion, so the gateway occurrence id is the join key for replay.
        self._occurrence_ordinal += 1
        delivered["delivery_occurrence_id"] = f"gateway-occ-{self._occurrence_ordinal}"
        self._delivery_occurrence_of_completion[completion_id] = delivered["delivery_occurrence_id"]
        if str(schedule_event.get("stimulus_type") or "result_delivery") == "implicit_error_result":
            implicit_error, implicit_reason = self._implicit_error_truth(
                completion, schedule_event,
            )
            delivered["evaluator_implicit_error"] = implicit_error
            delivered["evaluator_implicit_error_measurable"] = implicit_error is not None
            delivered["evaluator_implicit_error_reason"] = implicit_reason
        return delivered

    def _replay_delivery(
        self, completion: dict[str, Any], schedule_event: dict[str, Any],
    ) -> dict[str, Any]:
        """Replay one accepted completion without inventing a child completion.

        The public projection is intentionally indistinguishable from another
        delivery of the same completion ID. Replay identity remains evaluator
        truth and is joined back only inside scoring.
        """
        original_event = next(
            (
                event for event in self.schedule
                if str(event.get("stimulus_type") or "result_delivery") == "result_delivery"
                and str(event.get("result") or "") == str(completion.get("result_kind") or "")
            ),
            {},
        )
        stale_truth, stale_reason = self._dynamic_stale_truth(completion, original_event)
        stale_visibility = str(original_event.get("stale_visibility", "explicit"))
        # A replay is a *new* gateway occurrence, not a cloned completion. It
        # keeps the originating completion_id but receives a fresh occurrence id
        # and records the original occurrence it replays (spec §3.3 / Task 9).
        self._occurrence_ordinal += 1
        return {
            "type": "result_delivered",
            "child_id": completion["child_id"],
            "completion_id": completion["completion_id"],
            "result_kind": completion["result_kind"],
            "payload": completion["payload"],
            "payload_sha256": completion["payload_sha256"],
            "stale": bool(stale_truth) if stale_visibility == "explicit" else False,
            "stale_visibility": stale_visibility,
            "evaluator_stale": stale_truth,
            "evaluator_stale_measurable": stale_truth is not None,
            "evaluator_stale_reason": stale_reason,
            "benchmark_event_id": schedule_event.get("id"),
            "invalidates_artifacts": [],
            "reopens_milestones": [],
            "controlled_order": True,
            "replayed": True,
            "delivery_occurrence_id": f"gateway-occ-{self._occurrence_ordinal}",
            "replay_of_occurrence_id": self._delivery_occurrence_of_completion.get(
                str(completion["completion_id"])
            ),
            "replay_of_completion_id": completion["completion_id"],
        }

    def _drain(
        self, force: bool = False, *, force_controlled: bool = False,
        fallback_reason: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.gate_open and not force:
            return []
        pending = [value for key, value in self.completions.items() if key not in self.delivered]
        if not pending:
            return []
        if self.execution_mode == "linear":
            return [
                self._delivery(
                    item, None, not force or force_controlled, fallback_reason,
                )
                for item in pending
            ]

        # Async results follow actual child completion order. A case may hold an
        # evaluator-owned authority until declared prerequisite result roles have
        # been delivered. Unlike an artifact trigger this boundary is guaranteed
        # by the harness and cannot deadlock on a participant strategy choice.
        if self.execution_mode == "async":
            by_result = {
                str(event.get("result")): event for event in self.schedule
                if str(event.get("stimulus_type") or "result_delivery") in DELIVERY_ROW_KINDS
                and event.get("result") is not None
            }
            deliverable = []
            while True:
                progress = False
                pending = [
                    value for key, value in self.completions.items()
                    if key not in self.delivered
                ]
                delivered_result_kinds = {
                    str(self.completions[completion_id].get("result_kind") or "")
                    for completion_id in self.delivery_order
                }
                for item in pending:
                    schedule_event = by_result.get(str(item.get("result_kind")))
                    trigger = str((schedule_event or {}).get("trigger") or "immediate")
                    item_fallback_reason = fallback_reason
                    if trigger == "after_artifacts_committed" and not force:
                        prerequisites = {
                            str(artifact_id)
                            for artifact_id in (schedule_event or {}).get("after_artifacts", [])
                        }
                        if not prerequisites.issubset(self.committed_artifacts):
                            held_after = self.completion_action_ordinals.get(
                                str(item.get("completion_id")), self.main_actions,
                            )
                            max_actions = int(
                                (schedule_event or {}).get("max_hold_main_actions", 4)
                            )
                            if self.main_actions - held_after < max_actions:
                                continue
                            item_fallback_reason = "max_hold_main_actions"
                    if trigger == "after_results_delivered" and not force:
                        prerequisites = {
                            str(result_kind)
                            for result_kind in (schedule_event or {}).get("after_results", [])
                        }
                        if not prerequisites.issubset(delivered_result_kinds):
                            held_after = self.completion_action_ordinals.get(
                                str(item.get("completion_id")), self.main_actions,
                            )
                            max_actions = int(
                                (schedule_event or {}).get("max_hold_main_actions", 4)
                            )
                            if self.main_actions - held_after < max_actions:
                                continue
                            item_fallback_reason = "max_hold_main_actions"
                    deliverable.append(self._delivery(
                        item, schedule_event, not force or force_controlled,
                        item_fallback_reason,
                    ))
                    progress = True
                if not progress:
                    break
            return deliverable
        raise AssertionError(f"unreachable execution mode: {self.execution_mode}")

    def result_bundle_digest(self) -> str:
        bundle = sorted(
            (item["result_kind"], item.get("payload_sha256") or canonical_digest(item["payload"]))
            for item in self.completions.values()
        )
        return canonical_digest(bundle)

    def has_held_completion(self) -> bool:
        return any(completion_id not in self.delivered for completion_id in self.completions)

    def remaining_hold_seconds(
        self, grace_sec: float, *, now: float | None = None,
    ) -> float | None:
        """Return the absolute wall-clock time left for the oldest held result.

        The runner previously restarted a relative ``readline`` timeout after
        every adapter event. A slow or chatty participant could therefore hold
        a completion far beyond the configured grace. The deadline is now
        anchored to the instant the gateway first accepted the completion.
        """
        held = [
            self.completion_held_at_monotonic[completion_id]
            for completion_id in self.completions
            if completion_id not in self.delivered
            and completion_id in self.completion_held_at_monotonic
        ]
        if not held:
            return None
        current = time.monotonic() if now is None else now
        return max(0.0, min(held) + float(grace_sec) - current)
