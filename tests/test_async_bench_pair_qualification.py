from async_rbench.evaluation.pair_qualification import pair_qualification_errors
from async_rbench.evaluation.aggregate import pair_identity_errors


def result(score_overrides=None):
    scores = []
    for mode in ("linear", "async"):
        row = {
            "execution_mode": mode,
            "scenario_constructed": True,
            "scenario_exposed": True,
            "scenario_entry": True,
            "score_status": "scored",
            "infrastructure_failures": [],
        }
        row.update((score_overrides or {}).get(mode, {}))
        scores.append(row)
    return {
        "passed": True,
        "episode_count": 2,
        "scenario_constructed_count": 2,
        "scenario_exposed_count": 2,
        "scores": scores,
    }


def test_strict_pair_accepts_complete_scored_pair():
    assert pair_qualification_errors(0, result()) == []


def test_strict_pair_rejects_nonzero_exit_even_if_results_claim_passed():
    assert "pair_exit_code=1" in pair_qualification_errors(1, result())


def test_pair_allows_early_stop_scored_as_failure():
    # A participant who stops early / does not wait for a late result is a
    # *scored failure*, not an unscored episode.  Incomplete exposure must not
    # disqualify the pair (the score already reflects the points it lost).
    payload = result({"async": {"scenario_exposed": False, "scenario_entry": False}})
    payload["scenario_exposed_count"] = 1
    payload["passed"] = True
    assert pair_qualification_errors(0, payload) == []


def test_strict_pair_rejects_false_passed_or_unscored_episode():
    # ``passed`` must be true and every episode must be scored; but exposure and
    # entry completeness are model outcomes, not qualification criteria.
    payload = result({"async": {"scenario_exposed": False}})
    payload["passed"] = False
    errors = pair_qualification_errors(0, payload)
    assert "pair_results.passed!=true" in errors
    assert "async.scenario_exposed!=true" not in errors
    errors = pair_qualification_errors(0, result({
        "async": {"scenario_entry": False, "score_status": "unscored"}
    }))
    assert "async.scenario_entry!=true" not in errors
    assert "async.score_status!=scored" in errors


# ---------------------------------------------------------------------------
# Task 11 Step 4: aggregation-level counterfactual pair qualification.  A pair
# must share the benchmark-owned fixed factors (case/instance/seed, task bundle,
# child pool identity/budget/provider) while the main model/provider may differ.
# ---------------------------------------------------------------------------


def _pair(linear_extra=None, async_extra=None):
    linear = {
        "execution_mode": "linear", "case_id": "c1", "instance_id": "i1",
        "agent_seed": 7, "counterfactual_pair_id": "c1-i1-0",
        "task_bundle_sha256": "bundle-a", "child_pool_id": "pool-x",
        "child_budget": "shared:1m", "child_provider": "codex_cli",
        "child_model": "mini", "child_backend": "codex_cli",
        "child_child_overlap": True, "main_child_overlap": False,
        "individual_result_presentations": 0, "atomic_bundle_presentations": 1,
        "score_status": "scored",
    }
    async_row = {
        "execution_mode": "async", "case_id": "c1", "instance_id": "i1",
        "agent_seed": 7, "counterfactual_pair_id": "c1-i1-0",
        "task_bundle_sha256": "bundle-a", "child_pool_id": "pool-x",
        "child_budget": "shared:1m", "child_provider": "codex_cli",
        "child_model": "mini", "child_backend": "codex_cli",
        "individual_result_presentations": 2,
        "score_status": "scored",
    }
    if linear_extra:
        linear.update(linear_extra)
    if async_extra:
        async_row.update(async_extra)
    return linear, async_row


def test_pair_identity_accepts_matching_fixed_factors():
    left, right = _pair()
    assert pair_identity_errors(left, right) == []


def test_pair_identity_allows_main_model_and_provider_to_differ():
    left, right = _pair()
    left["model"] = "deepseek-v4-pro"
    left["main_provider"] = "openai_compatible"
    right["model"] = "claude-sonnet"
    right["main_provider"] = "anthropic"
    assert pair_identity_errors(left, right) == []


def test_pair_identity_rejects_child_pool_mismatch():
    left, right = _pair()
    right["child_pool_id"] = "pool-y"
    errors = pair_identity_errors(left, right)
    assert any("child_pool" in error for error in errors)


def test_pair_identity_rejects_task_bundle_and_seed_mismatch():
    left, right = _pair()
    right["task_bundle_sha256"] = "bundle-b"
    errors = pair_identity_errors(left, right)
    assert any("task_bundle" in error for error in errors)
    left, right = _pair()
    right["agent_seed"] = 8
    errors = pair_identity_errors(left, right)
    assert any("seed" in error for error in errors)


def test_pair_identity_checks_linear_sync_aggregation_invariants():
    left, right = _pair()
    left["child_child_overlap"] = False
    left["main_child_overlap"] = True
    left["individual_result_presentations"] = 3
    left["atomic_bundle_presentations"] = 2
    errors = pair_identity_errors(left, right)
    assert "linear.child_child_overlap!=true" in errors
    assert "linear.main_child_overlap!=false" in errors
    assert "linear.individual_result_presentations!=0" in errors
    assert "linear.atomic_bundle_presentations!=1" in errors


def test_pair_identity_checks_async_presentation_invariant():
    left, right = _pair()
    right["individual_result_presentations"] = 0
    errors = pair_identity_errors(left, right)
    assert any("async.individual_result_presentations" in error for error in errors)
