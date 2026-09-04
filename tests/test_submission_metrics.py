"""Task 8 (P1-18 / P1-19): submission-verdict metrics on score records and
aggregates.

Contract acceptance is the gateway verdict.  A ``result_delivered`` means the
gateway accepted and released the submission (``gateway_accepted``), whether or
not the main agent ever consumed it (``consumed_by_main`` facet); a public
``result_rejected`` is ``public_rejection``; a sealed submission that reached no
verdict before the episode closed is ``sealed_pending_verdict`` and never enters
a verdict denominator.  Budget exits, turn/no-submission ends, designed
terminals, cancels, case-contract and infrastructure failures never submitted,
so they never shape an acceptance/rejection rate.

Rates return ``None`` on a zero denominator.  Aggregated paper metrics are split
by execution mode (``paper_metrics_by_mode``) so no consumer can read a combined
value as an Async claim; the descriptive all-modes view rides under
``paper_metrics_all_modes_descriptive``.
"""

from __future__ import annotations

from async_rbench.evaluation.aggregate import aggregate_reports
from async_rbench.evaluation.scoring import score_trace
from async_rbench.evaluation.weighting import SCORE_POLICY_VERSION


def _case_spec() -> dict:
    return {
        "initial_wave": [
            {"workstream_id": "provisional"},
            {"workstream_id": "authority"},
        ],
        "delegation_workstreams": [
            {"id": "provisional", "result_kind": "provisional_result"},
            {"id": "authority", "result_kind": "authority_result"},
        ],
        "authoritative_result_kind": "authority_result",
        "superseded_result_kind": "provisional_result",
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": []},
        },
        "artifacts": [{"id": "final"}],
    }


def _contract() -> list[dict]:
    return [{
        "event_id": "evt.authority",
        "state_delta": {"affected_artifacts": ["final"], "unaffected_artifacts": []},
        "required_opportunities": ["authority_delivery"],
    }]


def _spawn(child_id: str, workstream: str, seq: int) -> dict:
    return {
        "type": "child_spawned", "seq": seq, "child_id": child_id,
        "parent_id": "main", "work_units": [workstream], "initial_wave": True,
    }


def _progress(child_id: str, tokens: int, seq: int) -> dict:
    return {
        "type": "agent_progress", "seq": seq, "role": f"child:{child_id}",
        "phase": "model_call_finished", "tokens": tokens,
    }


def _score(events: list[dict]) -> dict:
    events = [{**event, "elapsed_ms": float(event.get("elapsed_ms", 0.0))}
              for event in events]
    return score_trace(
        events, _case_spec(), "async",
        semantic_registry={"checks": []}, control_flow_checks=[],
        event_contracts=_contract(),
    )


def test_submission_verdict_rates_exclude_resource_and_cancel() -> None:
    events = [
        _spawn("c1", "ws-a", 1), _progress("c1", 50, 2),
        {
            "type": "child_completed", "seq": 3, "child_id": "c1",
            "completion_id": "p1", "payload": {"x": 1},
        },
        {
            "type": "result_rejected", "seq": 4, "child_id": "c1",
            "completion_id": "p1", "reason_codes": ["report_file_missing"],
            "result_kind": "provisional_result",
        },
        _spawn("c2", "ws-a", 5),
        {
            "type": "child_completed", "seq": 6, "child_id": "c2",
            "completion_id": "p2", "payload": {"x": 1},
        },
        {
            "type": "result_delivered", "seq": 7, "child_id": "c2",
            "completion_id": "p2", "payload": {"x": 1},
            "result_kind": "authority_result",
        },
        {"type": "result_consumed", "seq": 8, "completion_id": "p2", "action_id": "a"},
        _spawn("c3", "ws-b", 9),
        {
            "type": "child_resource_safety_abort", "seq": 10, "child_id": "c3",
            "reason": "emergency fuse",
        },
        _spawn("c4", "ws-c", 11),
        {
            "type": "child_cancelled", "seq": 12, "child_id": "c4",
            "initiated_by": "main", "reason": "redundant",
        },
    ]
    score = _score(events)

    # Task 8: exact one class per attempt; the emergency fuse is not a submission.
    assert score["child_terminal_counts"] == {
        "gateway_accepted": 1, "public_rejection": 1, "sealed_pending_verdict": 0,
        "resource_safety_abort": 1, "step_limit_reached": 0, "no_submission": 0,
        "timeout": 0, "crash": 0, "cancel": 1, "case_contract_failure": 0,
        "infrastructure_failure": 0, "in_flight": 0,
    }
    # Verdict denominator = gateway_accepted + public_rejection (2), so the
    # safety abort and the cancel do not dilute the rates.
    assert score["sealed_submission_count"] == 2
    assert score["gateway_verdict_count"] == 2
    assert score["gateway_accepted_count"] == 1
    assert score["public_rejected_count"] == 1
    assert score["sealed_pending_verdict_count"] == 0
    assert score["submission_acceptance_rate"] == 0.5
    assert score["submission_rejection_rate"] == 0.5
    # First attempt was rejected; the retry (only verdict-bearing retry) accepted.
    assert score["first_attempt_verdict_count"] == 1
    assert score["first_attempt_accepted_count"] == 0
    assert score["first_attempt_acceptance_rate"] == 0.0
    assert score["retry_verdict_count"] == 1
    assert score["retry_accepted_count"] == 1
    assert score["retry_acceptance_rate"] == 1.0
    assert score["avg_child_tokens_per_gateway_accepted"] == 0.0
    # Extra tokens from public rejections: the 50-token rejected attempt before
    # the accepted one in ws-a.
    assert score["extra_child_tokens_from_public_rejections"] == 50
    assert score["resource_safety_abort_rate_per_attempt"] == 1 / 4
    assert score["child_step_limit_rate_per_attempt"] == 0.0
    assert score["no_submission_rate_per_attempt"] == 0.0
    assert score["redelegation_attempt_count"] == 1
    assert score["invalid_redelegation_count"] == 0
    assert score["invalid_redelegation_rate"] == 0.0


def test_private_only_rejection_is_case_contract_failure_not_a_verdict() -> None:
    events = [
        _spawn("c1", "ws-a", 1),
        {
            "type": "child_completed", "seq": 2, "child_id": "c1",
            "completion_id": "p1", "payload": {"x": 1},
        },
        {
            "type": "result_rejected", "seq": 3, "child_id": "c1",
            "completion_id": "p1", "reason_codes": ["validator_command_failed"],
        },
    ]
    score = _score(events)
    assert score["child_terminal_counts"]["case_contract_failure"] == 1
    assert score["child_terminal_counts"]["public_rejection"] == 0
    assert score["child_terminal_counts"]["gateway_accepted"] == 0
    # A private-only rejection is a benchmark/case-contract failure, never a
    # rejection verdict: it must not make the rejection rate look full.
    assert score["gateway_verdict_count"] == 0
    assert score["sealed_submission_count"] == 0
    assert score["submission_rejection_rate"] is None
    assert score["submission_acceptance_rate"] is None
    row = score["child_terminal_classifications"][0]
    assert row["public_codes"] == []
    assert row["contract_part"] == "submission"


def test_designed_timeout_and_rejection_do_not_mix() -> None:
    events = [
        _spawn("c1", "ws-a", 1),
        {
            "type": "result_delivered", "seq": 2, "child_id": "c1",
            "completion_id": "terminal:ev-1", "terminal_outcome": "timeout",
            "payload": {},
        },
        _spawn("c2", "ws-b", 3),
        {
            "type": "child_completed", "seq": 4, "child_id": "c2",
            "completion_id": "p2", "payload": {"x": 1},
        },
        {
            "type": "result_rejected", "seq": 5, "child_id": "c2",
            "completion_id": "p2", "reason_codes": ["missing_required_evidence"],
        },
    ]
    score = _score(events)
    assert score["child_terminal_counts"]["timeout"] == 1
    assert score["child_terminal_counts"]["public_rejection"] == 1
    # The designed terminal never seals, so it is not in the verdict denominator.
    assert score["sealed_submission_count"] == 1
    assert score["gateway_verdict_count"] == 1
    assert score["submission_rejection_rate"] == 1.0
    assert score["submission_acceptance_rate"] == 0.0


def test_unconsumed_delivery_is_still_a_gateway_acceptance() -> None:
    events = [
        _spawn("c1", "ws-a", 1),
        {
            "type": "child_completed", "seq": 2, "child_id": "c1",
            "completion_id": "p1", "payload": {"x": 1},
        },
        # Delivered at the edge of the episode but never consumed: still accepted.
        {
            "type": "result_delivered", "seq": 3, "child_id": "c1",
            "completion_id": "p1", "payload": {"x": 1},
        },
    ]
    score = _score(events)
    assert score["child_terminal_counts"]["gateway_accepted"] == 1
    assert score["child_terminal_counts"]["sealed_pending_verdict"] == 0
    assert score["sealed_submission_count"] == 1
    assert score["gateway_verdict_count"] == 1
    assert score["submission_acceptance_rate"] == 1.0
    assert score["submission_rejection_rate"] == 0.0
    assert score["child_terminal_classifications"][0]["consumed_by_main"] is False


def test_invalid_redelegation_rate_from_runtime_markers() -> None:
    events = [
        _spawn("c1", "ws-a", 1), _spawn("c2", "ws-a", 2),
        {"type": "duplicate_evidence_retry_detected", "seq": 3,
         "workstream_id": "ws-a", "no_new_evidence_retries": 1},
    ]
    score = _score(events)
    assert score["redelegation_attempt_count"] == 1
    assert score["invalid_redelegation_count"] == 1
    assert score["invalid_redelegation_rate"] == 1.0


# ---------------------------------------------------------------------------
# Task 8 aggregation: gateway-verdict denominators and mode-separated metrics.
# ---------------------------------------------------------------------------

def _record(
    rows: list[dict], *, official: bool = False, mode: str = "async",
    invalid_redelegation_count: int = 0,
) -> dict:
    return {
        "episode_id": f"case-a-{mode}-0", "case_id": "case-a", "instance_id": "seed-1",
        "repeat": 0, "execution_mode": mode, "guidance": "incentive",
        "adapter_profile": "reference_scaffold_api", "runtime_mode": "api_only",
        "score_status": "scored", "test_point_pass_rate": 1.0,
        "scenario_constructed": True,
        "denominator_digest": "digest-a", "total_tokens": 100, "main_tokens": 100,
        "leaderboard_eligible": official, "conformance_passed": official,
        "capability_categories": ["stale_result_rejection"],
        "split": "test" if official else "calibration", "model": "deepseek-v4-pro",
        "scaffold_and_protocol_sha256": "evaluator-scaffold-v1",
        "semantic_task_score": 1.0, "dynamic_control_score": 1.0, "dt_score": 1.0,
        "score_policy_version": SCORE_POLICY_VERSION,
        "child_terminal_classifications": rows,
        "invalid_redelegation_count": invalid_redelegation_count,
    }


def _row(child: str, cls: str, attempt: int, sealed: bool, tokens: int,
         workstream: str = "ws-a") -> dict:
    return {
        "child_id": child, "workstream_id": workstream,
        "attempt_number": attempt, "retry": attempt >= 2,
        "terminal_class": cls, "sealed_submission": sealed, "tokens": tokens,
    }


def test_paper_metrics_aggregate_first_attempt_and_retry_acceptance() -> None:
    records = [
        # First attempt accepted.
        _record([
            _row("c1", "gateway_accepted", 1, True, 100),
        ]),
        # First attempt public-rejected (40 tokens), retry accepted (60 tokens).
        _record([
            _row("c2", "public_rejection", 1, True, 40),
            _row("c3", "gateway_accepted", 2, True, 60),
        ]),
        # A step-limit exit is not a submission.
        _record([
            _row("c4", "step_limit_reached", 1, False, 30, workstream="ws-b"),
        ]),
    ]
    paper = aggregate_reports(
        records, bootstrap_iterations=5,
    )["development_summary"]["paper_metrics_by_mode"]["async"]
    assert paper["sealed_submission_count"] == 3
    assert paper["gateway_verdict_count"] == 3
    assert paper["gateway_accepted_count"] == 2
    assert paper["public_rejected_count"] == 1
    assert paper["submission_acceptance_rate"] == 2 / 3
    assert paper["submission_rejection_rate"] == 1 / 3
    assert paper["first_attempt_verdict_count"] == 2
    assert paper["first_attempt_accepted_count"] == 1
    assert paper["first_attempt_acceptance_rate"] == 0.5
    assert paper["retry_verdict_count"] == 1
    assert paper["retry_accepted_count"] == 1
    assert paper["retry_acceptance_rate"] == 1.0
    assert paper["avg_child_tokens_per_gateway_accepted"] == (100 + 60) / 2
    assert paper["extra_child_tokens_from_public_rejections"] == 40
    assert paper["terminal_class_counts"]["step_limit_reached"] == 1
    # One redelegation (episode 2's retry), which was valid (added evidence and
    # was accepted), so the invalid-redelegation rate is zero, not null.
    assert paper["redelegation_attempt_count"] == 1
    assert paper["invalid_redelegation_count"] == 0
    assert paper["invalid_redelegation_rate"] == 0.0


def test_paper_metrics_rate_is_none_when_no_submissions() -> None:
    records = [
        _record([
            _row("c1", "in_flight", 1, False, 10),
        ]),
    ]
    paper = aggregate_reports(
        records, bootstrap_iterations=5,
    )["development_summary"]["paper_metrics_by_mode"]["async"]
    assert paper["sealed_submission_count"] == 0
    assert paper["gateway_verdict_count"] == 0
    assert paper["submission_acceptance_rate"] is None
    assert paper["submission_rejection_rate"] is None
    assert paper["first_attempt_acceptance_rate"] is None
    assert paper["avg_child_tokens_per_gateway_accepted"] is None


def test_paper_metrics_ride_each_leaderboard_entry() -> None:
    records = [
        _record([_row("c1", "gateway_accepted", 1, True, 100)], official=True),
    ]
    report = aggregate_reports(records, bootstrap_iterations=5)
    entry = report["leaderboard"][0]
    async_paper = entry["paper_metrics_by_mode"]["async"]
    assert async_paper["sealed_submission_count"] == 1
    assert async_paper["first_attempt_acceptance_rate"] == 1.0


def test_verdict_denominator_is_gateway_accepted_plus_public_rejected() -> None:
    events = [
        # Accepted and consumed by main.
        _spawn("c1", "ws-a", 1),
        {
            "type": "child_completed", "seq": 2, "child_id": "c1",
            "completion_id": "p1", "payload": {"x": 1},
        },
        {
            "type": "result_delivered", "seq": 3, "child_id": "c1",
            "completion_id": "p1", "payload": {"x": 1},
            "result_kind": "authority_result",
        },
        {"type": "result_consumed", "seq": 4, "completion_id": "p1", "action_id": "a"},
        # Delivered at the episode edge but never consumed: still accepted.
        _spawn("c2", "ws-b", 5),
        {
            "type": "child_completed", "seq": 6, "child_id": "c2",
            "completion_id": "p2", "payload": {"x": 1},
        },
        {
            "type": "result_delivered", "seq": 7, "child_id": "c2",
            "completion_id": "p2", "payload": {"x": 1},
            "result_kind": "authority_result",
        },
        # Public rejection is the only rejection that shapes the rejection rate.
        _spawn("c3", "ws-c", 8),
        {
            "type": "child_completed", "seq": 9, "child_id": "c3",
            "completion_id": "p3", "payload": {"x": 1},
        },
        {
            "type": "result_rejected", "seq": 10, "child_id": "c3",
            "completion_id": "p3", "reason_codes": ["report_file_missing"],
            "result_kind": "authority_result",
        },
    ]
    score = _score(events)
    assert score["gateway_verdict_count"] == 3
    assert score["gateway_accepted_count"] == 2
    assert score["public_rejected_count"] == 1
    assert score["sealed_pending_verdict_count"] == 0
    assert score["sealed_submission_count"] == 3
    assert score["submission_acceptance_rate"] == 2 / 3
    assert score["submission_rejection_rate"] == 1 / 3


def test_sealed_pending_verdict_is_excluded_from_verdict_denominator() -> None:
    events = [
        _spawn("c1", "ws-a", 1),
        {
            "type": "child_completed", "seq": 2, "child_id": "c1",
            "completion_id": "p1", "payload": {"x": 1},
        },
    ]
    score = _score(events)
    assert score["child_terminal_counts"]["sealed_pending_verdict"] == 1
    assert score["sealed_pending_verdict_count"] == 1
    assert score["sealed_submission_count"] == 1
    assert score["gateway_verdict_count"] == 0
    assert score["submission_acceptance_rate"] is None
    assert score["submission_rejection_rate"] is None


def test_first_attempt_and_retry_acceptance_use_verdict_bearing_only() -> None:
    events = [
        # First attempt: public rejection (verdict, not accepted).
        _spawn("c1", "ws-a", 1),
        {
            "type": "child_completed", "seq": 2, "child_id": "c1",
            "completion_id": "p1", "payload": {"x": 1},
        },
        {
            "type": "result_rejected", "seq": 3, "child_id": "c1",
            "completion_id": "p1", "reason_codes": ["report_file_missing"],
            "result_kind": "authority_result",
        },
        # Retry: accepted (delivered but unconsumed is still accepted).
        _spawn("c2", "ws-a", 4),
        {
            "type": "child_completed", "seq": 5, "child_id": "c2",
            "completion_id": "p2", "payload": {"x": 1},
        },
        {
            "type": "result_delivered", "seq": 6, "child_id": "c2",
            "completion_id": "p2", "payload": {"x": 1},
            "result_kind": "authority_result",
        },
        # Sealed with no verdict and a step-limit exit carry no verdict at all.
        _spawn("c3", "ws-b", 7),
        {
            "type": "child_completed", "seq": 8, "child_id": "c3",
            "completion_id": "p3", "payload": {"x": 1},
        },
        _spawn("c4", "ws-c", 9),
        {
            "type": "child_step_limit_reached", "seq": 10, "child_id": "c4",
            "reason": "limit",
        },
    ]
    score = _score(events)
    assert score["first_attempt_verdict_count"] == 1
    assert score["first_attempt_accepted_count"] == 0
    assert score["first_attempt_acceptance_rate"] == 0.0
    assert score["retry_verdict_count"] == 1
    assert score["retry_accepted_count"] == 1
    assert score["retry_acceptance_rate"] == 1.0
    assert score["sealed_pending_verdict_count"] == 1
    assert score["child_step_limit_rate_per_attempt"] == 1 / 4
    assert score["resource_safety_abort_rate_per_attempt"] == 0.0
    assert score["no_submission_rate_per_attempt"] == 0.0


def test_paper_metrics_are_split_by_execution_mode() -> None:
    records = [
        _record([_row("c1", "gateway_accepted", 1, True, 100)], mode="linear"),
        _record([_row("c1", "public_rejection", 1, True, 40)], mode="async"),
    ]
    summary = aggregate_reports(
        records, bootstrap_iterations=5,
    )["development_summary"]
    # No combined metric may be mislabeled Async.
    assert "paper_metrics" not in summary
    assert set(summary["paper_metrics_by_mode"]) == {"linear", "async"}
    assert summary["paper_metrics_by_mode"]["async"]["sealed_submission_count"] == 1
    assert summary["paper_metrics_by_mode"]["async"]["submission_rejection_rate"] == 1.0
    assert summary["paper_metrics_by_mode"]["async"]["submission_acceptance_rate"] == 0.0
    assert summary["paper_metrics_by_mode"]["linear"]["sealed_submission_count"] == 1
    assert summary["paper_metrics_by_mode"]["linear"]["submission_rejection_rate"] == 0.0
    # The combined view is still available under a name that cannot be read as
    # an Async claim.
    combined = summary["paper_metrics_all_modes_descriptive"]
    assert combined["sealed_submission_count"] == 2
