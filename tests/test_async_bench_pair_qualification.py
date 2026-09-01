from async_rbench.evaluation.pair_qualification import pair_qualification_errors


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
