"""Protocol conformance checks (Layer 4).

Each check tests a *protocol* invariant — never task capability. The suite is
deliberately decoupled from the live scoring path: it reads an episode's
recorded events (or exercises a kernel invariant directly) and reports a
pass/fail per invariant.

Checks cover the fixed protocol-3 public/private and lineage invariants.
"""

from __future__ import annotations

import io
import json
from dataclasses import asdict, dataclass
from types import SimpleNamespace
from typing import Any, Callable

from ..evaluation.event_store import strip_for_adapter
from ..evaluation.protocol import validate_adapter_event
from ..evaluation.case_contract import find_private_fields, public_delivery
from ..evaluation.event_taxonomy import (
    validate_event_taxonomy,
    validate_event_theme_fixtures,
)
from ..profiles.reference_scaffold_api.gateway import ProtocolEmitter
from ..evaluation.scheduler import DeliveryController
from ..evaluation.workspace_runtime import (
    DisabledWorkspaceRuntime,
    DockerWorkspaceRuntime,
    build_workspace_runtime,
    event_assets_for_workstreams,
)


@dataclass(frozen=True)
class CheckResult:
    test_id: str
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# A check returns ``(passed, detail)``; ``run_checks`` stamps test identity.
CheckFn = Callable[[list[dict[str, Any]], dict[str, Any]], tuple[bool, str]]


# --- registry -----------------------------------------------------------------

CONFORMANCE_TESTS: tuple[dict[str, str], ...] = (
    {
        "id": "no_pre_delivery_leak",
        "name": "pre-delivery leakage",
        "description": "a completion's content is never referenced by the adapter "
                       "before the gateway delivers it, and hidden evaluator truth is stripped",
    },
    {
        "id": "child_workspace_isolation",
        "name": "child workspace isolation",
        "description": "workspace runtime maps container_clone/disabled to isolated implementations",
    },
    {
        "id": "gateway_delivery_enforced",
        "name": "result gateway enforcement",
        "description": "every completion is gateway-delivered before it may be consumed",
    },
    {
        "id": "stale_result_rejection",
        "name": "stale result rejection",
        "description": "the evaluator stale predicate flags a superseded revision as stale",
    },
    {
        "id": "artifact_lineage_valid",
        "name": "artifact lineage validity",
        "description": "artifact/verification lineage only references consumed completions",
    },
    {
        "id": "event_asset_scoping",
        "name": "event-asset distribution",
        "description": "event assets are scoped to the workstreams of the child that requests them",
    },
    {
        "id": "private_truth_projection",
        "name": "private truth projection",
        "description": "participant-visible start and gateway shapes contain no evaluator-private keys",
    },
    {
        "id": "verifier_post_episode",
        "name": "verifier post-episode injection",
        "description": "the hidden verifier records its result only after episode end",
    },
    {
        "id": "promotion_outcome_audit",
        "name": "child-path promotion outcome audit",
        "description": "every promotion attempt has exactly one typed success, failure, or rejection outcome",
    },
    {
        "id": "event_theme_expressibility",
        "name": "eight event-theme expressibility",
        "description": "all eight evaluator-owned event themes have valid private fixtures and completion replay preserves completion identity",
    },
)


# --- runtime checks (consume the episode event list) --------------------------

_REFERENCE_KEYS: dict[str, str] = {
    "result_consumed": "completion_id",
    "artifact_committed": "lineage_completion_ids",
    "verification_requested": "lineage_completion_ids",
    "main_action": "consumes_completion_ids",
}


def _check_no_pre_delivery_leak(events: list[dict[str, Any]], context: dict[str, Any]) -> tuple[bool, str]:
    delivered: set[str] = set()
    for event in events:
        event_type = event.get("type")
        if event_type == "result_delivered":
            delivered.add(str(event.get("completion_id")))
            continue
        if event_type in _REFERENCE_KEYS:
            value = event.get(_REFERENCE_KEYS[event_type])
            ids = [value] if isinstance(value, str) else (value or [])
            for completion_id in ids:
                if completion_id is not None and str(completion_id) not in delivered:
                    return False, f"{event_type} referenced completion {completion_id} before gateway delivery"
    for field in ("evaluator_stale", "evaluator_stale_measurable", "evaluator_stale_reason"):
        stripped = strip_for_adapter({"type": "result_delivered", "completion_id": "x", field: True, "payload": {}})
        if field in stripped:
            return False, f"strip_for_adapter leaked hidden field {field!r}"
    return True, "no completion content leaked before gateway delivery"


def _check_gateway_delivery_enforced(events: list[dict[str, Any]], context: dict[str, Any]) -> tuple[bool, str]:
    completions: set[str] = set()
    delivered: set[str] = set()
    rejected: set[str] = set()
    consumed: set[str] = set()
    for event in events:
        event_type = event.get("type")
        if event_type == "child_completed":
            completions.add(str(event.get("completion_id")))
        elif event_type == "result_delivered":
            delivered.add(str(event.get("completion_id")))
        elif event_type == "result_rejected":
            rejected.add(str(event.get("completion_id")))
        elif event_type == "result_consumed":
            consumed.add(str(event.get("completion_id")))
    if consumed - delivered:
        return False, f"consumed without gateway delivery: {sorted(consumed - delivered)}"
    if completions - delivered - rejected:
        return False, (
            "completions never resolved by the gateway: "
            f"{sorted(completions - delivered - rejected)}"
        )
    return True, "every completion was delivered or contract-rejected by the gateway"


def _check_artifact_lineage_valid(events: list[dict[str, Any]], context: dict[str, Any]) -> tuple[bool, str]:
    consumed: set[str] = set()
    for event in events:
        if event.get("type") == "result_consumed":
            consumed.add(str(event.get("completion_id")))
    for event in events:
        if event.get("type") in ("artifact_committed", "verification_requested"):
            for completion_id in (event.get("lineage_completion_ids") or []):
                if str(completion_id) not in consumed:
                    return False, (
                        f"{event.get('type')} lineage references un-consumed completion {completion_id}"
                    )
    for event in events:
        if event.get("type") == "protocol_violation" and "lineage" in str(event.get("detail")):
            return False, f"runner recorded lineage violation: {event.get('detail')}"
    return True, "artifact and verification lineage only reference consumed completions"


def _check_verifier_post_episode(events: list[dict[str, Any]], context: dict[str, Any]) -> tuple[bool, str]:
    end_index = max(
        (index for index, event in enumerate(events) if event.get("type") == "episode_ended"),
        default=-1,
    )
    verifier_indices = [
        index for index, event in enumerate(events) if event.get("type") == "verifier_result"
    ]
    if not verifier_indices:
        return False, "no verifier_result recorded"
    if end_index == -1:
        return False, "no episode_end recorded"
    if any(index <= end_index for index in verifier_indices):
        return False, "verifier_result recorded before episode_end"
    return True, "the hidden verifier runs only after episode end"


def _check_promotion_outcome_audit(
    events: list[dict[str, Any]], context: dict[str, Any],
) -> tuple[bool, str]:
    attempts = {
        str(event.get("action_id"))
        for event in events
        if event.get("type") == "main_action"
        and event.get("kind") == "promote_child_path"
    }
    outcomes: dict[str, int] = {}
    for event in events:
        if event.get("type") != "child_path_promotion_result":
            continue
        action_id = str(event.get("action_id"))
        outcomes[action_id] = outcomes.get(action_id, 0) + 1
    missing_or_duplicate = {
        action_id: outcomes.get(action_id, 0)
        for action_id in attempts
        if outcomes.get(action_id, 0) != 1
    }
    orphaned = sorted(set(outcomes) - attempts)
    if missing_or_duplicate or orphaned:
        return False, (
            f"promotion outcome closure failed: attempts={missing_or_duplicate}, "
            f"orphaned={orphaned}"
        )

    # Exercise the concrete reference-adapter emitter with all three outcome
    # classes. This catches interface drift even when a conformance episode's
    # scripted model does not happen to request a file promotion.
    stream = io.StringIO()
    emitter = ProtocolEmitter(stdout=stream)
    fixtures = (
        {"action_id": "success", "completion_id": "p1", "child_id": "c1",
         "source_path": "/child/a", "destination_path": "/main/a",
         "success": True, "exit_code": 0, "failure_detail": ""},
        {"action_id": "failure", "completion_id": "p2", "child_id": "c2",
         "source_path": "/child/b", "destination_path": "/main/b",
         "success": False, "exit_code": 1, "failure_detail": "copy failed"},
        {"action_id": "rejected", "completion_id": "unknown", "child_id": None,
         "source_path": "/child/c", "destination_path": "/main/c",
         "success": False, "exit_code": None, "failure_detail": "not accepted"},
    )
    for fixture in fixtures:
        emitter.emit("child_path_promotion_result", **fixture)
    emitted = [json.loads(line) for line in stream.getvalue().splitlines()]
    try:
        for event in emitted:
            validate_adapter_event(event)
    except Exception as exc:
        return False, f"reference emitter produced an invalid promotion outcome: {exc}"
    return True, "every promotion attempt closes with one typed outcome; all outcome classes emit"


# --- kernel-invariant checks (no episode required) ----------------------------

def _check_child_workspace_isolation(events: list[dict[str, Any]], context: dict[str, Any]) -> tuple[bool, str]:
    def config(mode: str) -> Any:
        return SimpleNamespace(workspace_mode=mode, child_terminal_timeout_sec=180, keep_child_workspaces=False)

    disabled = build_workspace_runtime({"episode_id": "e", "workspace_run_id": "r"}, config("disabled"))
    if not isinstance(disabled, DisabledWorkspaceRuntime):
        return False, "disabled mode did not select DisabledWorkspaceRuntime"
    container = build_workspace_runtime(
        {"episode_id": "e", "workspace_run_id": "r", "container_name": "c"}, config("container_clone")
    )
    if not isinstance(container, DockerWorkspaceRuntime):
        return False, "container_clone mode did not select DockerWorkspaceRuntime"
    return True, "workspace runtime maps modes to isolated implementations"


def _check_stale_result_rejection(events: list[dict[str, Any]], context: dict[str, Any]) -> tuple[bool, str]:
    case_spec = {
        "superseded_result_kind": "superseded",
        "authoritative_result_kind": "authoritative",
        "scenarios": {"async": {"events": []}},
        "stale_predicate": {
            "type": "revision_mismatch",
            "authoritative_fields": ["head"],
            "superseded_fields": ["head"],
        },
    }
    controller = DeliveryController("async", case_spec)
    authoritative = {"completion_id": "auth", "result_kind": "authoritative", "payload": {"head": "new-revision"}}
    superseded = {"completion_id": "super", "result_kind": "superseded", "payload": {"head": "old-revision"}}
    controller.completions["auth"] = authoritative
    controller.completions["super"] = superseded
    controller.delivery_order.append("auth")
    stale, reason = controller._dynamic_stale_truth(superseded, {"stale": False})
    if stale is not True:
        return False, f"superseded revision not flagged stale: {stale!r} ({reason})"
    matching = {"completion_id": "match", "result_kind": "superseded", "payload": {"head": "new-revision"}}
    controller.completions["match"] = matching
    stale_match, _ = controller._dynamic_stale_truth(matching, {"stale": False})
    if stale_match is not False:
        return False, f"matching revision was incorrectly flagged stale: {stale_match!r}"
    return True, "the stale predicate rejects superseded revisions and accepts matching ones"


def _check_event_asset_scoping(events: list[dict[str, Any]], context: dict[str, Any]) -> tuple[bool, str]:
    event_assets = {"workstream_a": ["/a"], "workstream_b": ["/b"]}
    scoped = event_assets_for_workstreams(event_assets, ["workstream_a"])
    if scoped != {"/a"}:
        return False, f"event assets not scoped to the requesting workstream: {scoped}"
    return True, "event assets are scoped to the designated workstreams"


def _check_private_truth_projection(
    events: list[dict[str, Any]], context: dict[str, Any],
) -> tuple[bool, str]:
    participant_shapes = [
        event for event in events
        if event.get("type") in {"episode_started", "result_delivered", "result_rejected"}
        and event.get("visibility", "public") == "public"
    ]
    hits = [hit for event in participant_shapes for hit in find_private_fields(event)]
    if hits:
        return False, f"participant projection exposes private keys: {sorted(set(hits))!r}"
    return True, "participant start and gateway projections contain no private truth keys"


def _check_event_theme_expressibility(
    events: list[dict[str, Any]], context: dict[str, Any],
) -> tuple[bool, str]:
    errors = [*validate_event_taxonomy(), *validate_event_theme_fixtures()]
    if errors:
        return False, "; ".join(errors)
    case_spec = {
        "authoritative_result_kind": "authority",
        "superseded_result_kind": "provisional",
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [
                {"id": "original", "result": "authority"},
                {
                    "id": "replay", "stimulus_type": "completion_replay",
                    "replay_of_result": "authority", "trigger": "after_consumed",
                },
            ]},
        },
    }
    controller = DeliveryController("async", case_spec)
    controller.spawned = {"authority-child": {}, "other-child": {}}
    original = controller.on_complete({
        "type": "child_completed", "child_id": "authority-child",
        "completion_id": "completion-authority", "result_kind": "authority",
        "payload": {"revision": "v2"},
    })
    if len(original) != 1 or original[0].get("replayed"):
        return False, "original completion did not produce exactly one original delivery"
    replay = controller.on_consumed({"completion_id": "completion-authority"})
    if len(replay) != 1:
        return False, "completion replay was not emitted after first consumption"
    if replay[0].get("completion_id") != original[0].get("completion_id"):
        return False, "completion replay invented a new completion identity"
    if replay[0].get("payload_sha256") != original[0].get("payload_sha256"):
        return False, "completion replay changed the original payload"
    if controller.on_consumed({"completion_id": "completion-authority"}):
        return False, "the same replay schedule event fired more than once"
    projected = public_delivery(replay[0], workstream_id="authority_stream")
    if "replayed" in projected or "replay_of_completion_id" in projected:
        return False, "public replay delivery leaked evaluator replay truth"
    return True, "all eight event themes validate; replay preserves identity and private truth"


_CHECKS: dict[str, CheckFn] = {
    "no_pre_delivery_leak": _check_no_pre_delivery_leak,
    "child_workspace_isolation": _check_child_workspace_isolation,
    "gateway_delivery_enforced": _check_gateway_delivery_enforced,
    "stale_result_rejection": _check_stale_result_rejection,
    "artifact_lineage_valid": _check_artifact_lineage_valid,
    "event_asset_scoping": _check_event_asset_scoping,
    "private_truth_projection": _check_private_truth_projection,
    "verifier_post_episode": _check_verifier_post_episode,
    "promotion_outcome_audit": _check_promotion_outcome_audit,
    "event_theme_expressibility": _check_event_theme_expressibility,
}


def run_checks(events: list[dict[str, Any]], context: dict[str, Any] | None = None) -> list[CheckResult]:
    """Run every registered check against an episode's recorded events."""
    context = context or {}
    results: list[CheckResult] = []
    for spec in CONFORMANCE_TESTS:
        passed, detail = _CHECKS[spec["id"]](events, context)
        results.append(CheckResult(
            test_id=spec["id"],
            name=spec["name"],
            passed=passed,
            detail=detail,
        ))
    return results
