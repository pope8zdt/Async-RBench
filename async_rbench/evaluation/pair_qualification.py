from __future__ import annotations

from typing import Any


def pair_qualification_errors(exit_code: int, results: dict[str, Any]) -> list[str]:
    """Return strict consumer-side reasons a model pair cannot be `passed`."""
    errors: list[str] = []
    if exit_code != 0:
        errors.append(f"pair_exit_code={exit_code}")
    if results.get("passed") is not True:
        errors.append("pair_results.passed!=true")
    scores = results.get("scores")
    if not isinstance(scores, list) or not scores:
        errors.append("pair_results.scores_missing")
        scores = []
    episode_count = results.get("episode_count")
    if not isinstance(episode_count, int) or episode_count != len(scores):
        errors.append("pair_results.episode_count_mismatch")
    if results.get("scenario_constructed_count") != len(scores):
        errors.append("pair_results.scenario_constructed_count_mismatch")
    modes = {str(row.get("execution_mode")) for row in scores if isinstance(row, dict)}
    if modes != {"linear", "async"}:
        errors.append("pair_results.linear_async_pair_incomplete")
    for index, row in enumerate(scores):
        if not isinstance(row, dict):
            errors.append(f"scores[{index}]_not_object")
            continue
        label = str(row.get("execution_mode") or index)
        # Only an infrastructure/benchmark failure to CONSTRUCT the scenario makes
        # an episode unscored.  A participant who stops early, does not wait for a
        # late result, or never observes every event is still a *scored failure*:
        # the score already reflects the points it failed to win.  Requiring full
        # exposure/entry here would conflate a genuine model failure (which counts
        # as a failure) with a qualification failure (which is unscored).
        if row.get("scenario_constructed") is not True:
            errors.append(f"{label}.scenario_constructed!=true")
        if row.get("score_status") != "scored":
            errors.append(f"{label}.score_status!=scored")
        if row.get("infrastructure_failures"):
            errors.append(f"{label}.infrastructure_failures_nonempty")
    return errors
