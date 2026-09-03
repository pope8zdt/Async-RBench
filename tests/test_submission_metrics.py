"""P1-18 / P1-19: submission-verdict metrics on score records and aggregates.

P1-17 classifies every child attempt into exactly one terminal class; P1-18
redefines the rejection rate to run over *sealed submissions only* (budget
exits, designed terminals, cancels, infrastructure failures and in-flight
closes never submitted, so they must not shape the rejection rate); P1-19
aggregates the paper metrics (first-attempt vs retry acceptance, tokens per
accepted submission, extra tokens from rejections, invalid-redelegation rate).
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


def test_submission_rejection_rate_excludes_resource_and_cancel() -> None:
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
            "type": "child_resource_exhausted", "seq": 10, "child_id": "c3",
            "pool": "episode", "remaining": 0,
        },
        _spawn("c4", "ws-c", 11),
        {
            "type": "child_cancelled", "seq": 12, "child_id": "c4",
            "initiated_by": "main", "reason": "redundant",
        },
    ]
    score = _score(events)

    # P1-17: exact one class per attempt.
    counts = score["child_terminal_counts"]
    assert counts == {
        "accepted": 1, "public_rejection": 1, "private_rejection": 0,
        "sealed": 0, "resource_exhausted": 1, "timeout": 0, "crash": 0,
        "cancel": 1, "infrastructure_failure": 0, "in_flight": 0,
    }
    # P1-18: the denominator is sealed submissions only (2), so the budget exit
    # and the cancel do not dilute the rejection rate.
    assert score["sealed_submission_count"] == 2
    assert score["rejected_submission_count"] == 1
    assert score["submission_rejection_rate"] == 0.5
    # P1-19: attempt facet (first vs retry) on one dimension.
    assert score["first_attempt_submission_count"] == 1
    assert score["first_attempt_accepted_count"] == 0
    assert score["retry_submission_count"] == 1
    assert score["retry_accepted_count"] == 1
    # Extra tokens from rejections: the sealed-50-token attempt before the
    # accepted one.
    assert score["extra_rejection_tokens"] == 50
    assert score["redelegation_attempt_count"] == 1


def test_private_rejection_is_counted_separately_and_rates_full() -> None:
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
    assert score["child_terminal_counts"]["private_rejection"] == 1
    assert score["child_terminal_counts"]["public_rejection"] == 0
    assert score["submission_rejection_rate"] == 1.0
    row = score["child_terminal_classifications"][0]
    assert row["public_codes"] == []
    assert row["contract_part"] == "submission"


def test_designed_timeout_and_private_rejection_do_not_mix() -> None:
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
    # The designed terminal never seals, so it is not in the denominator.
    assert score["sealed_submission_count"] == 1
    assert score["submission_rejection_rate"] == 1.0


def test_sealed_unresolved_is_a_submission_but_not_a_rejection() -> None:
    events = [
        _spawn("c1", "ws-a", 1),
        {
            "type": "child_completed", "seq": 2, "child_id": "c1",
            "completion_id": "p1", "payload": {"x": 1},
        },
        # Delivered at the edge of the episode but never acknowledged.
        {
            "type": "result_delivered", "seq": 3, "child_id": "c1",
            "completion_id": "p1", "payload": {"x": 1},
        },
    ]
    score = _score(events)
    assert score["child_terminal_counts"]["sealed"] == 1
    assert score["sealed_submission_count"] == 1
    assert score["submission_rejection_rate"] == 0.0


def test_invalid_redelegation_rate_from_runtime_markers() -> None:
    events = [
        _spawn("c1", "ws-a", 1), _spawn("c2", "ws-a", 2),
        {"type": "no_information_retry_detected", "seq": 3,
         "workstream_id": "ws-a", "no_new_evidence_retries": 1},
    ]
    score = _score(events)
    assert score["redelegation_attempt_count"] == 1
    assert score["invalid_redelegation_count"] == 1
    assert score["invalid_redelegation_rate"] == 1.0


# ---------------------------------------------------------------------------
# P1-19 aggregation
# ---------------------------------------------------------------------------

def _record(
    rows: list[dict], *, official: bool = False, mode: str = "async",
    extra_rejection_tokens: int = 0,
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
        "extra_rejection_tokens": extra_rejection_tokens,
        "invalid_redelegation_count": 0,
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
            _row("c1", "accepted", 1, True, 100),
        ]),
        # First attempt rejected (40 tokens), retry accepted (60 tokens).
        _record([
            _row("c2", "public_rejection", 1, True, 40),
            _row("c3", "accepted", 2, True, 60),
        ], extra_rejection_tokens=40),
        # A budget exit is not a submission.
        _record([
            _row("c4", "resource_exhausted", 1, False, 30, workstream="ws-b"),
        ]),
    ]
    paper = aggregate_reports(records, bootstrap_iterations=5)["development_summary"]["paper_metrics"]
    assert paper["sealed_submission_count"] == 3
    assert paper["submission_acceptance_rate"] == 2 / 3
    assert paper["submission_rejection_rate"] == 1 / 3
    assert paper["first_attempt_submission_count"] == 2
    assert paper["first_attempt_accepted_count"] == 1
    assert paper["first_attempt_acceptance_rate"] == 0.5
    assert paper["retry_submission_count"] == 1
    assert paper["retry_accepted_count"] == 1
    assert paper["retry_acceptance_rate"] == 1.0
    assert paper["avg_tokens_per_accepted"] == (100 + 60) / 2
    assert paper["extra_tokens_from_rejections"] == 40
    assert paper["terminal_class_counts"]["resource_exhausted"] == 1
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
    paper = aggregate_reports(records, bootstrap_iterations=5)["development_summary"]["paper_metrics"]
    assert paper["sealed_submission_count"] == 0
    assert paper["submission_acceptance_rate"] is None
    assert paper["first_attempt_acceptance_rate"] is None
    assert paper["avg_tokens_per_accepted"] is None


def test_paper_metrics_ride_each_leaderboard_entry() -> None:
    records = [
        _record([_row("c1", "accepted", 1, True, 100)], official=True),
    ]
    report = aggregate_reports(records, bootstrap_iterations=5)
    entry = report["leaderboard"][0]
    assert entry["paper_metrics"]["sealed_submission_count"] == 1
    assert entry["paper_metrics"]["first_attempt_acceptance_rate"] == 1.0
