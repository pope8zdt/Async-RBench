"""Task 8: mutually exclusive per-attempt terminal classification.

A workstream attempt is one child spawn (``child_spawned``); a retry is a later
spawn for the same workstream.  Every attempt terminates in exactly one terminal
class (the taxonomy below is exhaustive and mutually exclusive), and the
*attempt number* ("first attempt" vs "retry") is a facet dimension of each row,
never a duplicated set of counters.

Contract acceptance is the *gateway verdict*, not the main agent's later use: a
``result_delivered`` means the gateway accepted and released the submission, so
the attempt is ``gateway_accepted`` whether or not the main agent ever consumed
it.  ``result_consumed`` only records whether the main agent later used the
delivered result (``consumed_by_main`` facet) and never changes the terminal
class.  A child that sealed (``child_completed``) but reached no gateway
delivery/rejection before the episode closed is ``sealed_pending_verdict``: it
is a sealed submission but carries no gateway verdict, so it never enters a
verdict acceptance/rejection denominator.

Taxonomy::

    gateway_accepted       gateway delivered the sealed submission (accepted)
    public_rejection       gateway rejected with >=1 actionable public code
    sealed_pending_verdict sealed submission (``child_completed``) that reached
                           no gateway verdict before the episode closed
    step_limit_reached     child model-step horizon ended the attempt
    resource_safety_abort emergency provider-runaway fuse ended the attempt
    no_submission          child ended without sealing any submission
    timeout                designed child-timeout terminal, delivered to main
    crash                  designed child-crash terminal, delivered to main
    cancel                 explicit main-agent cancellation (``initiated_by=main``)
    case_contract_failure  benchmark/gateway contract failure (a ``case_contract``
                           infrastructure event, or a private-only rejection
                           reaching the scorer); never a model verdict
    infrastructure_failure benchmark/provider failure (workspace, backend, ...)
    in_flight              child still queued/running when the episode closed

Each row carries facets beyond ``terminal_class``:

* ``sealed_submission``: the attempt physically sealed a child submission.
* ``gateway_verdict``: the gateway reached accept/reject on the submission.
* ``consumed_by_main``: the main agent later consumed the delivered result.

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

GATEWAY_ACCEPTED = "gateway_accepted"
PUBLIC_REJECTION = "public_rejection"
SEALED_PENDING_VERDICT = "sealed_pending_verdict"
STEP_LIMIT_REACHED = "step_limit_reached"
RESOURCE_SAFETY_ABORT = "resource_safety_abort"
NO_SUBMISSION = "no_submission"
TIMEOUT = "timeout"
CRASH = "crash"
CANCEL = "cancel"
CASE_CONTRACT_FAILURE = "case_contract_failure"
INFRASTRUCTURE_FAILURE = "infrastructure_failure"
IN_FLIGHT = "in_flight"

TERMINAL_CLASSES = (
    GATEWAY_ACCEPTED,
    PUBLIC_REJECTION,
    SEALED_PENDING_VERDICT,
    STEP_LIMIT_REACHED,
    RESOURCE_SAFETY_ABORT,
    NO_SUBMISSION,
    TIMEOUT,
    CRASH,
    CANCEL,
    CASE_CONTRACT_FAILURE,
    INFRASTRUCTURE_FAILURE,
    IN_FLIGHT,
)

#: Classes in which the child actually sealed a submission.  These carry the
#: ``sealed_submission`` facet and feed the descriptive sealed-submission count.
SUBMISSION_CLASSES = frozenset({
    GATEWAY_ACCEPTED, PUBLIC_REJECTION, SEALED_PENDING_VERDICT,
})

#: Classes that reached a gateway accept/reject verdict on the sealed
#: submission.  Only these enter a verdict acceptance/rejection denominator
#: (Task 8): step/safety/no-submission ends, designed terminals, cancels,
#: case-contract and infrastructure failures and in-flight closes never did.
GATEWAY_VERDICT_CLASSES = frozenset({GATEWAY_ACCEPTED, PUBLIC_REJECTION})

#: Benchmark/resource endpoints rather than model submission verdicts.
NON_SUBMISSION_CLASSES = frozenset(set(TERMINAL_CLASSES) - SUBMISSION_CLASSES)


# Runtime lifecycle states are shared by the async wait surface, the Linear
# bundle barrier, cancellation guards, and status projections.  A state belongs
# here only when the child can no longer produce a submission in this attempt.
RUNTIME_TERMINAL_STATUSES = frozenset({
    "delivered",
    "contract_rejected",
    "rejected",
    "cancelled",
    "step_limit_reached",
    "resource_safety_abort",
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


#: Runtime events that end an attempt without sealing a submission.
_TERMINAL_EVENT_TO_CLASS = {
    "child_step_limit_reached": STEP_LIMIT_REACHED,
    "child_resource_safety_abort": RESOURCE_SAFETY_ABORT,
    "child_no_submission": NO_SUBMISSION,
}


def classify_child_terminals(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Classify every spawned child attempt, one row per child.

    Deterministic by event order; each row carries exactly one ``terminal_class``
    plus the attempt facet (``attempt_number`` / ``retry``) and the
    ``sealed_submission`` / ``gateway_verdict`` / ``consumed_by_main`` facets so
    consumers never need second-guess the taxonomy.

    Precedence per attempt (Task 8 Step 3):
    1. case-contract / infrastructure failure
    2. designed timeout/crash terminal
    3. explicit cancellation (``initiated_by=main``)
    4. step/safety/no-submission terminal event
    5. public ``result_rejected`` (a private-only rejection is a
       ``case_contract_failure``)
    6. ``result_delivered`` => ``gateway_accepted``
    7. ``child_completed`` => ``sealed_pending_verdict``
    8. otherwise ``in_flight``

    ``consumed_by_main`` is joined through completion id independently of the
    terminal class.
    """
    spawns = _events_of(events, "child_spawned")
    completions = _events_of(events, "child_completed")
    cancelled = _events_of(events, "child_cancelled")
    runtime_terminals = [
        event for event in events
        if event.get("type") in _TERMINAL_EVENT_TO_CLASS
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

    # Benchmark/provider severance, split into contract-level and infrastructure.
    case_contract_child_ids = {
        str(event.get("child_id"))
        for event in infra_events
        if event.get("child_id") and str(event.get("component") or "") == "case_contract"
    }
    infra_child_ids = {
        str(event.get("child_id"))
        for event in infra_events
        if event.get("child_id") and str(event.get("component") or "") != "case_contract"
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

        if child_id in case_contract_child_ids:
            terminal_class = CASE_CONTRACT_FAILURE
            case_contract_event = next(
                (event for event in infra_events
                 if str(event.get("child_id") or "") == child_id
                 and str(event.get("component") or "") == "case_contract"),
                {},
            )
            completion_id = str(case_contract_event.get("completion_id") or "") or None
            detail = str(case_contract_event.get("detail") or "") or None
        elif child_id in infra_child_ids:
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
            else:
                runtime_terminal_events = _by_child(runtime_terminals, child_id)
                if runtime_terminal_events:
                    terminal_class = _TERMINAL_EVENT_TO_CLASS[
                        str(runtime_terminal_events[0].get("type"))
                    ]
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
                        contract_part = contract_part_for_codes(public_codes)
                        if public_codes:
                            terminal_class = PUBLIC_REJECTION
                        else:
                            # A private-only rejection reaching the scorer is a
                            # gateway/case-contract failure, never a model verdict.
                            terminal_class = CASE_CONTRACT_FAILURE
                    else:
                        accepted_delivery = next(
                            (event for event in _by_child(deliveries, child_id)
                             if not event.get("terminal_outcome")),
                            None,
                        )
                        if accepted_delivery is not None:
                            terminal_class = GATEWAY_ACCEPTED
                            completion_id = str(
                                accepted_delivery.get("completion_id") or ""
                            ) or None
                        elif _by_child(completions, child_id):
                            terminal_class = SEALED_PENDING_VERDICT
                            completion_id = str(
                                _by_child(completions, child_id)[0].get("completion_id") or ""
                            ) or None
                        else:
                            terminal_class = IN_FLIGHT
                            cancel_event = _by_child(cancelled, child_id)
                            detail = (
                                str(cancel_event[0].get("reason") or "")
                                if cancel_event else None
                            )

        consumed_by_main = any(
            completion_to_child.get(str(event.get("completion_id") or "")) == child_id
            for event in consumed
        )

        rows.append({
            "child_id": child_id,
            "workstream_id": workstream_id,
            "attempt_number": attempt_number,
            "retry": attempt_number >= 2,
            "terminal_class": terminal_class,
            "completion_id": completion_id,
            "sealed_submission": terminal_class in SUBMISSION_CLASSES,
            "gateway_verdict": terminal_class in GATEWAY_VERDICT_CLASSES,
            "consumed_by_main": consumed_by_main,
            "tokens": int(child_tokens.get(child_id, 0)),
            "reason_codes": reason_codes,
            "public_codes": public_codes,
            "contract_part": contract_part,
            "terminal_outcome": terminal_outcome,
            "detail": detail,
        })
    return rows
