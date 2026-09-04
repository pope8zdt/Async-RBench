from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from .weighting import SCORE_POLICY_VERSION

DATASET_SPLITS = ("calibration", "development", "test")


EXECUTION_MODES = ("linear", "async")


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def _x(item: dict[str, Any]) -> float | None:
    if item.get("score_status") != "scored":
        return None
    value = item.get("test_point_pass_rate")
    return float(value) if value is not None else None


def _named_score(item: dict[str, Any], key: str) -> float | None:
    if item.get("score_status") != "scored":
        return None
    value = item.get(key)
    return float(value) if value is not None else None


def _model_key(item: dict[str, Any]) -> str:
    """Stable single-model factor identity for an episode.

    A scored record carries the requested and resolved model identities.  The
    resolved identity is authoritative when present; otherwise fall back to the
    requested model so aggregation never silently merges distinct models.
    """
    return str(
        item.get("model")
        or item.get("resolved_model")
        or item.get("requested_model")
        or "unknown-model"
    )


def _config_key(item: dict[str, Any]) -> str:
    """Stable configuration digest for an episode.

    `scaffold_and_protocol_sha256` hashes the evaluator scaffolding and protocol
    (not the participant), so it is a robust config factor shared across repeats
    of the same run while still distinguishing runs that changed the evaluator.
    """
    return str(
        item.get("scaffold_and_protocol_sha256")
        or item.get("resource_policy_sha256")
        or item.get("runtime_mode")
        or ""
    )


def _semantic(item: dict[str, Any]) -> float | None:
    # The linear baseline is semantic-only. Historic records store the semantic
    # task score as ``semantic_task_score``; when a record predates that field
    # its ``test_point_pass_rate`` is the semantic proxy.  This fallback is
    # correct for the *linear* semantic baseline — unlike ``_dynamic``, which
    # must never fall back to the semantic pass rate.
    value = _named_score(item, "semantic_task_score")
    return value if value is not None else _x(item)


def _dynamic(item: dict[str, Any]) -> float | None:
    if _mode(item) != "async":
        return None
    return _named_score(item, "dynamic_control_score")


def _dt(item: dict[str, Any]) -> float | None:
    if _mode(item) != "async":
        return None
    return _named_score(item, "dt_score")


def _base_task(item: dict[str, Any]) -> float | None:
    """Base Task Score (BTS) for an episode's own execution mode.

    ``base_task_score`` is the mode-neutral ``score_domain == base_task`` fraction
    computed by the scorer, so a linear episode carries Linear BTS and an async
    episode carries Async BTS.  Reading the field directly rather than inferring
    it from a blended measure keeps Linear BTS and Async BTS independent (spec 2.2).
    """
    return _named_score(item, "base_task_score")


def _async_drs(item: dict[str, Any]) -> float | None:
    """Per-episode Async Dynamic Replanning Score (Async DRS).

    Only async episodes carry an ``async_drs``; linear episodes never do.
    """
    if _mode(item) != "async":
        return None
    return _named_score(item, "async_drs")


def _tokens(item: dict[str, Any]) -> float | None:
    value = item.get("total_tokens")
    return float(value) if value is not None else None


def _mode(item: dict[str, Any]) -> str:
    return str(item.get("execution_mode") or "")


def _pair_key(item: dict[str, Any]) -> tuple[Any, ...]:
    """Identity of one repeated within-instance pair.

    Must be unique per (case, instance, repeat) *and* per model / seed / config,
    otherwise merging two models or two seeds would pair episodes that never
    shared a counterfactual and report a spurious effect.

    The fixed benchmark-owned factors are part of the key too (spec 8): a
    linear/async pair must share the same task bundle, child pool identity, and
    child provider. Two runs built against a different child pool
    never share a counterfactual even when they agree on case/instance/model, so
    they must not be paired.
    """
    return (
        item.get("case_id"), item.get("instance_id", "seed-1"),
        item.get("repeat", 0), item.get("guidance", "protocol"),
        item.get("adapter_profile"), item.get("runtime_mode"),
        item.get("split", "unassigned"),
        item.get("agent_seed"), item.get("counterfactual_pair_id"),
        _model_key(item), _config_key(item),
        # Fixed child-pool identity factors: absent (None) on both sides matches
        # trivially, present and differing forces separate pairs.
        item.get("task_bundle_sha256"), item.get("child_pool_id"),
        item.get("child_provider"),
        item.get("child_model"), item.get("child_backend"),
    )


# Fixed benchmark-owned factors that a linear/async counterfactual pair must
# share (spec 8).  The main model/provider is deliberately excluded: different
# main models legitimately use the same fixed child pool.
_PAIR_FIXED_FACTORS = (
    ("case_id", "case"), ("instance_id", "instance"), ("agent_seed", "seed"),
    ("counterfactual_pair_id", "counterfactual_pair_id"),
    ("task_bundle_sha256", "task_bundle"),
    ("child_pool_id", "child_pool"),
    ("child_provider", "child_provider"),
    ("child_model", "child_model"),
    ("child_backend", "child_backend"),
)


def pair_identity_errors(
    left: dict[str, Any], right: dict[str, Any],
) -> list[str]:
    """Return strict pairing errors for a linear/async counterfactual pair.

    A valid pair must share the fixed benchmark-owned factors above (case /
    instance / seed / task bundle / child pool id / child provider
    / child model / child backend).  The main model and main provider are the
    participant factor and are allowed to differ.  Linear must satisfy the
    synchronous-aggregation invariant (spec 6) and Async the per-result
    presentation invariant (spec 5.1); both are benchmark-owned topology facts
    that disqualify a pair when violated.
    """
    errors: list[str] = []
    for field, label in _PAIR_FIXED_FACTORS:
        left_value = left.get(field)
        right_value = right.get(field)
        if (
            left_value is not None and right_value is not None
            and left_value != right_value
        ):
            errors.append(f"pair.{label} mismatch: {left_value!r} != {right_value!r}")
    # Linear synchronous-aggregation invariants (spec 6): children overlap, but
    # main never overlaps a child, no individual result is presented, and exactly
    # one atomic bundle is presented per wave.
    if str(left.get("execution_mode")) == "linear":
        if left.get("child_child_overlap") is False:
            errors.append("linear.child_child_overlap!=true")
        if left.get("main_child_overlap") is True:
            errors.append("linear.main_child_overlap!=false")
        if left.get("individual_result_presentations", 0) != 0:
            errors.append("linear.individual_result_presentations!=0")
        if left.get("atomic_bundle_presentations") not in (None, 1):
            errors.append("linear.atomic_bundle_presentations!=1")
    # Async per-result presentation invariant (spec 5.1): a scored async episode
    # must have presented at least one real result into a started main request.
    if str(right.get("execution_mode")) == "async":
        presented = right.get("individual_result_presentations")
        if (
            isinstance(presented, int)
            and presented < 1
            and right.get("score_status") == "scored"
        ):
            errors.append("async.individual_result_presentations<1")
    return errors


def _pair_quality_errors(records: list[dict[str, Any]]) -> list[str]:
    """Aggregate-level pair qualification errors for every matched linear/async pair.

    Pairs are formed per (case, instance, repeat, model, seed, config, fixed child
    factors); within each pair the linear and async records must share the fixed
    benchmark-owned factors and satisfy their mode topology invariants.  Duplicate
    errors are collapsed so the audit is a stable set.
    """
    by_family: dict[str, dict[tuple[Any, ...], dict[str, dict[str, Any]]]] = defaultdict(dict)
    for item in records:
        family = _family_key(item)
        by_family[family].setdefault(_pair_key(item), {})[_mode(item)] = item
    errors: list[str] = []
    for _, pairs in sorted(by_family.items()):
        for pair in pairs.values():
            if "linear" in pair and "async" in pair:
                errors.extend(pair_identity_errors(pair["linear"], pair["async"]))
    return sorted(set(errors))


def _family_key(item: dict[str, Any]) -> str:
    return str(item.get("case_id"))


# The headline macro unit is the event-theme family (the 8 case categories), not
# the ~200 registration families.  A theme with very few held-out test instances
# has an unusable single-point variance, so the headline keeps only themes with
# at least this many scored test instances and reports the rest.
MINIMUM_THEME_TEST_INSTANCES = 3


def _theme(
    item: dict[str, Any], theme_by_case: dict[str, str] | None = None,
) -> str:
    """Resolve an episode's primary event theme.

    Prefer a theme stamped directly on the score record; fall back to a
    ``case_id -> theme`` map supplied by the caller so aggregation stays
    self-contained and works against records that predate the stamp.
    """
    value = (
        item.get("event_theme") or item.get("theme") or item.get("primary_event_theme")
    )
    if value:
        return str(value)
    case_id = str(item.get("case_id"))
    if theme_by_case and case_id in theme_by_case:
        return str(theme_by_case[case_id])
    return "unassigned"


def _theme_macro(
    records: list[dict[str, Any]], mode: str,
    value: Callable[[dict[str, Any]], float | None] = _x,
    theme_by_case: dict[str, str] | None = None,
    minimum_theme_test_instances: int = MINIMUM_THEME_TEST_INSTANCES,
) -> dict[str, Any]:
    """Theme-equal headline macro.

    Imbalance is resolved by averaging at the theme level: within a theme, cases
    are balanced (each case's instance-mean contributes once) before themes are
    balanced (each theme contributes once).  A theme whose number of scored
    instances is below ``minimum_theme_test_instances`` is excluded from the
    headline (its single-point variance is not a mean) but reported as dropped so
    the coverage loss is never silent.
    """
    by_theme_case_instance: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    instance_counts: dict[str, int] = defaultdict(int)
    for item in records:
        if _mode(item) != mode:
            continue
        observed = value(item)
        if observed is None:
            continue
        theme = _theme(item, theme_by_case)
        by_theme_case_instance[theme][str(item["case_id"])][
            str(item.get("instance_id", "seed-1"))
        ].append(observed)
    theme_scores: dict[str, float] = {}
    for theme, by_case in sorted(by_theme_case_instance.items()):
        case_values = [
            mean for by_instance in by_case.values()
            if (mean := _mean([
                instance_mean for values in by_instance.values()
                if (instance_mean := _mean(values)) is not None
            ])) is not None
        ]
        instance_counts[theme] = sum(
            len(by_instance) for by_instance in by_case.values()
        )
        if case_values:
            theme_scores[theme] = _mean(case_values)
    ranked = sorted(theme_scores.items())
    if len(ranked) == 1:
        # A single theme cannot be "narrowed" away: with no multi-theme average
        # for an underpowered theme to distort, it stands as the whole headline.
        # This also lets a dataset carrying no theme breakdown (every record
        # resolving to "unassigned") degrade to the case-macro value instead of
        # producing an undefined headline.
        kept = dict(ranked)
        dropped = {}
    else:
        kept = {
            theme: score for theme, score in ranked
            if instance_counts[theme] >= minimum_theme_test_instances
        }
        dropped = {
            theme: score for theme, score in ranked
            if instance_counts[theme] < minimum_theme_test_instances
        }
    return {
        "mean": _mean(list(kept.values())),
        "kept_scores": kept,
        "dropped_scores": dropped,
        "theme_instance_counts": dict(sorted(instance_counts.items())),
    }


def _theme_estimands(
    records: list[dict[str, Any]], mode: str,
    value: Callable[[dict[str, Any]], float | None] = _x,
    theme_by_case: dict[str, str] | None = None,
    minimum_theme_test_instances: int = MINIMUM_THEME_TEST_INSTANCES,
) -> list[float]:
    """Per-kept-theme value array used by the multiplicity-correct bootstrap."""
    macro = _theme_macro(
        records, mode, value, theme_by_case, minimum_theme_test_instances,
    )
    return list(macro["kept_scores"].values())




def _family_estimands(
    records: list[dict[str, Any]], value: Callable[[dict[str, Any]], float | None],
) -> list[float]:
    """Per-registered-case estimate array, case-equal.

    The legacy helper name predates the terminology correction. Each ``case_id``
    contributes the mean of its per-instance means, so a case with many instances
    and repeats is not weighted more than a single-instance case. A benchmark case
    family is instead one of the eight ``primary_event_theme`` categories.
    """
    by_family: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for item in records:
        observed = value(item)
        if observed is not None:
            by_family[str(item.get("case_id"))][
                str(item.get("instance_id", "seed-1"))
            ].append(float(observed))
    estimates: list[float] = []
    for _, by_instance in sorted(by_family.items()):
        instance_means = [
            mean for values in by_instance.values()
            if (mean := _mean(values)) is not None
        ]
        if instance_means:
            estimates.append(_mean(instance_means))
    return estimates


def bootstrap_ci(
    records: list[dict[str, Any]],
    estimator: Callable[[list[dict[str, Any]]], float | None],
    iterations: int = 1000,
    seed: int = 2026,
    pre_aggregate: Callable[
        [list[dict[str, Any]]], list[float]
    ] | None = None,
) -> list[float] | None:
    """Cluster bootstrap, multiplicity-correct.

    The naive approach (resample whole clusters of records under *replacement*,
    then re-run a macro that de-duplicates by ``case_id``) silently drops the
    draw multiplicity: a family drawn three times is averaged only once, so the
    CI is too narrow. Instead we pre-aggregate to one per-cluster estimand and
    resample *that* array with replacement, preserving the cluster bootstrap's
    between-family variation.

    ``pre_aggregate`` maps a record list to the per-cluster value array. When it
    is omitted, each record list is passed to ``estimator`` directly (kept for
    estimators that are already family-aware).
    """
    rng = random.Random(seed)
    if pre_aggregate is None:
        # Back-compatible records path: resample registered-case clusters directly.
        clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            clusters[_family_key(record)].append(record)
        keys = list(clusters)
        if not keys:
            return None
        estimates: list[float] = []
        for _ in range(iterations):
            sample: list[dict[str, Any]] = []
            for key in (rng.choice(keys) for _ in keys):
                sample.extend(clusters[key])
            value = estimator(sample)
            if value is not None:
                estimates.append(value)
        return (
            [_percentile(estimates, .025), _percentile(estimates, .975)]
            if estimates else None
        )
    family_values = pre_aggregate(records)
    if not family_values:
        return None
    estimates: list[float] = []
    n = len(family_values)
    for _ in range(iterations):
        sample = [_mean([rng.choice(family_values) for _ in range(n)])]
        estimates.extend(sample)
    return (
        [_percentile(estimates, .025), _percentile(estimates, .975)]
        if estimates else None
    )


def _matched_mode_effect(
    records: list[dict[str, Any]], left: str, right: str,
    value: Callable[[dict[str, Any]], float | None] = _x,
    return_family_values: bool = False,
) -> float | None | tuple[float | None, list[float]]:
    """Matched within-instance effect, averaged at the family level.

    Pairs are formed per (case, instance, repeat, model, seed, config), then the
    mode difference is averaged within each *family* before the family-equal
    macro, so a multi-instance family does not dominate the effect estimate.
    Returns the overall mean, or ``(mean, per_family_values)`` for a bootstrap.
    """
    by_family: dict[str, dict[tuple[Any, ...], dict[str, dict[str, Any]]]] = defaultdict(dict)
    for item in records:
        family = _family_key(item)
        by_family[family].setdefault(_pair_key(item), {})[_mode(item)] = item
    family_values: list[float] = []
    for _, pairs in sorted(by_family.items()):
        differences: list[float] = []
        for pair in pairs.values():
            if left not in pair or right not in pair:
                continue
            left_value = value(pair[left])
            right_value = value(pair[right])
            if left_value is not None and right_value is not None:
                differences.append(left_value - right_value)
        if differences:
            family_values.append(_mean(differences))
    mean = _mean(family_values)
    return (mean, family_values) if return_family_values else mean


def _weighted_rate(
    items: list[dict[str, Any]], weighted_key: str, denominator_field: str,
) -> float | None:
    passed = total = 0
    for item in items:
        if _x(item) is None:
            continue
        counts = item.get(weighted_key) or {}
        passed += int(counts.get("passed", 0))
        total += int(counts.get(denominator_field, 0))
    return passed / total if total else None


def _case_macro(
    records: list[dict[str, Any]], mode: str,
    value: Callable[[dict[str, Any]], float | None] = _x,
) -> tuple[float | None, dict[str, float]]:
    by_case_instance: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for item in records:
        if _mode(item) != mode:
            continue
        observed = value(item)
        if observed is not None:
            by_case_instance[str(item["case_id"])][
                str(item.get("instance_id", "seed-1"))
            ].append(observed)
    case_values: dict[str, float] = {}
    for case_id, by_instance in sorted(by_case_instance.items()):
        instance_values = [
            mean for values in by_instance.values()
            if (mean := _mean(values)) is not None
        ]
        if (case_mean := _mean(instance_values)) is not None:
            case_values[case_id] = case_mean
    return _mean(list(case_values.values())), case_values


def _capability_macro(
    records: list[dict[str, Any]], mode: str,
    value: Callable[[dict[str, Any]], float | None] = _x,
) -> dict[str, float]:
    by_capability_case_instance: dict[
        str, dict[str, dict[str, list[float]]]
    ] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for item in records:
        if _mode(item) != mode:
            continue
        observed = value(item)
        if observed is None:
            continue
        for capability in item.get("capability_categories") or []:
            by_capability_case_instance[str(capability)][str(item["case_id"])][
                str(item.get("instance_id", "seed-1"))
            ].append(observed)
    result: dict[str, float] = {}
    for capability, by_case in sorted(by_capability_case_instance.items()):
        case_values = [
            case_mean
            for by_instance in by_case.values()
            if (case_mean := _mean([
                instance_mean for values in by_instance.values()
                if (instance_mean := _mean(values)) is not None
            ])) is not None
        ]
        if case_values:
            result[capability] = sum(case_values) / len(case_values)
    return result


def _episode_success(item: dict[str, Any]) -> bool | None:
    if item.get("score_status") != "scored":
        return None
    if item.get("dynamic_success") is not None:
        return bool(item["dynamic_success"])
    value = _x(item)
    return value == 1.0 if value is not None else None


def _reliability_pass_at_k(records: list[dict[str, Any]], mode: str, k: int) -> float | None:
    """Strict reliability pass^k (τ-bench): probability k random trials all succeed.

    For one case with ``n`` repeats and ``c`` successes, pass^k is
    ``C(c, k) / C(n, k)`` — that is, the fraction of k-tuples of repeats that all
    succeed, with an exact combinatoric weight rather than the looser "at least k
    of n succeeded" reading.  pass^1 = c/n; pass^3 = P(three randomly drawn
    repeats all succeed).  The macro is case-level: a single case counts once.
    """
    trials: dict[tuple[str, str], list[int]] = defaultdict(list)
    for item in records:
        if _mode(item) != mode:
            continue
        success = _episode_success(item)
        if success is not None:
            trials[(str(item["case_id"]), str(item.get("instance_id", "seed-1")))].append(int(success))
    if not trials:
        return None
    reliabilities: list[float] = []
    for (successes, total) in ((sum(flags), len(flags)) for flags in trials.values()):
        combinations_total = math.comb(total, k)
        if combinations_total <= 0:
            continue
        reliabilities.append(math.comb(successes, k) / combinations_total)
    return _mean(reliabilities) if reliabilities else None


def _pass_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pass_1": _reliability_pass_at_k(records, "async", 1),
        "pass_2": _reliability_pass_at_k(records, "async", 2),
        "pass_3": _reliability_pass_at_k(records, "async", 3),
        "linear_pass_1": _reliability_pass_at_k(records, "linear", 1),
        "linear_pass_2": _reliability_pass_at_k(records, "linear", 2),
        "linear_pass_3": _reliability_pass_at_k(records, "linear", 3),
    }


def _duration(item: dict[str, Any]) -> float | None:
    value = item.get("episode_duration_ms")
    return float(value) if value is not None else None


def _wall_clock_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    def stats(mode: str) -> dict[str, float | None]:
        values = [
            value for item in records
            if _mode(item) == mode and (value := _duration(item)) is not None
        ]
        return {
            "episode_count": len(values),
            "duration_ms_mean": _mean(values),
            "duration_ms_median": _percentile(values, .5),
            "duration_ms_p95": _percentile(values, .95),
            "total_duration_ms": sum(values) if values else None,
        }
    return {"linear": stats("linear"), "async": stats("async")}


def _cost_quality_pareto(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Group by the single-model factor (and profile/runtime), never by adapter
    # profile alone: every model is ``reference_scaffold_api`` internally, so
    # grouping only by profile would silently merge distinct models.
    by_factor: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        by_factor[(
            _model_key(item),
            str(item.get("adapter_profile") or "unknown"),
            str(item.get("runtime_mode") or "unknown"),
        )].append(item)
    rows: list[dict[str, Any]] = []
    for key, items in sorted(by_factor.items()):
        model, profile, runtime = key
        async_items = [item for item in items if _mode(item) == "async"]
        tokens = [v for item in items if (v := _tokens(item)) is not None]
        durations = [v for item in items if (v := _duration(item)) is not None]
        score, _ = _case_macro(async_items, "async", _dynamic)
        semantic, _ = _case_macro(items, "linear", _semantic)
        rows.append({
            "model": model,
            "adapter_profile": profile,
            "runtime_mode": runtime,
            "episode_count": len(items),
            "dynamic_control_score": score,
            "linear_semantic_task_score": semantic,
            "total_tokens_mean": _mean(tokens),
            "total_tokens_p95": _percentile(tokens, .95),
            "duration_ms_mean": _mean(durations),
        })
    return rows


def _aggregate_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        groups[(
            item.get("case_id"), item.get("instance_id", "seed-1"),
            _mode(item), item.get("guidance", "protocol"),
            item.get("adapter_profile"), item.get("runtime_mode"),
            item.get("split", "unassigned"), _model_key(item),
        )].append(item)

    rows: list[dict[str, Any]] = []
    for key, items in sorted(
        groups.items(), key=lambda entry: tuple(str(value or "") for value in entry[0]),
    ):
        case_id, instance_id, mode, guidance, adapter_profile, runtime_mode, split, model = key
        scored = [item for item in items if _x(item) is not None]
        rates = [_x(item) for item in scored]
        digests = {
            str(item["denominator_digest"])
            for item in items if item.get("denominator_digest")
        }
        tokens = [value for item in scored if (value := _tokens(item)) is not None]
        rows.append({
            "case_id": case_id,
            "instance_id": instance_id,
            "execution_mode": mode,
            "guidance": guidance,
            "adapter_profile": adapter_profile,
            "runtime_mode": runtime_mode,
            "split": split,
            "model": model,
            "capability_categories": sorted({
                str(capability)
                for item in items
                for capability in (item.get("capability_categories") or [])
            }),
            "n": len(items),
            "scored_n": len(scored),
            "unscored_n": len(items) - len(scored),
            "leaderboard_eligible_n": sum(
                item.get("leaderboard_eligible") is True for item in items
            ),
            "test_point_pass_rate": _mean([
                float(value) for value in rates if value is not None
            ]),
            "semantic_task_score": _mean([
                value for item in scored if (value := _semantic(item)) is not None
            ]),
            "semantic_test_point_pass_rate": _mean([
                value for item in scored if (value := _semantic(item)) is not None
            ]),
            "dynamic_control_score": _mean([
                value for item in scored if (value := _dynamic(item)) is not None
            ]),
            "control_flow_test_point_pass_rate": _mean([
                value for item in scored if (value := _dynamic(item)) is not None
            ]),
            "dt_score": _mean([
                value for item in scored if (value := _dt(item)) is not None
            ]),
            "dynamic_success_rate": _mean([
                float(item["dynamic_success"]) for item in scored
                if item.get("dynamic_success") is not None
            ]),
            "critical_dynamic_success_rate": _mean([
                float(item["critical_dynamic_success"]) for item in scored
                if item.get("critical_dynamic_success") is not None
            ]),
            "dynamic_dimension_scores": {
                dimension: mean
                for dimension in sorted({
                    str(dimension)
                    for item in scored
                    for dimension in (item.get("dynamic_dimension_scores") or {})
                })
                if (mean := _mean([
                    float(item["dynamic_dimension_scores"][dimension])
                    for item in scored
                    if dimension in (item.get("dynamic_dimension_scores") or {})
                ])) is not None
            },
            "scenario_construction_rate": _mean([
                float(item.get("scenario_constructed") is True) for item in items
            ]),
            "scenario_exposure_rate": _mean([
                float(item.get("scenario_exposure_complete") is True) for item in items
            ]),
            "denominator_digest": next(iter(digests)) if len(digests) == 1 else None,
            "denominator_digest_consistent": bool(digests) and len(digests) == 1,
            "total_tokens_mean": _mean(tokens),
            "total_tokens_median": _percentile(tokens, .5),
            "total_tokens_p95": _percentile(tokens, .95),
            "recovery_latency_mean_ms": _mean([
                float(item["recovery_latency_ms"]) for item in scored
                if item.get("recovery_latency_ms") is not None
            ]),
            "stale_retention_rate": _mean([
                float(item["stale_retention_rate"]) for item in scored
                if item.get("stale_retention_rate") is not None
            ]),
            "reverification_completeness": _mean([
                float(item["reverification_completeness"]) for item in scored
                if item.get("reverification_completeness") is not None
            ]),
        })
    return rows


# Per-episode delivery-opportunity stages summed across the run (spec 3.3 / 9.4).
# The scorer stamps these on each record so aggregation can report how many
# declared events reached each stage and how failures split between participant
# and infrastructure causes.
_OPPORTUNITY_COUNT_FIELDS = (
    "declared_events", "provisional_established", "result_available",
    "adapter_queued", "result_presented", "response_window_closed",
    "participant_provisional_failure", "infrastructure_delivery_failure",
)


def _opportunity_summary(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = {field: 0 for field in _OPPORTUNITY_COUNT_FIELDS}
    for item in records:
        per_episode = item.get("event_opportunity_counts")
        if not isinstance(per_episode, dict):
            continue
        for field in _OPPORTUNITY_COUNT_FIELDS:
            value = per_episode.get(field)
            if isinstance(value, int) and not isinstance(value, bool):
                counts[field] += value
    return counts


# Task 8 paper metrics, aggregated over the per-attempt terminal classifications
# the scorer stamps on each episode record.  Contract acceptance is the gateway
# verdict; verdict acceptance/rejection denominators cover only verdict-bearing
# submissions (gateway_accepted + public_rejection).  Null rates and null token
# means mean "no qualifying attempt in this factor", never zero.
_PAPER_TERMINAL_COUNT_FIELDS = (
    "gateway_accepted", "public_rejection", "sealed_pending_verdict",
    "step_limit_reached", "resource_safety_abort", "no_submission",
    "timeout", "crash", "cancel", "case_contract_failure",
    "infrastructure_failure", "in_flight",
)


def _extra_tokens_from_public_rejections(
    rows: list[dict[str, Any]],
) -> int:
    """Per-episode tokens spent on public rejections beyond the accepted one.

    Per workstream within one episode, public-rejected attempts before the
    gateway-accepted attempt (or all public-rejected attempts when none was
    accepted) are the rejection cost.
    """
    attempt_rows_by_workstream: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        attempt_rows_by_workstream[
            str(row.get("workstream_id") or "no_workstream")
        ].append(row)
    extra = 0
    for attempt_rows in attempt_rows_by_workstream.values():
        ordered = sorted(attempt_rows, key=lambda row: int(row["attempt_number"]))
        accepted_index = next(
            (index for index, row in enumerate(ordered)
             if str(row.get("terminal_class") or "") == "gateway_accepted"), None,
        )
        rejected_up_to = (
            [row for row in ordered[:accepted_index]
             if str(row.get("terminal_class") or "") == "public_rejection"]
            if accepted_index is not None
            else [row for row in ordered
                  if str(row.get("terminal_class") or "") == "public_rejection"]
        )
        extra += sum(int(row.get("tokens") or 0) for row in rejected_up_to)
    return extra


def _paper_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    terminal_counts = {field: 0 for field in _PAPER_TERMINAL_COUNT_FIELDS}
    total_attempts = 0
    sealed_submissions = 0
    gateway_verdict = 0
    gateway_accepted = 0
    public_rejected = 0
    sealed_pending = 0
    first_attempt_verdict = 0
    first_attempt_accepted = 0
    retry_verdict = 0
    retry_accepted = 0
    accepted_tokens = 0
    extra_public_rejection_tokens = 0
    resource_safety_abort_attempts = 0
    step_limit_attempts = 0
    no_submission_attempts = 0
    redelegation_attempts = 0
    invalid_redelegations = 0
    for item in records:
        rows = item.get("child_terminal_classifications")
        if not isinstance(rows, list):
            continue
        for row in rows:
            cls = str(row.get("terminal_class") or "")
            total_attempts += 1
            if cls in terminal_counts:
                terminal_counts[cls] += 1
            retry = bool(row.get("retry") or int(row.get("attempt_number") or 1) >= 2)
            if retry:
                redelegation_attempts += 1
            if cls == "resource_safety_abort":
                resource_safety_abort_attempts += 1
            elif cls == "step_limit_reached":
                step_limit_attempts += 1
            elif cls == "no_submission":
                no_submission_attempts += 1
            if row.get("sealed_submission"):
                sealed_submissions += 1
            tokens = int(row.get("tokens") or 0)
            if cls == "gateway_accepted":
                gateway_accepted += 1
                gateway_verdict += 1
                accepted_tokens += tokens
                if retry:
                    retry_accepted += 1
                    retry_verdict += 1
                else:
                    first_attempt_accepted += 1
                    first_attempt_verdict += 1
            elif cls == "public_rejection":
                public_rejected += 1
                gateway_verdict += 1
                if retry:
                    retry_verdict += 1
                else:
                    first_attempt_verdict += 1
            elif cls == "sealed_pending_verdict":
                sealed_pending += 1
        extra_public_rejection_tokens += _extra_tokens_from_public_rejections(rows)
        invalid_redelegations += int(item.get("invalid_redelegation_count") or 0)

    def _rate(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None

    return {
        # Task 8: per-attempt terminal histogram (attempt dimension included).
        "terminal_class_counts": terminal_counts,
        # Verdict acceptance/rejection rates run over verdict-bearing
        # submissions only; sealed-without-verdict closes, step/safety/no-
        # submission ends, designed terminals, cancels, case-contract and
        # infrastructure failures never enter these denominators.
        "sealed_submission_count": sealed_submissions,
        "gateway_verdict_count": gateway_verdict,
        "gateway_accepted_count": gateway_accepted,
        "public_rejected_count": public_rejected,
        "sealed_pending_verdict_count": sealed_pending,
        "submission_acceptance_rate": _rate(gateway_accepted, gateway_verdict),
        "submission_rejection_rate": _rate(public_rejected, gateway_verdict),
        # First-attempt vs retry acceptance over verdict-bearing submissions.
        "first_attempt_verdict_count": first_attempt_verdict,
        "first_attempt_accepted_count": first_attempt_accepted,
        "first_attempt_acceptance_rate": _rate(
            first_attempt_accepted, first_attempt_verdict,
        ),
        "retry_verdict_count": retry_verdict,
        "retry_accepted_count": retry_accepted,
        "retry_acceptance_rate": _rate(retry_accepted, retry_verdict),
        # Cost metrics over gateway-accepted attempts and public rejections.
        "avg_child_tokens_per_gateway_accepted": _rate(
            accepted_tokens, gateway_accepted,
        ),
        "extra_child_tokens_from_public_rejections": extra_public_rejection_tokens,
        # Model/runtime outcome rates per attempt (never rejection rates).
        "resource_safety_abort_rate_per_attempt": _rate(
            resource_safety_abort_attempts, total_attempts,
        ),
        "child_step_limit_rate_per_attempt": _rate(
            step_limit_attempts, total_attempts,
        ),
        "no_submission_rate_per_attempt": _rate(
            no_submission_attempts, total_attempts,
        ),
        # A redelegation contributing no new evidence is a duplicate evidence
        # retry (P0-9 / Task 7 diagnostic).
        "redelegation_attempt_count": redelegation_attempts,
        "invalid_redelegation_count": invalid_redelegations,
        "invalid_redelegation_rate": _rate(invalid_redelegations, redelegation_attempts),
    }


def _summary(
    records: list[dict[str, Any]], bootstrap_iterations: int,
    theme_by_case: dict[str, str] | None = None,
    minimum_theme_test_instances: int = MINIMUM_THEME_TEST_INSTANCES,
) -> dict[str, Any]:
    linear_semantic, linear_semantic_cases = _case_macro(records, "linear", _semantic)
    async_semantic, async_semantic_cases = _case_macro(records, "async", _semantic)
    async_dynamic, async_dynamic_cases = _case_macro(records, "async", _dynamic)
    async_dt, async_dt_cases = _case_macro(records, "async", _dt)
    # Headline metrics are theme-equal (each of the 8 event categories counts
    # once) rather than dominated by the delayed_authoritative_result plurality.
    theme_dynamic = _theme_macro(
        records, "async", _dynamic, theme_by_case, minimum_theme_test_instances,
    )
    theme_semantic = _theme_macro(
        records, "async", _semantic, theme_by_case, minimum_theme_test_instances,
    )
    theme_linear = _theme_macro(
        records, "linear", _semantic, theme_by_case, minimum_theme_test_instances,
    )
    theme_dt = _theme_macro(
        records, "async", _dt, theme_by_case, minimum_theme_test_instances,
    )
    semantic_drop, semantic_drop_family = _matched_mode_effect(
        records, "linear", "async", _semantic, return_family_values=True,
    )
    token_delta = _matched_mode_effect(records, "async", "linear", _tokens)
    observed_cases = {str(item.get("case_id")) for item in records}
    complete = bool(observed_cases) and all(
        case_id in linear_semantic_cases and case_id in async_dynamic_cases
        for case_id in observed_cases
    )
    scored_async = [item for item in records if _dynamic(item) is not None]
    theme_counts = theme_dynamic["theme_instance_counts"]
    # Base Task Score and Async DRS are independent headlines (spec 2.2): BTS
    # reads the mode-specific ``base_task_score``, DRS reads the per-episode
    # ``async_drs``.  Neither is derived from the blended semantic/dynamic mix.
    linear_bts, linear_bts_cases = _case_macro(records, "linear", _base_task)
    async_bts, async_bts_cases = _case_macro(records, "async", _base_task)
    async_drs_value, async_drs_cases = _case_macro(records, "async", _async_drs)
    theme_linear_bts = _theme_macro(
        records, "linear", _base_task, theme_by_case, minimum_theme_test_instances,
    )
    theme_async_bts = _theme_macro(
        records, "async", _base_task, theme_by_case, minimum_theme_test_instances,
    )
    theme_async_drs = _theme_macro(
        records, "async", _async_drs, theme_by_case, minimum_theme_test_instances,
    )
    bts_complete = bool(observed_cases) and all(
        case_id in linear_bts_cases and case_id in async_bts_cases
        for case_id in observed_cases
    )
    drs_complete = bool(observed_cases) and all(
        case_id in async_drs_cases for case_id in observed_cases
    )
    async_drs_theme_counts = theme_async_drs["theme_instance_counts"]
    return {
        # The three new headlines are the only primary metrics of the new Track
        # A protocol (spec 2.2).  The old blended metrics are reported as legacy
        # diagnostics below and are never selected as ``primary_metric``.
        "primary_metric": [
            "linear_base_task_score",
            "async_base_task_score",
            "async_dynamic_replanning_score",
        ],
        "linear_base_task_score": theme_linear_bts["mean"],
        "async_base_task_score": theme_async_bts["mean"] if bts_complete else None,
        "observed_async_base_task_score": theme_async_bts["mean"],
        "async_dynamic_replanning_score": theme_async_drs["mean"] if drs_complete else None,
        "observed_async_dynamic_replanning_score": theme_async_drs["mean"],
        "paired_bts_delta": _matched_mode_effect(records, "linear", "async", _base_task),
        "theme_linear_base_task_scores": theme_linear_bts["kept_scores"],
        "theme_async_base_task_scores": theme_async_bts["kept_scores"],
        "theme_async_drs_scores": theme_async_drs["kept_scores"],
        "dropped_async_drs_themes": theme_async_drs["dropped_scores"],
        "async_drs_theme_instance_counts": async_drs_theme_counts,
        "async_drs_theme_coverage": (
            len(theme_async_drs["kept_scores"]) / len(async_drs_theme_counts)
            if async_drs_theme_counts else None
        ),
        "case_linear_base_task_scores": linear_bts_cases,
        "case_async_base_task_scores": async_bts_cases if bts_complete else {},
        "case_async_drs_scores": async_drs_cases if drs_complete else {},
        "event_opportunity": _opportunity_summary(records),
        "dynamic_control_score": theme_dynamic["mean"] if complete else None,
        "observed_dynamic_control_score": theme_dynamic["mean"],
        "semantic_task_score": theme_semantic["mean"] if complete else None,
        "linear_semantic_task_score": theme_linear["mean"],
        "async_semantic_task_score": theme_semantic["mean"] if complete else None,
        "dt_score": theme_dt["mean"] if complete else None,
        "paired_semantic_drop": semantic_drop,
        "dynamic_success_rate": _mean([
            float(item["dynamic_success"]) for item in scored_async
            if item.get("dynamic_success") is not None
        ]),
        "critical_dynamic_success_rate": _mean([
            float(item["critical_dynamic_success"]) for item in scored_async
            if item.get("critical_dynamic_success") is not None
        ]),
        # Compatibility aliases. In v9 async X means dynamic control, while the
        # linear baseline is semantic-only; new analyses must use the explicit names.
        "test_point_pass_rate": theme_dynamic["mean"] if complete else None,
        "async_test_point_pass_rate": theme_dynamic["mean"] if complete else None,
        "observed_async_test_point_pass_rate": theme_dynamic["mean"],
        "linear_test_point_pass_rate": theme_linear["mean"],
        "paired_async_replanning_drop": semantic_drop,
        "paired_async_replanning_drop_ci95": bootstrap_ci(
            records,
            lambda sample: _matched_mode_effect(sample, "linear", "async", _semantic),
            bootstrap_iterations,
            pre_aggregate=lambda sample: _matched_mode_effect(
                sample, "linear", "async", _semantic, return_family_values=True,
            )[1],
        ),
        "paired_bts_delta_ci95": bootstrap_ci(
            records,
            lambda sample: _matched_mode_effect(sample, "linear", "async", _base_task),
            bootstrap_iterations,
            pre_aggregate=lambda sample: _matched_mode_effect(
                sample, "linear", "async", _base_task, return_family_values=True,
            )[1],
        ),
        "paired_async_token_delta": token_delta,
        "pass_at_k": _pass_summary(records),
        "wall_clock": _wall_clock_summary(records),
        "cost_quality_pareto": _cost_quality_pareto(records),
        "dynamic_control_score_ci95": bootstrap_ci(
            [item for item in records if _mode(item) == "async"],
            lambda sample: _theme_macro(
                sample, "async", _dynamic, theme_by_case, minimum_theme_test_instances,
            )["mean"],
            bootstrap_iterations,
            pre_aggregate=lambda sample: _theme_estimands(
                sample, "async", _dynamic, theme_by_case, minimum_theme_test_instances,
            ),
        ),
        "case_dynamic_control_scores": async_dynamic_cases if complete else {},
        "observed_case_dynamic_control_scores": async_dynamic_cases,
        "case_async_semantic_task_scores": async_semantic_cases,
        "case_linear_semantic_task_scores": linear_semantic_cases,
        "case_dt_scores": async_dt_cases if complete else {},
        "capability_dynamic_control_scores": _capability_macro(records, "async", _dynamic),
        "case_async_test_point_pass_rates": async_dynamic_cases if complete else {},
        "observed_case_async_test_point_pass_rates": async_dynamic_cases,
        "case_linear_test_point_pass_rates": linear_semantic_cases,
        "capability_async_test_point_pass_rates": _capability_macro(records, "async", _dynamic),
        # Theme coverage bookkeeping: which of the 8 event themes the headline
        # actually covers, and which were dropped for having too few test instances.
        "theme_dynamic_control_scores": theme_dynamic["kept_scores"],
        "dropped_dynamic_themes": theme_dynamic["dropped_scores"],
        "dynamic_theme_instance_counts": theme_counts,
        "dynamic_theme_coverage": (
            len(theme_dynamic["kept_scores"]) / len(theme_counts) if theme_counts else None
        ),
        "theme_instance_count_minimum": minimum_theme_test_instances,
        "paired_mode_coverage_complete": complete,
        # Task 8: paper metrics are mode-separated.  The paper-facing Async
        # claim must read the Async subgroup of ``paper_metrics_by_mode``; no
        # combined value may be read as an Async claim.  The all-modes rollup is
        # kept under an explicit descriptive name.
        "paper_metrics_by_mode": {
            mode: _paper_metrics([item for item in records if _mode(item) == mode])
            for mode in EXECUTION_MODES
        },
        "paper_metrics_all_modes_descriptive": _paper_metrics(records),
    }


def aggregate_reports(
    records: list[dict[str, Any]], bootstrap_iterations: int = 1000,
    minimum_counterfactual_coverage: float = 0.0,
    planned_episodes: list[dict[str, Any]] | None = None,
    theme_by_case: dict[str, str] | None = None,
    minimum_theme_test_instances: int | None = None,
) -> dict[str, Any]:
    invalid_modes = sorted({_mode(item) for item in records} - set(EXECUTION_MODES))
    official = [
        item for item in records
        if item.get("leaderboard_eligible") is True
        and item.get("score_policy_version") == SCORE_POLICY_VERSION
    ]
    planned = list(planned_episodes or [])
    planned_ids = {
        str(item["episode_id"]) for item in planned if item.get("episode_id") is not None
    }
    observed_ids = {
        str(item["episode_id"]) for item in records if item.get("episode_id") is not None
    }
    exclusion_reasons: dict[str, int] = defaultdict(int)
    for item in records:
        if (
            item.get("leaderboard_eligible") is True
            and item.get("score_policy_version") == SCORE_POLICY_VERSION
        ):
            continue
        reasons = list(item.get("leaderboard_ineligibility_reasons") or [])
        if item.get("score_policy_version") != SCORE_POLICY_VERSION:
            reasons.append("score_policy_mismatch")
        if not reasons:
            reasons.append("not_official_track_a")
        for reason in reasons:
            exclusion_reasons[str(reason)] += 1

    official_by_factor: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in official:
        official_by_factor[(
            str(item.get("guidance", "protocol")), _model_key(item),
        )].append(item)
    official_rows = _aggregate_rows(official)
    development_rows = _aggregate_rows(records)
    if minimum_theme_test_instances is None:
        minimum_theme_test_instances = MINIMUM_THEME_TEST_INSTANCES
    missing_episode_ids = sorted(planned_ids - observed_ids) if planned else None
    official_comparability = (
        all(row.get("denominator_digest_consistent") is True for row in official_rows)
        if official_rows else None
    )
    development_comparability = (
        all(row.get("denominator_digest_consistent") is True for row in development_rows)
        if development_rows else None
    )
    official_models = sorted({_model_key(item) for item in official})
    official_splits = sorted({
        str(item.get("split", "unassigned")) for item in official
    })

    # Hard-fail gates: a run must not silently certify a leaderboard when the
    # manifest promised episodes that never ran, when the same case instance was
    # scored against more than one denominator digest (digest drift), when an
    # official headline mixes held-out test cases with calibration/development
    # ones, when distinct models were merged into one headline, or when a
    # record's execution_mode is not in the contract's modes.
    hard_fail_reasons: list[str] = []
    if missing_episode_ids:
        hard_fail_reasons.append("missing_episodes")
    if official_comparability is False:
        hard_fail_reasons.append("official_denominator_digest_drift")
    if development_comparability is False:
        hard_fail_reasons.append("development_denominator_digest_drift")
    if official_splits and official_splits != ["test"]:
        hard_fail_reasons.append("official_split_not_test")
    if len(official_models) > 1:
        hard_fail_reasons.append("multi_model_official_merge")
    for item in official:
        if item.get("split") not in DATASET_SPLITS:
            hard_fail_reasons.append("official_split_unset")
            break
    if invalid_modes:
        hard_fail_reasons.append("invalid_execution_modes")
    # P1-15: an abnormal Linear episode (zero main-side measurement) must never
    # certify a leaderboard.  Checked from the raw record rather than the
    # runner-stamped flags, so a stale pre-gate score file cannot slip an empty
    # Linear measurement into an official headline.
    linear_zero_main_ids = sorted({
        str(item.get("episode_id"))
        for item in records
        if _mode(item) == "linear" and int(item.get("main_tokens") or 0) == 0
    })
    official_linear_zero_main = [
        str(item.get("episode_id")) for item in official
        if _mode(item) == "linear" and int(item.get("main_tokens") or 0) == 0
    ]
    if official_linear_zero_main:
        hard_fail_reasons.append("official_linear_zero_main_tokens")

    # Task 10: per-attempt terminal integrity of the scorer-stamped
    # ``child_terminal_classifications``.  A private-only rejection (a
    # ``case_contract_failure`` row carrying rejection codes but no public code)
    # and an in-flight row both mean a spawned child never reached a concrete,
    # model-verdict terminal.  Development runs are reported in the audit counts
    # but never block a certification of the official episodes.
    def _terminal_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
        rows = item.get("child_terminal_classifications")
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def _private_only_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            row for row in _terminal_rows(item)
            if str(row.get("terminal_class") or "") == "case_contract_failure"
            and (row.get("reason_codes")) and not (row.get("public_codes"))
        ]

    def _in_flight_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            row for row in _terminal_rows(item)
            if str(row.get("terminal_class") or "") == "in_flight"
        ]

    private_submission_rejection_ids = sorted({
        str(item.get("episode_id"))
        for item in records if _private_only_rows(item)
    })
    unknown_child_terminal_ids = sorted({
        str(item.get("episode_id"))
        for item in records if _in_flight_rows(item)
    })
    if any(_private_only_rows(item) for item in official):
        hard_fail_reasons.append("private_submission_rejection")
    if any(_in_flight_rows(item) for item in official):
        hard_fail_reasons.append("unknown_child_terminal")

    return {
        "architecture_version": "8.0",
        "leaderboard": [
            {
                "guidance": guidance,
                "model": model,
                **_summary(
                    items, bootstrap_iterations, theme_by_case, minimum_theme_test_instances,
                ),
            }
            for (guidance, model), items in sorted(official_by_factor.items())
        ],
        "development_summary": _summary(
            records, bootstrap_iterations, theme_by_case, minimum_theme_test_instances,
        ),
        "rows": development_rows,
        "audit": {
            "execution_modes": list(EXECUTION_MODES),
            "invalid_execution_modes": invalid_modes,
            "planned_episode_count": len(planned) if planned else None,
            "observed_episode_count": len(records),
            "missing_episode_ids": missing_episode_ids,
            "manifest_completion_rate": (
                len(planned_ids & observed_ids) / len(planned_ids) if planned_ids else None
            ),
            "leaderboard_eligible_episode_count": len(official),
            "leaderboard_excluded_episode_count": len(records) - len(official),
            "leaderboard_exclusion_reasons": dict(sorted(exclusion_reasons.items())),
            "official_models": official_models,
            "official_splits": official_splits,
            "all_conformance_passed": (
                all(item.get("conformance_passed") is True for item in official)
                if official else None
            ),
            "denominator_comparability_ok": official_comparability,
            "development_denominator_comparability_ok": development_comparability,
            "hard_fail": bool(hard_fail_reasons),
            "hard_fail_reasons": hard_fail_reasons,
            "visibility_leakage_detected": any(
                item.get("visibility_leakage_detected") is True for item in records
            ),
            "required_score_policy_version": SCORE_POLICY_VERSION,
            "headline_macro_unit": "event_theme",
            "minimum_theme_test_instances": minimum_theme_test_instances,
            "resolved_themes": len({_theme(item, theme_by_case) for item in records}),
            "observed_score_policy_versions": sorted({
                str(item.get("score_policy_version") or "legacy-or-missing")
                for item in records
            }),
            "scenario_construction_rate": _mean([
                float(item.get("scenario_constructed") is True) for item in records
            ]),
            "scenario_exposure_rate": _mean([
                float(item.get("scenario_exposure_complete") is True) for item in records
            ]),
            "deprecated_minimum_counterfactual_coverage": minimum_counterfactual_coverage,
            "opportunity_counts": _opportunity_summary(records),
            "pair_quality_errors": _pair_quality_errors(records),
            "linear_abnormal_episode_count": len(linear_zero_main_ids),
            "linear_abnormal_episode_ids": linear_zero_main_ids,
            "private_submission_rejection_count": len(private_submission_rejection_ids),
            "private_submission_rejection_episode_ids": private_submission_rejection_ids,
            "unknown_child_terminal_count": len(unknown_child_terminal_ids),
            "unknown_child_terminal_episode_ids": unknown_child_terminal_ids,
        },
    }


def load_reports(root: Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in sorted(root.rglob("score.json")):
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts[:-1]):
            continue
        reports.append(json.loads(path.read_text(encoding="utf-8")))
    return reports
