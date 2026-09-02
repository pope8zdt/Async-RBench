from __future__ import annotations

from async_rbench.evaluation.aggregate import aggregate_reports
from async_rbench.evaluation.weighting import SCORE_POLICY_VERSION


def _record(
    case: str, mode: str, x: float | None, *, official: bool = False,
    repeat: int = 0, instance: str = "seed-1",
):
    return {
        "episode_id": f"{case}-{mode}-{repeat}", "case_id": case,
        "instance_id": instance, "repeat": repeat, "execution_mode": mode,
        "guidance": "incentive", "adapter_profile": "reference_scaffold_api",
        "runtime_mode": "api_only", "score_status": "scored" if x is not None else "unscored",
        "test_point_pass_rate": x, "scenario_constructed": x is not None,
        "denominator_digest": f"digest-{case}-{mode}", "total_tokens": 100,
        "leaderboard_eligible": official, "conformance_passed": official,
        "capability_categories": ["stale_result_rejection"],
        # Formal experiment factors now required on every record: the dataset
        # split and the single model. Official (Track-A) records must sit in the
        # held-out test split; calibration/development records carry a split too.
        "split": "test" if official else "calibration",
        "model": "deepseek-v4-pro",
        "scaffold_and_protocol_sha256": "evaluator-scaffold-v1",
        "semantic_task_score": x,
        "dynamic_control_score": x if mode == "async" else None,
        "dt_score": x if mode == "async" else None,
        "score_policy_version": SCORE_POLICY_VERSION,
    }


def test_unscored_records_are_counted_but_not_averaged() -> None:
    report = aggregate_reports([
        _record("case-a", "async", 0.75), _record("case-a", "async", None, repeat=1),
    ], bootstrap_iterations=5)
    row = report["rows"][0]
    assert (row["n"], row["scored_n"], row["unscored_n"]) == (2, 1, 1)
    assert row["test_point_pass_rate"] == 0.75
    assert row["scenario_construction_rate"] == 0.5


def test_official_and_development_summaries_are_separate() -> None:
    records = [
        _record("case-a", "linear", 1.0, official=True),
        _record("case-a", "async", 0.5, official=True),
        _record("case-b", "linear", 1.0),
        _record("case-b", "async", 0.0),
    ]
    report = aggregate_reports(records, bootstrap_iterations=5)
    assert report["leaderboard"][0]["async_test_point_pass_rate"] == 0.5
    assert report["leaderboard"][0]["paired_async_replanning_drop"] == 0.5
    assert report["development_summary"]["observed_async_test_point_pass_rate"] == 0.25
    assert report["audit"]["leaderboard_eligible_episode_count"] == 2


def test_case_macro_prevents_large_case_from_dominating() -> None:
    records = [
        _record("small", "linear", 1.0), _record("small", "async", 1.0),
        _record("large", "linear", 1.0),
        *[_record("large", "async", 0.0, repeat=i) for i in range(5)],
    ]
    summary = aggregate_reports(records, bootstrap_iterations=5)["development_summary"]
    assert summary["observed_async_test_point_pass_rate"] == 0.5
    assert summary["capability_async_test_point_pass_rates"]["stale_result_rejection"] == 0.5


def test_family_macro_balances_instances_before_balancing_families() -> None:
    records = [
        _record("family-a", "async", 1.0, instance="instance-1"),
        *[
            _record("family-a", "async", 0.0, instance="instance-2", repeat=index)
            for index in range(5)
        ],
        _record("family-b", "async", 1.0),
    ]
    summary = aggregate_reports(records, bootstrap_iterations=5)["development_summary"]
    assert summary["observed_case_async_test_point_pass_rates"]["family-a"] == 0.5
    assert summary["observed_async_test_point_pass_rate"] == 0.75


def test_manifest_missing_ids_are_reported() -> None:
    records = [_record("case-a", "linear", 1.0)]
    planned = [
        {"episode_id": "case-a-linear-0"}, {"episode_id": "case-a-async-0"},
    ]
    audit = aggregate_reports(records, planned_episodes=planned, bootstrap_iterations=5)["audit"]
    assert audit["missing_episode_ids"] == ["case-a-async-0"]
    assert audit["manifest_completion_rate"] == 0.5


def test_missing_episode_is_a_hard_fail() -> None:
    records = [_record("case-a", "async", 1.0)]
    planned = [{"episode_id": "case-a-async-0"}, {"episode_id": "case-a-async-1"}]
    audit = aggregate_reports(records, planned_episodes=planned, bootstrap_iterations=5)["audit"]
    assert audit["hard_fail"] is True
    assert "missing_episodes" in audit["hard_fail_reasons"]


def test_denominator_digest_drift_is_a_hard_fail() -> None:
    # Two episodes of the same case instance scored against different digests.
    first = _record("case-a", "async", 1.0, official=True)
    second = _record("case-a", "async", 1.0, official=True, repeat=1)
    second["denominator_digest"] = "digest-tampered"
    audit = aggregate_reports([first, second], bootstrap_iterations=5)["audit"]
    assert audit["denominator_comparability_ok"] is False
    assert audit["hard_fail"] is True
    assert "official_denominator_digest_drift" in audit["hard_fail_reasons"]


def test_clean_run_does_not_hard_fail() -> None:
    records = [_record("case-a", "async", 1.0, official=True)]
    audit = aggregate_reports(records, bootstrap_iterations=5)["audit"]
    assert audit["hard_fail"] is False
    assert audit["hard_fail_reasons"] == []


def test_opportunity_counts_are_reported() -> None:
    rec = _record("case-a", "async", 0.75)
    rec["base_task_score"] = 0.8
    rec["async_drs"] = 0.5
    rec["event_opportunity_counts"] = {
        "declared_events": 2, "provisional_established": 1,
        "result_available": 2, "adapter_queued": 2, "result_presented": 2,
        "response_window_closed": 2, "participant_provisional_failure": 0,
        "infrastructure_delivery_failure": 0,
    }
    report = aggregate_reports([rec], bootstrap_iterations=5)
    dev_opp = report["development_summary"]["event_opportunity"]
    assert dev_opp["declared_events"] == 2
    assert dev_opp["provisional_established"] == 1
    assert dev_opp["result_presented"] == 2
    assert dev_opp["response_window_closed"] == 2
    assert report["audit"]["opportunity_counts"]["adapter_queued"] == 2
    assert report["audit"]["opportunity_counts"]["declared_events"] == 2


def test_opportunity_counts_account_for_participant_and_infrastructure_failures() -> None:
    # A participant provisional failure and an infrastructure delivery failure
    # are counted separately so neither is silently absorbed into the mean.
    rec = _record("case-a", "linear", 1.0)
    rec["event_opportunity_counts"] = {
        "declared_events": 1, "provisional_established": 0,
        "result_available": 1, "adapter_queued": 1, "result_presented": 1,
        "response_window_closed": 1, "participant_provisional_failure": 1,
        "infrastructure_delivery_failure": 1,
    }
    summary = aggregate_reports([rec], bootstrap_iterations=5)["development_summary"]
    opp = summary["event_opportunity"]
    assert opp["participant_provisional_failure"] == 1
    assert opp["infrastructure_delivery_failure"] == 1
