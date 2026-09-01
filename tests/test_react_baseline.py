from async_rbench.react_baseline import BlockingReActEnvironment, score_react_state


def _fixture():
    public = {
        "case_id": "case-1",
        "source": {"instruction": "Perform the correct final action."},
        "causal_record": {
            "prior_work": [{"id": "done", "description": "already done"}],
            "independent_event": {"id": "event", "description": "new evidence"},
            "affected_work": [
                {"id": "required-a", "description": "do A"},
                {"id": "required-b", "description": "do B"},
            ],
        },
    }
    expected = {
        "affected_work_ids": ["required-a", "required-b"],
        "superseded_work_ids": ["stale"],
    }
    return public, expected


def test_blocking_react_oracle_gets_full_dynamic_semantic_score():
    public, expected = _fixture()
    env = BlockingReActEnvironment(public, expected)
    env.call("inspect_current_state")
    env.call("query_authoritative_evidence")
    env.call("execute_action", {"action_id": "required-a"})
    env.call("execute_action", {"action_id": "required-b"})
    env.call("inspect_final_state")
    env.call("finish", {"summary": "done"})
    result = score_react_state(public, expected, env.state)
    assert result["score"] == 1.0
    assert result["test_point_count"] == 6
    assert result["unscored_point_count"] == 0


def test_react_score_penalises_missing_stale_and_unverified_work():
    public, expected = _fixture()
    env = BlockingReActEnvironment(public, expected)
    env.call("execute_action", {"action_id": "required-a"})
    env.call("execute_action", {"action_id": "stale"})
    env.call("finish", {"summary": "done"})
    result = score_react_state(public, expected, env.state)
    checks = {item["id"]: item["passed"] for item in result["test_points"]}
    assert not checks["authoritative_evidence_acquired"]
    assert not checks["required_action_02"]
    assert not checks["no_superseded_action"]
    assert not checks["no_extraneous_or_duplicate_action"]
    assert not checks["final_state_reverified"]
    assert result["score"] == 0.3


def test_repeated_evidence_query_is_explicitly_cached_and_final_inspection_guides_finish():
    public, expected = _fixture()
    env = BlockingReActEnvironment(public, expected)
    env.call("query_authoritative_evidence")
    repeated = env.call("query_authoritative_evidence")
    assert "no new information" in repeated["note"]
    final = env.call("inspect_final_state")
    assert "call finish" in final["next_step"]
