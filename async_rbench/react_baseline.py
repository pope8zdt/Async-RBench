"""Blocking single-agent ReAct baseline for authoritative case capsules.

This module deliberately contains no child-agent, gateway, event-interruption,
or replanning machinery.  The model sees one tool result at a time and cannot
continue until that result has been returned by the harness.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def _stable_catalog(public: dict[str, Any], expected: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a deterministic action catalogue without exposing oracle labels."""
    causal = public.get("causal_record") or {}
    entries: list[dict[str, Any]] = []
    for item in list(causal.get("affected_work") or []):
        entries.append({
            "action_id": str(item["id"]),
            "kind": item.get("kind"),
            "app": item.get("app"),
            "function": item.get("function"),
            "description": item.get("description"),
        })
    for item in list(causal.get("prior_work") or []):
        entries.append({
            "action_id": str(item["id"]),
            "kind": item.get("kind"),
            "app": item.get("app"),
            "function": item.get("function"),
            "description": item.get("description"),
        })
    for action_id in list(expected.get("superseded_work_ids") or []):
        entries.append({
            "action_id": str(action_id),
            "kind": "provisional_action",
            "app": None,
            "function": "apply_provisional_action",
            "description": "A provisional action derived without the authoritative evidence.",
        })
    # Avoid teaching models that the first catalogue entries are the oracle.
    return sorted(
        entries,
        key=lambda item: hashlib.sha256(
            f"{public.get('case_id')}\0{item['action_id']}".encode("utf-8")
        ).hexdigest(),
    )


@dataclass
class ReActState:
    step: int = 0
    evidence_observed_at: int | None = None
    executed_actions: list[dict[str, Any]] = field(default_factory=list)
    final_inspections: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    finish_summary: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "evidence_observed_at": self.evidence_observed_at,
            "executed_actions": list(self.executed_actions),
            "final_inspections": list(self.final_inspections),
            "finished": self.finished,
            "finish_summary": self.finish_summary,
        }


class BlockingReActEnvironment:
    """A tiny deterministic environment whose tools always return synchronously."""

    TOOL_DESCRIPTIONS = [
        {
            "name": "inspect_current_state",
            "description": "Inspect already-completed work and the currently available action catalogue.",
            "arguments": {},
        },
        {
            "name": "query_authoritative_evidence",
            "description": "Synchronously obtain the authoritative evidence needed to resolve the task.",
            "arguments": {},
        },
        {
            "name": "execute_action",
            "description": "Execute one available action by action_id. The call blocks until completion.",
            "arguments": {"action_id": "string"},
        },
        {
            "name": "inspect_final_state",
            "description": "Inspect the resulting state after actions have completed.",
            "arguments": {},
        },
        {
            "name": "finish",
            "description": "Finish the task after checking the final state.",
            "arguments": {"summary": "string"},
        },
    ]

    def __init__(self, public: dict[str, Any], expected: dict[str, Any]):
        self.public = public
        self.expected = expected
        self.catalog = _stable_catalog(public, expected)
        self.catalog_by_id = {str(item["action_id"]): item for item in self.catalog}
        self.state = ReActState()
        self.trace: list[dict[str, Any]] = []

    def start_payload(self) -> dict[str, Any]:
        return {
            "case_id": self.public["case_id"],
            "task": self.public["source"]["instruction"],
            "execution_mode": "react_linear",
            "interaction_rule": (
                "Choose exactly one tool per turn. Every tool call is blocking: "
                "wait for its observation before choosing the next action."
            ),
            "tools": self.TOOL_DESCRIPTIONS,
            "response_shape": {"action": {"tool": "tool_name", "arguments": {}}},
        }

    def call(self, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments if isinstance(arguments, dict) else {}
        self.state.step += 1
        step = self.state.step
        if tool == "inspect_current_state":
            observation = {
                "already_completed": list((self.public.get("causal_record") or {}).get("prior_work") or []),
                "executed_in_this_episode": [item["action_id"] for item in self.state.executed_actions],
                "available_actions": self.catalog,
            }
            ok = True
        elif tool == "query_authoritative_evidence":
            first_observation = self.state.evidence_observed_at is None
            if first_observation:
                self.state.evidence_observed_at = step
            observation = {
                "authoritative_evidence": (self.public.get("causal_record") or {}).get("independent_event"),
                "status": "returned_synchronously",
                "note": (
                    "This is the authoritative observation. Use it to choose actions."
                    if first_observation
                    else "Cached observation returned unchanged; repeated queries provide no new information."
                ),
            }
            ok = True
        elif tool == "execute_action":
            action_id = str(arguments.get("action_id") or "")
            action = self.catalog_by_id.get(action_id)
            if action is None:
                observation = {"error": "unknown_action_id", "action_id": action_id}
                ok = False
            else:
                record = {"action_id": action_id, "step": step, "action": action}
                self.state.executed_actions.append(record)
                observation = {"status": "completed", "action": action}
                ok = True
        elif tool == "inspect_final_state":
            snapshot = {
                "step": step,
                "already_completed_ids": [
                    str(item["id"])
                    for item in list((self.public.get("causal_record") or {}).get("prior_work") or [])
                ],
                "executed_action_ids": [item["action_id"] for item in self.state.executed_actions],
            }
            self.state.final_inspections.append(snapshot)
            observation = {
                **snapshot,
                "next_step": "If the task is correct, call finish now; otherwise execute only the needed repair.",
            }
            ok = True
        elif tool == "finish":
            self.state.finished = True
            self.state.finish_summary = str(arguments.get("summary") or "")
            observation = {"status": "finished"}
            ok = True
        else:
            observation = {"error": "unknown_tool", "tool": tool}
            ok = False
        event = {
            "step": step,
            "tool": tool,
            "arguments": arguments,
            "ok": ok,
            "observation": observation,
        }
        self.trace.append(event)
        return observation


def score_react_state(
    public: dict[str, Any], expected: dict[str, Any], state: ReActState | dict[str, Any],
) -> dict[str, Any]:
    """Score only ordinary task evidence; no asynchronous lifecycle point exists."""
    state_dict = state.as_dict() if isinstance(state, ReActState) else dict(state)
    required = [str(value) for value in list(expected.get("affected_work_ids") or [])]
    superseded = {str(value) for value in list(expected.get("superseded_work_ids") or [])}
    allowed = set(required) | {
        str(item["id"])
        for item in list((public.get("causal_record") or {}).get("prior_work") or [])
    } | superseded
    executions = list(state_dict.get("executed_actions") or [])
    executed = [str(item.get("action_id") or "") for item in executions]
    executed_set = set(executed)
    evidence_at = state_dict.get("evidence_observed_at")
    required_steps = [
        int(item.get("step") or 0) for item in executions if str(item.get("action_id") or "") in set(required)
    ]
    evidence_before_action = (
        isinstance(evidence_at, int)
        and (not required_steps or evidence_at < min(required_steps))
    )
    latest_required_step = max(required_steps, default=0)
    inspections = list(state_dict.get("final_inspections") or [])
    closure_reverified = bool(state_dict.get("finished")) and any(
        int(item.get("step") or 0) > latest_required_step for item in inspections
    )

    points: list[dict[str, Any]] = []
    points.append({
        "id": "authoritative_evidence_acquired",
        "description": "The blocking authoritative observation was acquired before dependent actions.",
        "weight": 0.10,
        "passed": evidence_before_action,
    })
    action_mass = 0.60
    per_action = action_mass / len(required) if required else action_mass
    affected_by_id = {
        str(item["id"]): item
        for item in list((public.get("causal_record") or {}).get("affected_work") or [])
    }
    for index, action_id in enumerate(required, 1):
        item = affected_by_id.get(action_id) or {}
        points.append({
            "id": f"required_action_{index:02d}",
            "action_id": action_id,
            "description": str(item.get("description") or f"Complete required action {index}"),
            "weight": per_action,
            "passed": action_id in executed_set,
        })
    points.extend([
        {
            "id": "no_superseded_action",
            "description": "No provisional or superseded action was executed.",
            "weight": 0.10,
            "passed": not bool(executed_set & superseded),
        },
        {
            "id": "no_extraneous_or_duplicate_action",
            "description": "No unrelated, already-completed, unknown, or duplicate action was executed.",
            "weight": 0.10,
            "passed": (
                len(executed) == len(executed_set)
                and not bool(executed_set - set(required))
                and all(value in allowed for value in executed_set)
            ),
        },
        {
            "id": "final_state_reverified",
            "description": "The final state was inspected after the required work and before finish.",
            "weight": 0.10,
            "passed": closure_reverified,
        },
    ])
    # Floating division for per-action points is normalised at aggregation.
    total = sum(float(item["weight"]) for item in points if item["passed"])
    return {
        "case_id": public["case_id"],
        "execution_mode": "react_linear",
        "score": round(total, 8),
        "test_point_count": len(points),
        "passed_point_count": sum(bool(item["passed"]) for item in points),
        "unscored_point_count": 0,
        "test_points": points,
    }
