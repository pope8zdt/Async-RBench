"""P1-17: mutually exclusive per-attempt terminal classification.

A workstream attempt is one child spawn (``child_spawned``); a redelegation is
a later spawn for the same workstream.  Every attempt terminates in exactly one
terminal class (the taxonomy below is exhaustive and mutually exclusive), and
the *attempt number* ("first attempt" vs "retry") is a facet dimension of each
row, never a duplicated set of counters.

Taxonomy::

    accepted              sealed submission consumed by the main agent
    public_rejection      gateway rejection carrying >=1 actionable public code
    private_rejection     gateway rejection whose public feedback was empty
                          (private validator reason only)
    sealed                sealed submission (``child_completed``) that reached no
                          verdict before the episode closed
    resource_exhausted    budget/turn exhaustion cut the child off (no submission)
    timeout               designed child-timeout terminal, delivered to main
    crash                 designed child-crash terminal, delivered to main
    cancel                explicit main-agent cancellation (``initiated_by=main``)
    infrastructure_failure benchmark/provider failure (workspace, backend, ...)
    in_flight             child still queued/running when the episode closed

Pipeline independence (P1-16): the classifier never reads ``execution_mode``
and only depends on child-level events, which Linear and Async record
identically --- both arms therefore classify the same way, and only arrival
timing/presentation differs.  Input events are the scorer's merged view (public
records with the matching kernel evaluator facts re-joined), so *private*
rejection codes and *public* feedback codes are both available.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .case_contract import (
    PUBLIC_RESULT_REJECTION_CODES,
    contract_part_for_codes,
)

ACCEPTED = "accepted"
PUBLIC_REJECTION = "public_rejection"
PRIVATE_REJECTION = "private_rejection"
SEALED = "sealed"
RESOURCE_EXHAUSTED = "resource_exhausted"
TIMEOUT = "timeout"
CRASH = "crash"
CANCEL = "cancel"
INFRASTRUCTURE_FAILURE = "infrastructure_failure"
IN_FLIGHT = "in_flight"

TERMINAL_CLASSES = (
    ACCEPTED,
    PUBLIC_REJECTION,
    PRIVATE_REJECTION,
    SEALED,
    RESOURCE_EXHAUSTED,
    TIMEOUT,
    CRASH,
    CANCEL,
    INFRASTRUCTURE_FAILURE,
    IN_FLIGHT,
)

#: Classes in which the child actually sealed a submission.  Only these enter
#: a submission-verdict denominator (P1-18): budget exits, designed terminals,
#: cancels, infrastructure failures and in-flight closes never submitted.
SUBMISSION_CLASSES = frozenset({ACCEPTED, PUBLIC_REJECTION, PRIVATE_REJECTION, SEALED})

#: Benchmark/resource endpoints rather than model submission verdicts; the
#: P1-18 rejection rate must exclude them.
NON_SUBMISSION_CLASSES = frozenset(set(TERMINAL_CLASSES) - SUBMISSION_CLASSES)


# Runtime lifecycle states are shared by the async wait surface, the Linear
# bundle barrier, cancellation guards, and status projections.  A state belongs
# here only when the child can no longer produce a submission in this attempt.
RUNTIME_TERMINAL_STATUSES = frozenset({
    "delivered",
    "contract_rejected",
    "rejected",
    "cancelled",
    "token_budget_exhausted",
    "turn_limit_exhausted",
    "no_submission",
    "timed_out",
    "infrastructure_failed",
})


def is_runtime_terminal(status: str) -> bool:
    return status in RUNTIME_TERMINAL_STATUSES


def _events_of(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [event for event in events if event.get("type") == event_type]


def _by_child(events: list[dict[str, Any]], child_id: str) -> list[dict[str, Any]]:
    return [event for event in events if str(event.get("child_id") or "") == child_id]


def classify_child_terminals(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Classify every spawned child attempt, one row per child.

    Deterministic by event order; each row carries exactly one ``terminal_class``
    plus the attempt facet (``attempt_number`` / ``retry``) so consumers never
    need second-guess the taxonomy.
    """
    spawns = _events_of(events, "child_spawned")
    completions = _events_of(events, "child_completed")
    cancelled = _events_of(events, "child_cancelled")
    exhausted = [
        event for event in events
        if event.get("type") in {
            "child_resource_exhausted",  # legacy artifact alias
            "child_token_budget_exhausted",
            "child_turn_limit_exhausted",
            "child_no_submission",
        }
    ]
    deliveries = _events_of(events, "result_delivered")
    rejections = _events_of(events, "result_rejected")
    consumed = _events_of(events, "result_consumed")
    infra_events = _events_of(events, "infrastructure_failure")

    # completion_id -> child_id (a designed-terminal synthetic completion has no
    # child_completed record, but its delivery/rejection carries child_id).
    completion_to_child = {
        str(event.get("completion_id")): str(event.get("child_id"))
        for event in completions
    }
    # Per-child token spend measured from child-side model calls.
    child_tokens: dict[str, int] = defaultdict(int)
    for event in _events_of(events, "agent_progress"):
        role = str(event.get("role") or "")
        if event.get("phase") != "model_call_finished" or not role.startswith("child:"):
            continue
        child_tokens[role.removeprefix("child:")] += int(event.get("tokens") or 0)

    # Attempt numbering: spawn order within the workstream (work_units[0]).
    attempt_by_child: dict[str, int] = {}
    attempt_counter: defaultdict[str, int] = defaultdict(int)
    for spawn in spawns:
        child_id = str(spawn.get("child_id") or "")
        work_units = [str(item) for item in (spawn.get("work_units") or [])]
        attempt_counter[str(work_units[0] if work_units else "")] += 1
        attempt_by_child[child_id] = attempt_counter[str(work_units[0] if work_units else "")]

    # Benchmark/provider severance: infrastructure failures plus any child
    # cancellation initiated by infrastructure (workspace/backend failures).
    infra_child_ids = {
        str(event.get("child_id"))
        for event in infra_events
        if event.get("child_id")
    }
    infra_child_ids |= {
        str(event.get("child_id"))
        for event in cancelled
        if str(event.get("initiated_by") or "") == "infrastructure"
    }

    rows: list[dict[str, Any]] = []
    for spawn in spawns:
        child_id = str(spawn.get("child_id") or "")
        work_units = [str(item) for item in (spawn.get("work_units") or [])]
        workstream_id = work_units[0] if work_units else None
        attempt_number = int(attempt_by_child.get(child_id, 1))

        completion_id: str | None = None
        reason_codes: list[str] = []
        public_codes: list[str] = []
        contract_part: str | None = None
        terminal_outcome: str | None = None
        detail: str | None = None

        if child_id in infra_child_ids:
            terminal_class = INFRASTRUCTURE_FAILURE
            detail = str(
                next(
                    (event for event in infra_events
                     if str(event.get("child_id") or "") == child_id),
                    {},
                ).get("detail", "")
            ) or None
        else:
            terminal_delivery = next(
                (event for event in _by_child(deliveries, child_id)
                 if event.get("terminal_outcome")),
                None,
            )
            if terminal_delivery is not None:
                terminal_outcome = str(terminal_delivery["terminal_outcome"])
                terminal_class = TIMEOUT if terminal_outcome == "timeout" else CRASH
                completion_id = str(terminal_delivery.get("completion_id") or "") or None
                detail = str(terminal_delivery.get("evaluator_terminal_reason") or "") or None
            elif any(
                str(event.get("initiated_by") or "") == "main"
                for event in _by_child(cancelled, child_id)
            ):
                terminal_class = CANCEL
                cancel_event = _by_child(cancelled, child_id)[0]
                detail = str(cancel_event.get("reason") or "") or None
            elif _by_child(exhausted, child_id):
                terminal_class = RESOURCE_EXHAUSTED
            else:
                rejection = _by_child(rejections, child_id)
                if rejection:
                    rejection = rejection[0]
                    completion_id = str(rejection.get("completion_id") or "") or None
                    reason_codes = [str(code) for code in (rejection.get("reason_codes") or [])]
                    public_codes = [
                        code for code in reason_codes
                        if code in PUBLIC_RESULT_REJECTION_CODES
                    ]
                    terminal_class = PUBLIC_REJECTION if public_codes else PRIVATE_REJECTION
                    contract_part = contract_part_for_codes(public_codes)
                else:
                    bound_consumed = next(
                        (event for event in consumed
                         if completion_to_child.get(str(event.get("completion_id") or ""))
                         == child_id),
                        None,
                    )
                    if bound_consumed is not None:
                        terminal_class = ACCEPTED
                        completion_id = str(bound_consumed.get("completion_id") or "") or None
                    elif _by_child(completions, child_id):
                        terminal_class = SEALED
                    else:
                        terminal_class = IN_FLIGHT
                        cancel_event = _by_child(cancelled, child_id)
                        detail = (
                            str(cancel_event[0].get("reason") or "")
                            if cancel_event else None
                        )

        rows.append({
            "child_id": child_id,
            "workstream_id": workstream_id,
            "attempt_number": attempt_number,
            "retry": attempt_number >= 2,
            "terminal_class": terminal_class,
            "completion_id": completion_id,
            "sealed_submission": terminal_class in SUBMISSION_CLASSES,
            "tokens": int(child_tokens.get(child_id, 0)),
            "reason_codes": reason_codes,
            "public_codes": public_codes,
            "contract_part": contract_part,
            "terminal_outcome": terminal_outcome,
            "detail": detail,
        })
    return rows
