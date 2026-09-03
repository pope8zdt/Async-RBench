"""P1-15: abnormal Linear runs must be forbidden from the leaderboard.

The abnormal-Linear signature is zero main-side measurement: the Linear arm
shows the model exactly one atomic bundle, so ``main_tokens == 0`` means the
run recorded nothing about the model's behaviour (bundle never presented, or
never answered).  Two independent gates enforce this:

* runtime-time: the runner marks the run ``unscored``
  (``linear_no_main_measurement``) and leaderboard-ineligible
  (``linear_zero_main_tokens`` in ``leaderboard_ineligibility_reasons``);
* scoring-time: ``aggregate_reports`` hard-fails a certification that would
  certify an official record with the signature, checked from the raw record
  (not the runner-stamped flags) so a stale pre-gate score.json cannot pass.

Development (non-official) records with the signature are counted in the audit
but do not block a certification of official episodes.
"""

from __future__ import annotations

from async_rbench.evaluation.aggregate import aggregate_reports
from async_rbench.evaluation.runner import _linear_main_measurement_abnormal
from async_rbench.evaluation.weighting import SCORE_POLICY_VERSION


def _record(
    case: str, mode: str, x: float | None, *, official: bool = False,
    main_tokens: int = 100, repeat: int = 0,
):
    return {
        "episode_id": f"{case}-{mode}-{repeat}", "case_id": case,
        "instance_id": "seed-1", "repeat": repeat, "execution_mode": mode,
        "guidance": "incentive", "adapter_profile": "reference_scaffold_api",
        "runtime_mode": "api_only", "score_status": "scored" if x is not None else "unscored",
        "test_point_pass_rate": x, "scenario_constructed": x is not None,
        "denominator_digest": f"digest-{case}-{mode}", "total_tokens": 100,
        "main_tokens": main_tokens,
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


def test_abnormal_linear_signature() -> None:
    assert _linear_main_measurement_abnormal("linear", 0) is True
    assert _linear_main_measurement_abnormal("linear", None) is True
    assert _linear_main_measurement_abnormal("linear", 1200) is False
    assert _linear_main_measurement_abnormal("async", 0) is False
    assert _linear_main_measurement_abnormal("async", 2500) is False


def test_runtime_reason_and_status_override() -> None:
    # The runner-side effect (mark unscored + ineligible with the two reasons)
    # is applied in run_episode; pin the reason strings so aggregation filters
    # them consistently.
    from async_rbench.evaluation.runner import (
        LINEAR_ABNORMAL_STATUS_REASON, LINEAR_ZERO_MAIN_REASON,
    )
    assert LINEAR_ZERO_MAIN_REASON == "linear_zero_main_tokens"
    assert LINEAR_ABNORMAL_STATUS_REASON == "linear_no_main_measurement"


def test_official_linear_zero_main_tokens_is_a_hard_fail() -> None:
    bad = _record("case-a", "linear", 0.9, official=True, main_tokens=0)
    records = [
        bad,
        _record("case-a", "async", 0.9, official=True),
    ]
    audit = aggregate_reports(records, bootstrap_iterations=5)["audit"]
    assert audit["linear_abnormal_episode_count"] == 1
    assert audit["linear_abnormal_episode_ids"] == ["case-a-linear-0"]
    assert audit["hard_fail"] is True
    assert "official_linear_zero_main_tokens" in audit["hard_fail_reasons"]


def test_development_linear_zero_main_is_counted_but_not_a_hard_fail() -> None:
    # A development/calibration record with the signature (e.g. a pre-fix smoke
    # run still on disk) is reported but must not block certifying the official
    # episodes.
    records = [
        _record("case-a", "linear", 0.9, official=True),
        _record("case-a", "async", 0.9, official=True),
        _record("case-b", "linear", None, main_tokens=0),
        _record("case-b", "async", None, main_tokens=0),
    ]
    audit = aggregate_reports(records, bootstrap_iterations=5)["audit"]
    # Only the Linear record with the signature is abnormal; the async one is
    # a different classification and does not enter the linear-abnormal count.
    assert audit["linear_abnormal_episode_count"] == 1
    assert audit["linear_abnormal_episode_ids"] == ["case-b-linear-0"]
    assert audit["hard_fail"] is False
    assert "official_linear_zero_main_tokens" not in audit["hard_fail_reasons"]


def test_async_zero_main_is_not_linear_abnormal() -> None:
    # The abnormal-Linear signature is arm-specific (zero main tokens is the
    # designed Linear measurement failure); async zero-main is a different
    # classification and must not trip the linear gates.
    records = [
        _record("case-a", "async", 0.9, official=True, main_tokens=0),
    ]
    audit = aggregate_reports(records, bootstrap_iterations=5)["audit"]
    assert audit["linear_abnormal_episode_count"] == 0
    assert audit["hard_fail"] is False
