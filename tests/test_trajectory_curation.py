from __future__ import annotations

import json
from pathlib import Path

from async_rbench.trajectory_curation import (
    decision_review_template, initialise_curation, read_jsonl, select_trajectories,
    select_authoritative_trajectory_batch,
    select_authoritative_batch, trajectory_review_record, validate_review,
)


def test_read_jsonl_preserves_unicode_line_separators_inside_strings(tmp_path: Path) -> None:
    source = tmp_path / "browser-trajectory.jsonl"
    rows = [
        {"id": "a", "content": "before\u2028after"},
        {"id": "b", "content": "left\u2029right"},
    ]
    source.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    assert read_jsonl(source) == rows


def _row(task: str, suffix: str, *, solved: bool, agent: str, steps: int) -> dict:
    return {
        "traj_id": f"{task}-{suffix}", "task_name": task, "solved": solved,
        "agent": agent, "model": f"model-{agent}", "step_count": steps,
        "stage_count": 3, "artifact_path": f"bench_artifacts/full/{task}-{suffix}.tar.zst",
    }


def test_selection_prefers_success_failure_and_agent_diversity() -> None:
    rows = [
        _row("task-a", "one", solved=True, agent="a", steps=20),
        _row("task-a", "two", solved=False, agent="a", steps=30),
        _row("task-a", "three", solved=False, agent="b", steps=10),
        _row("task-a", "four", solved=True, agent="c", steps=8),
    ]
    selected, coverage = select_trajectories(rows, ["task-a"], per_task=3)
    assert coverage == {"task-a": 4}
    assert len(selected) == 3
    assert {row["solved"] for row in selected} == {True, False}
    assert len({row["agent"] for row in selected}) >= 2


def test_authoritative_batch_is_unique_and_respects_source_quotas() -> None:
    rows = []
    for index in range(8):
        row = _row(
            f"tb-task-{index}", str(index), solved=index % 2 == 0,
            agent=f"agent-{index % 2}", steps=20 + index,
        )
        row.update({"source_relpath": f"terminus2/run-{index}", "category": "terminal"})
        rows.append(row)
    for index in range(7):
        row = _row(
            f"swe-task-{index}", str(index), solved=index % 2 == 0,
            agent=f"agent-{index % 3}", steps=30 + index,
        )
        row.update({"source_relpath": f"swe_raw/run-{index}", "category": "coding"})
        rows.append(row)
    selected, report = select_authoritative_batch(
        rows, source_quotas={"terminal_bench": 6, "swe_bench": 5},
    )
    assert len(selected) == 11
    assert report["unique_task_count"] == 11
    assert report["sources"]["terminal_bench"]["selected"] == 6
    assert report["sources"]["swe_bench"]["selected"] == 5
    assert {row["benchmark"] for row in selected} == {"Terminal-Bench", "SWE-bench"}


def test_expanded_authoritative_batch_retains_seeds_and_bounds_task_repeats() -> None:
    rows = []
    for task_index in range(3):
        for run_index in range(5):
            row = _row(
                f"tb-task-{task_index}", str(run_index), solved=run_index % 2 == 0,
                agent=f"agent-{run_index % 3}", steps=20 + run_index,
            )
            row.update({"source_relpath": f"terminus2/{task_index}/{run_index}", "category": "terminal"})
            rows.append(row)
    for task_index in range(2):
        for run_index in range(3):
            row = _row(
                f"swe-task-{task_index}", str(run_index), solved=run_index % 2 == 0,
                agent=f"agent-{run_index % 2}", steps=30 + run_index,
            )
            row.update({"source_relpath": f"swe_raw/{task_index}/{run_index}", "category": "coding"})
            rows.append(row)
    seed_ids = {rows[0]["traj_id"], rows[-1]["traj_id"]}
    selected, report = select_authoritative_trajectory_batch(
        rows, source_quotas={"terminal_bench": 9, "swe_bench": 4},
        seed_ids=seed_ids, max_per_task=3,
    )
    ids = {row["traj_id"] for row in selected}
    assert len(selected) == 13 and len(ids) == 13
    assert seed_ids <= ids
    counts: dict[str, int] = {}
    for row in selected:
        counts[row["task_name"]] = counts.get(row["task_name"], 0) + 1
    assert max(counts.values()) <= 3
    assert report["seed_retained"] == 2
    assert report["unique_task_count"] == 5


def test_fixed_choice_validation_requires_evidence_for_acceptance() -> None:
    record = trajectory_review_record(_row("task-a", "one", solved=True, agent="a", steps=20))
    review = record["human_review"]
    review.update({
        "review_decision": "accept", "task_match": "yes", "version_match": "exact",
        "trajectory_quality": "usable", "failure_attribution": "not_failure",
        "replanning_evidence": "direct", "research_events": ["late_authoritative_result"],
        "recommended_uses": ["positive_pattern"],
    })
    assert validate_review(record, "trajectory") == [
        "accepted trajectory review requires evidence_step_ids"
    ]
    review["evidence_step_ids"] = [4, 7]
    assert validate_review(record, "trajectory") == []


def test_decision_acceptance_requires_async_replanning_evidence() -> None:
    record = decision_review_template()
    review = record["human_review"]
    review.update({
        "benchmark_eligible": "accept", "trigger_can_be_async_result": "yes",
        "arrival_order_matters": "yes",
        "plan_change_required": "yes", "affected_scope": "local_branch",
        "semantic_consequence_observable": "yes", "control_consequence_observable": "yes",
        "prompt_leakage_risk": "no", "capability_target": "async_dynamic_replanning",
        "relevance_tier": "direct", "topology_roles": ["downstream_consumer"],
        "evidence_step_ids": [8, 9],
    })
    assert validate_review(record, "decision") == []


def test_initialise_curation_writes_review_bundle(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    task = root / "upstream" / "terminal-bench" / "original-tasks-locked" / "task-a"
    task.mkdir(parents=True)
    (task / "task.yaml").write_text("instruction: test\n", encoding="utf-8")
    manifest = tmp_path / "manifest.jsonl"
    rows = [
        _row("task-a", "one", solved=True, agent="a", steps=20),
        _row("task-a", "two", solved=False, agent="b", steps=22),
    ]
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    output = tmp_path / "curation"
    summary = initialise_curation(
        root=root, manifest=str(manifest), output=output, per_task=2,
    )
    assert summary["selected_trajectory_count"] == 2
    assert summary["selected_with_artifact_count"] == 2
    assert (output / "trajectory_reviews.jsonl").is_file()
    html_text = (output / "trajectory_review.html").read_text(encoding="utf-8")
    assert "<select" in html_text and "type=\"checkbox\"" in html_text
