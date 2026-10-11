import pytest

from async_rbench.evaluation.aggregate import aggregate_reports
from async_rbench.evaluation.weighting import SCORE_POLICY_VERSION


def _record(policy, value):
    return {"episode_id": "e", "case_id": "c", "execution_mode": "async",
            "score_policy_version": policy, "score_status": "scored",
            "base_task_score": value, "async_drs": 0.4}


def test_mixed_scoring_semantics_cannot_share_headline():
    with pytest.raises(ValueError, match="mixed scoring"):
        aggregate_reports([_record(SCORE_POLICY_VERSION, 1), _record("legacy", 0.5)])


def test_legacy_fractional_score_is_not_reinterpreted_as_task_success():
    report = aggregate_reports([_record("dtbench-v9-causal-groups-2", 0.5)])
    assert report["development_summary"]["observed_async_base_task_score"] is None


def test_new_policy_rejects_nonbinary_run_success():
    with pytest.raises(ValueError, match="binary"):
        aggregate_reports([_record(SCORE_POLICY_VERSION, 0.5)])


def test_executable_policy_has_new_identity():
    assert SCORE_POLICY_VERSION != "dtbench-v9-causal-groups-2"
