from __future__ import annotations

from pathlib import Path

from scripts.build_human_annotation_batches import (
    _assign_annotators,
    _blind_run, _blind_task,
    _render_workspace,
)


def _source(review_id: str, task: str) -> dict:
    return {
        "review_id": review_id,
        "task_name": task,
        "benchmark": "ExampleBench",
        "source_kind": "real_model_execution_trace",
        "source_agent": "secret-agent",
        "source_model": "secret-model",
        "instruction": "Perform the source task.",
        "normalized_step_count": 4,
        "tail": [{"step_id": 4, "kind": "observation", "content": "done"}],
        "codex_screen": {
            "decision": "promote_to_human",
            "rationale": "secret screening rationale",
            "evidence_step_ids": [4],
        },
    }


def _task(name: str) -> dict:
    return {
        "task_name": name,
        "benchmark": "ExampleBench",
        "run_count": 1,
        "representative_runs": [],
        "human_review": {
            "answers": {}, "computed_decision": "pending",
        },
    }


def test_blind_run_removes_identity_and_screening_fields() -> None:
    row = _blind_run(_source("raw-id", "task-a"))
    assert row["review_id"].startswith("SRC-")
    assert row["source_kind"] == "execution record"
    for forbidden in ("source_agent", "source_model", "codex_screen", "rationale"):
        assert forbidden not in row
    assert row["recommendation"]["source"] == "codex_initial_screen"
    assert row["recommendation"]["answers"]["trigger_is_independent_result"] == "yes"
    assert row["human_review"]["answers"] == row["recommendation"]["answers"]
    assert row["human_review"]["confirmed"] is False


def test_three_way_assignment_keeps_primary_tasks_disjoint_and_calibration_shared() -> None:
    tasks = [_blind_task(_task(f"task-{index}")) for index in range(9)]
    runs = [_blind_run(_source(f"run-{index}", f"task-{index}")) for index in range(9)]
    assignments, calibration = _assign_annotators(tasks, runs, 3, 2)
    assert len(assignments) == 3
    assert len(calibration) == 2
    primary_sets = [
        {row["task_name"] for row in item["tasks"] if row["assignment_role"] == "primary"}
        for item in assignments
    ]
    assert not (primary_sets[0] & primary_sets[1])
    assert not (primary_sets[0] & primary_sets[2])
    assert not (primary_sets[1] & primary_sets[2])
    for item in assignments:
        assert {row["task_name"] for row in item["tasks"] if row["assignment_role"] == "calibration"} == set(calibration)


def test_workspace_has_recommended_defaults_without_raw_screening(tmp_path: Path) -> None:
    run = _blind_run(_source("raw-id", "task-a"))
    run.update({"annotator_id": "annotator-1", "assignment_role": "primary", "annotation_batch_id": "run-batch-001"})
    task = _blind_task(_task("task-a"))
    task.update({"annotator_id": "annotator-1", "assignment_role": "primary", "annotation_batch_id": "task-batch-001"})
    output = tmp_path / "review.html"
    _render_workspace([task], [run], output, "annotator-1")
    html = output.read_text(encoding="utf-8")
    for forbidden in (
        "Codex hypothesis", "source_agent", "source_model", "codex_screen",
        "secret-agent", "secret-model", "secret screening rationale",
    ):
        assert forbidden not in html
    assert "annotator-1.task-reviews.jsonl" in html
    assert "async-rbench-assisted-v1-annotator-1" in html
    assert "async-rbench-blind-v1-annotator-1" in html
    assert "restoreReview" in html
    assert "初筛推荐" not in html
    assert "recommendation-note" not in html.split("<script>", 1)[1]
    assert "确认并下一条" in html
    assert '"trigger_is_independent_result": "yes"' in html
