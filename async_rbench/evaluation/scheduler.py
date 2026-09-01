from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

from .protocol import canonical_digest


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
            if str(schedule_event.get("type") or "result_delivery") != "completion_replay":
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
                if str(event.get("type") or "result_delivery") == "result_delivery"
                and str(event.get("result") or "") == str(completion.get("result_kind") or "")
            ),
            {},
        )
        stale_truth, stale_reason = self._dynamic_stale_truth(completion, original_event)
        stale_visibility = str(original_event.get("stale_visibility", "explicit"))
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
                if str(event.get("type") or "result_delivery") in {
                    "result_delivery", "implicit_error_result",
                }
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
