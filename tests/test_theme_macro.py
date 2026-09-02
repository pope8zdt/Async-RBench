from __future__ import annotations

import pytest

from async_rbench.evaluation.aggregate import _theme, aggregate_reports
from async_rbench.evaluation.weighting import SCORE_POLICY_VERSION


def _rec(
    case: str, mode: str, x: float | None, *, instance: str = "i1",
    repeat: int = 0, theme: str | None = None,
    base_task: float | None = None, drs: float | None = None,
):
    """One scored episode in the compact shape the aggregator consumes."""
    bts = x if base_task is None else base_task
    d = (x if drs is None else drs) if mode == "async" else None
    return {
        "episode_id": f"{case}-{mode}-{repeat}", "case_id": case,
        "instance_id": instance, "repeat": repeat, "execution_mode": mode,
        "guidance": "incentive", "adapter_profile": "reference_scaffold_api",
        "runtime_mode": "api_only", "score_status": "scored" if x is not None else "unscored",
        "test_point_pass_rate": x, "semantic_task_score": x,
        "dynamic_control_score": x if mode == "async" else None,
        "dt_score": x if mode == "async" else None,
        "base_task_score": bts,
        "async_drs": d,
        "scenario_constructed": x is not None, "scenario_exposure_complete": x is not None,
        "total_tokens": 100, "leaderboard_eligible": False, "conformance_passed": False,
        "capability_categories": ["stale_result_rejection"],
        "split": "test", "model": "deepseek-v4-pro",
        "score_policy_version": SCORE_POLICY_VERSION,
        **(  # noqa: E203
            {"event_theme": theme} if theme is not None else {}
        ),
    }


def test_headline_is_theme_equal_not_case_equal() -> None:
    # Theme "alpha" spans three cases with one low-scoring instance each; theme
    # "beta" is a single high-scoring case.  Case-equal would bury beta under
    # alpha's three cases; theme-equal gives each theme one vote.
    records = []
    for case in ("c1", "c2", "c3"):
        records.append(_rec(case, "linear", 0.0, theme="alpha"))
        records.append(_rec(case, "async", 0.0, theme="alpha"))
    records.append(_rec("c4", "linear", 1.0, theme="beta"))
    for instance in ("i1", "i2", "i3"):
        records.append(_rec("c4", "async", 1.0, instance=instance, theme="beta"))
    summary = aggregate_reports(records, bootstrap_iterations=5)["development_summary"]
    # theme-equal: mean(alpha=0.0, beta=1.0) == 0.5 (case-equal would be 0.25).
    assert summary["observed_dynamic_control_score"] == 0.5
    assert summary["dynamic_control_score"] == 0.5  # complete (each case has linear+async)
    assert summary["theme_dynamic_control_scores"] == {"alpha": 0.0, "beta": 1.0}


def test_underpowered_theme_is_dropped_from_headline_but_reported() -> None:
    records = [
        # theme "alpha": 3 instances, all pass -> reliable mean.
        _rec("c1", "async", 1.0, instance="i1", theme="alpha"),
        _rec("c1", "async", 1.0, instance="i2", theme="alpha"),
        _rec("c1", "async", 1.0, instance="i3", theme="alpha"),
        # theme "beta": a single scored instance -> single-point variance.
        _rec("c2", "async", 0.0, instance="i1", theme="beta"),
    ]
    summary = aggregate_reports(records, bootstrap_iterations=5)["development_summary"]
    assert summary["theme_dynamic_control_scores"] == {"alpha": 1.0}
    assert summary["dropped_dynamic_themes"] == {"beta": 0.0}
    assert summary["observed_dynamic_control_score"] == 1.0
    assert summary["dynamic_theme_coverage"] == 0.5
    assert summary["theme_instance_count_minimum"] == 3
    assert summary["dynamic_theme_instance_counts"] == {"alpha": 3, "beta": 1}


def test_single_theme_dataset_is_not_dropped_to_empty() -> None:
    # A dataset with no theme breakdown collapses to one "unassigned" theme.  It
    # must stand as the whole headline rather than being narrowed to None.
    records = [
        _rec("small", "linear", 1.0),
        _rec("small", "async", 1.0),
        _rec("large", "linear", 1.0),
        _rec("large", "async", 0.0),
    ]
    summary = aggregate_reports(records, bootstrap_iterations=5)["development_summary"]
    assert summary["observed_dynamic_control_score"] == 0.5
    assert summary["theme_dynamic_control_scores"] == {"unassigned": 0.5}
    assert summary["dropped_dynamic_themes"] == {}


def test_theme_resolution_prefers_stamp_then_map_then_unassigned() -> None:
    theme_map = {"case-only": "by-map", "stamped": "by-map"}
    assert _theme({"case_id": "x", "event_theme": "stamped"}, theme_map) == "stamped"
    assert _theme({"case_id": "stamped", "event_theme": "stamped"}, theme_map) == "stamped"
    assert _theme({"case_id": "case-only"}, theme_map) == "by-map"
    assert _theme({"case_id": "unknown"}) == "unassigned"


def test_theme_by_case_map_drives_headline_split() -> None:
    theme_map = {"c1": "alpha", "c2": "beta"}
    records = [
        _rec("c1", "async", 1.0, instance="i1"), _rec("c1", "async", 1.0, instance="i2"),
        _rec("c1", "async", 1.0, instance="i3"),
        _rec("c2", "async", 0.0, instance="i1"),
    ]
    report = aggregate_reports(records, theme_by_case=theme_map, bootstrap_iterations=5)
    summary = report["development_summary"]
    assert summary["dropped_dynamic_themes"] == {"beta": 0.0}
    assert summary["theme_dynamic_control_scores"] == {"alpha": 1.0}
    assert report["audit"]["resolved_themes"] == 2
    assert report["audit"]["headline_macro_unit"] == "event_theme"


# ---------------------------------------------------------------------------
# Task 11: Linear BTS / Async BTS / Async DRS are the only new headline metrics.
# ---------------------------------------------------------------------------


def test_headline_exposes_bts_and_drs_as_separate_primary_metrics() -> None:
    records = [
        _rec("c1", "linear", 0.8, base_task=0.8),
        _rec("c1", "async", 0.5, base_task=0.6, drs=0.4),
        _rec("c2", "linear", 1.0, base_task=1.0),
        _rec("c2", "async", 0.3, base_task=0.7, drs=0.2),
    ]
    summary = aggregate_reports(records, bootstrap_iterations=5)["development_summary"]
    # Linear BTS is the linear-mode base_task macro; Async BTS is the async-mode
    # macro; Async DRS is its own independent macro.  Each of the three is a
    # first-class headline field.
    assert summary["linear_base_task_score"] == pytest.approx(0.9)
    assert summary["observed_async_base_task_score"] == pytest.approx(0.65)
    assert summary["async_base_task_score"] == pytest.approx(0.65)
    assert summary["observed_async_dynamic_replanning_score"] == pytest.approx(0.3)
    assert summary["async_dynamic_replanning_score"] == pytest.approx(0.3)
    # The headline must not designate an old blended metric as primary.
    assert summary["primary_metric"] == [
        "linear_base_task_score", "async_base_task_score", "async_dynamic_replanning_score",
    ]
    for legacy in ("dynamic_control_score", "dt_score", "dynamic_success_rate",
                   "critical_dynamic_success_rate"):
        assert legacy not in summary["primary_metric"]
    # Paired BTS delta is the within-pair linear-minus-async effect.
    assert summary["paired_bts_delta"] == pytest.approx(0.25)


def test_bts_and_drs_are_independent_headlines() -> None:
    # BTS can be high while DRS is low (correct final state but poor replanning),
    # and vice versa.  They must not be derived from the same blended measure.
    records = [
        _rec("c1", "linear", 0.0, base_task=0.9),
        _rec("c1", "async", 1.0, base_task=0.9, drs=0.1),
    ]
    summary = aggregate_reports(records, bootstrap_iterations=5)["development_summary"]
    assert summary["async_base_task_score"] == 0.9
    assert summary["async_dynamic_replanning_score"] == 0.1
    # The legacy blended async measure is still surfaced as legacy, never as BTS.
    assert summary["async_test_point_pass_rate"] == 1.0
    assert summary["theme_async_drs_scores"]["unassigned"] == 0.1
