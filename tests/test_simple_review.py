from __future__ import annotations

import json
from pathlib import Path

import pytest

from async_rbench.simple_review import (
    build_simple_review_batch, collect_uncertain_records, render_simple_review_html, route_simple_review,
    validate_simple_review_record,
)


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples/simple-review/secure-release-demo.json"


def test_demo_review_record_is_valid() -> None:
    record = json.loads(DEMO.read_text(encoding="utf-8"))
    assert validate_simple_review_record(record) == []


def test_choice_only_routing_accepts_the_required_pattern() -> None:
    result = route_simple_review({
        "late_after_work_started": "yes",
        "requires_plan_change": "yes",
        "evidence_is_faithful": "yes",
    })
    assert result == {
        "route": "candidate_confirmed", "uncertainty_questions": [],
        "evidence_problem_parts": [], "reason_codes": [],
    }


def test_any_uncertain_answer_routes_to_the_uncertain_pool() -> None:
    result = route_simple_review({
        "late_after_work_started": "yes",
        "requires_plan_change": "uncertain",
        "evidence_is_faithful": "yes",
    })
    assert result["route"] == "uncertain_pool"
    assert result["uncertainty_questions"] == ["requires_plan_change"]


def test_non_late_information_gets_a_specific_route() -> None:
    result = route_simple_review({
        "late_after_work_started": "no",
        "requires_plan_change": "yes",
        "evidence_is_faithful": "yes",
    })
    assert result["route"] == "not_late_event"
    assert result["reason_codes"] == ["not_late_event"]


def test_no_replanning_need_gets_a_specific_route() -> None:
    result = route_simple_review({
        "late_after_work_started": "yes",
        "requires_plan_change": "no",
        "evidence_is_faithful": "yes",
    })
    assert result["route"] == "no_replanning_need"


def test_non_independent_observation_is_not_an_async_candidate() -> None:
    result = route_simple_review({
        "independent_async_source": "no",
        "late_after_work_started": "yes",
        "requires_plan_change": "yes",
        "evidence_is_faithful": "yes",
    })
    assert result["route"] == "ordinary_sequential_observation"
    assert result["reason_codes"] == ["not_independent_async_source"]


def test_evidence_mismatch_returns_to_extraction() -> None:
    result = route_simple_review({
        "late_after_work_started": "yes",
        "requires_plan_change": "yes",
        "evidence_is_faithful": "no",
    }, ["late_information"])
    assert result["route"] == "needs_reextraction"
    assert result["reason_codes"] == ["evidence_mismatch:late_information"]


def test_evidence_mismatch_requires_problem_location() -> None:
    with pytest.raises(ValueError, match="evidence_problem_parts"):
        route_simple_review({
            "late_after_work_started": "yes",
            "requires_plan_change": "yes",
            "evidence_is_faithful": "no",
        })


def test_incomplete_answers_fail_closed() -> None:
    with pytest.raises(ValueError, match="incomplete or invalid"):
        route_simple_review({"late_after_work_started": "yes"})


def test_rendered_review_is_neutral_and_uses_uncertain_wording(tmp_path: Path) -> None:
    record = json.loads(DEMO.read_text(encoding="utf-8"))
    output = tmp_path / "review.html"
    render_simple_review_html([record], output)
    html = output.read_text(encoding="utf-8")
    assert "AI" not in html
    assert "看不懂" not in html
    assert "扩展上下文复核" in html
    assert "关键轨迹描述" not in html  # the real page uses the shorter neutral heading
    assert "关键轨迹复核" in html
    assert "可见后果" not in html
    assert "0 / 3" in html
    assert "目标 60 秒" not in html
    assert 'id="reviewer-id"' in html
    assert "reviewer_id:" in html
    assert "审核页面不显示通过或淘汰结论" in html


def test_build_simple_review_batch_blinds_source_identity() -> None:
    normalized = [{
        "review_id": "openhands-OpenAI__GPT-5-task-source-id",
        "task_name": "task-one",
        "source_agent": "OpenHands",
        "source_model": "OpenAI GPT-5",
        "result": {"instruction": "Complete the benchmark task."},
        "steps": [
            {"step_id": 1, "kind": "action", "role": "assistant", "command": "run work"},
            {"step_id": 2, "kind": "observation", "role": "tool", "content": "failed check"},
            {"step_id": 3, "kind": "action", "role": "assistant", "command": "retry work"},
        ],
    }]
    decisions = [{
        "decision_id": "source:d1",
        "trajectory_review_id": "openhands-OpenAI__GPT-5-task-source-id",
        "agent_proposal": {
            "event_type": "reverification", "trigger_step_ids": [2],
            "precondition_step_ids": [], "response_step_ids": [3],
        },
    }]
    records, mapping = build_simple_review_batch(normalized, decisions)
    assert len(records) == len(mapping) == 1
    assert records[0]["schema_version"] == "3"
    assert records[0]["review_id"] == "calibration-b001-001"
    assert "OpenHands" not in json.dumps(records[0])
    assert "GPT-5" not in json.dumps(records[0])
    assert mapping[0]["source_review_id"].startswith("openhands-")
    assert validate_simple_review_record(records[0]) == []


def test_uncertain_annotation_builds_blind_expanded_second_round() -> None:
    record = json.loads(DEMO.read_text(encoding="utf-8"))
    annotation = {
        "review_id": record["review_id"],
        "answers": {
            "late_after_work_started": "yes",
            "requires_plan_change": "yes",
            "evidence_is_faithful": "uncertain",
        },
        "route": "uncertain_pool",
    }
    queue = collect_uncertain_records([record], [annotation])
    assert len(queue) == 1
    assert queue[0]["review_round"] == 2
    assert queue[0]["rereview"] == {
        "blind": True,
        "show_expanded_context": True,
        "source_annotation_retained_separately": True,
    }
    assert "answers" not in queue[0]


def test_uncertain_collection_rejects_tampered_route() -> None:
    record = json.loads(DEMO.read_text(encoding="utf-8"))
    annotation = {
        "review_id": record["review_id"],
        "answers": {
            "late_after_work_started": "yes",
            "requires_plan_change": "yes",
            "evidence_is_faithful": "uncertain",
        },
        "route": "candidate_confirmed",
    }
    with pytest.raises(ValueError, match="route does not match"):
        collect_uncertain_records([record], [annotation])
