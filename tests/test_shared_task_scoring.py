from async_rbench.authoritative_capsule import oracle_submission
from async_rbench.react_baseline import BlockingReActEnvironment
from async_rbench.shared_task_scoring import (
    score_capsule_task_outcome,
    score_react_task_outcome,
)


def test_capsule_outcome_oracle_is_full_score(tmp_path):
    case_dir = tmp_path / "case"
    (case_dir / "private").mkdir(parents=True)
    public = {
        "case_id": "c1",
        "source": {"source_id": "s1", "instruction_sha256": "h"},
        "causal_record": {
            "prior_work": [{"id": "p1"}],
            "affected_work": [{"id": "a1", "description": "do a1"}, {"id": "a2"}],
            "independent_event": {"id": "e1"},
        },
        "scenarios": {"linear": {"event_release_tick": 0}, "async": {"event_release_tick": 2}},
    }
    expected = {
        "event_id": "e1",
        "prior_work_ids": ["p1"],
        "affected_work_ids": ["a1", "a2"],
        "superseded_work_ids": ["x1"],
    }
    import json
    (case_dir / "case.json").write_text(json.dumps(public), encoding="utf-8")
    (case_dir / "private" / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
    submission = oracle_submission(case_dir, "linear")
    score = score_capsule_task_outcome(public, expected, submission)
    assert score["score"] == 1.0
    assert score["test_point_count"] == 6

    # A final-state representation may include preserved prior work.  It is
    # equivalent to the delta-only oracle representation and must not lose a
    # task-outcome point.
    submission["final_action_ids"].append("p1")
    score_with_prior = score_capsule_task_outcome(public, expected, submission)
    assert score_with_prior["score"] == 1.0

    # The delivered observation itself is not an executed action.  Putting it
    # in final_action_ids remains a real protocol error.
    submission["final_action_ids"].append("e1")
    score_with_event_as_action = score_capsule_task_outcome(public, expected, submission)
    assert score_with_event_as_action["score"] == 0.9


def test_base_task_score_is_mode_neutral_and_unaffected_by_async_domain():
    from async_rbench.evaluation.scoring import score_base_task, score_event_replanning

    # BTS consumes only base_task semantic checks; a failing async replanning
    # check must not drag down the mode-neutral task score.
    results = [
        {"id": "task.a", "score_domain": "base_task", "passed": True},
        {"id": "task.b", "score_domain": "base_task", "passed": True},
        {"id": "event.a", "score_domain": "async_replanning", "event_id": "evt.a", "passed": False},
    ]
    assert score_base_task(results) == 1.0

    # A per-event DRS is scored independently of the base task outcome: the
    # base-task checks passing does not manufacture event coverage that the
    # trajectory did not produce.
    contract = {
        "event_id": "evt.a", "expected_disposition": "revise",
        "required_changes": ["affected"], "required_preservation": ["prior"],
        "forbidden_changes": ["stable"], "closure_checks": ["event.a"],
    }
    before = {"affected": "provisional", "prior": "same", "stable": "same"}
    after = {"affected": "provisional", "prior": "same", "stable": "same"}
    score = score_event_replanning(contract, before, after, results)
    assert score.component_scores["required_effect_coverage"] == 0.0


def test_react_outcome_uses_variable_required_action_points():
    public = {
        "case_id": "c2",
        "source": {"instruction": "task"},
        "causal_record": {
            "prior_work": [{"id": "p1"}],
            "affected_work": [{"id": "a1"}, {"id": "a2"}, {"id": "a3"}],
            "independent_event": {"id": "e1"},
        },
    }
    expected = {
        "event_id": "e1",
        "prior_work_ids": ["p1"],
        "affected_work_ids": ["a1", "a2", "a3"],
        "superseded_work_ids": ["x1"],
    }
    env = BlockingReActEnvironment(public, expected)
    env.call("query_authoritative_evidence")
    for action_id in expected["affected_work_ids"]:
        env.call("execute_action", {"action_id": action_id})
    env.call("inspect_final_state")
    env.call("finish", {"summary": "done"})
    score = score_react_task_outcome(public, expected, env.state)
    assert score["score"] == 1.0
    assert score["test_point_count"] == 7
