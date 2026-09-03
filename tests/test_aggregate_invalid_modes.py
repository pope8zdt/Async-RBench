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
        "split": "test" if official else "calibration",
        "model": "deepseek-v4-pro",
        "scaffold_and_protocol_sha256": "evaluator-scaffold-v1",
        "semantic_task_score": x,
        "dynamic_control_score": x if mode == "async" else None,
        "dt_score": x if mode == "async" else None,
        "score_policy_version": SCORE_POLICY_VERSION,
    }


def test_clean_valid_mode_records_do_not_hard_fail() -> None:
    records = [
        _record("case-a", "linear", 1.0, official=True),
        _record("case-a", "async", 0.5, official=True),
        _record("case-b", "linear", 0.75),
        _record("case-b", "async", 0.25),
    ]
    audit = aggregate_reports(records, bootstrap_iterations=5)["audit"]
    assert audit["hard_fail"] is False
    assert "invalid_execution_modes" not in audit["hard_fail_reasons"]
    assert audit["invalid_execution_modes"] == []


def test_invalid_execution_mode_is_a_hard_fail() -> None:
    # A manifest rebuilt for an official track must not certify a leaderboard
    # carrying a record whose execution_mode is outside the contract
    # ("linear", "async").
    records = [_record("case-a", "something_else", 0.5, official=True)]
    audit = aggregate_reports(records, bootstrap_iterations=5)["audit"]
    assert audit["invalid_execution_modes"] == ["something_else"]
    assert audit["hard_fail"] is True
    assert audit["hard_fail_reasons"] == ["invalid_execution_modes"]


def test_invalid_execution_mode_hard_fails_even_when_record_is_not_official() -> None:
    # The gate scans every record in the manifest, not only leaderboard-eligible
    # ones, so an out-of-contract mode on a development/calibration episode is
    # still a hard fail.
    records = [
        _record("case-a", "async", 1.0, official=True),
        _record("case-a", "async", 1.0, repeat=1),
        _record("case-b", "wildcard", 0.5),
    ]
    audit = aggregate_reports(records, bootstrap_iterations=5)["audit"]
    assert audit["invalid_execution_modes"] == ["wildcard"]
    assert audit["hard_fail"] is True
    assert "invalid_execution_modes" in audit["hard_fail_reasons"]


def test_missing_execution_mode_key_is_a_hard_fail() -> None:
    # A record with no "execution_mode" key at all maps to "" via _mode, which
    # is not in the contract's modes: pin this branch so a future "helpful"
    # change that filters "" out cannot silently loosen the gate.
    record = _record("case-a", "async", 1.0, official=True)
    del record["execution_mode"]
    audit = aggregate_reports([record], bootstrap_iterations=5)["audit"]
    assert audit["invalid_execution_modes"] == [""]
    assert audit["hard_fail"] is True
    assert audit["hard_fail_reasons"] == ["invalid_execution_modes"]
