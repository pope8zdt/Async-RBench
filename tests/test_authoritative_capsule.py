from __future__ import annotations

import json
from pathlib import Path

from async_rbench.authoritative_capsule import oracle_submission, score_submission


def _capsule(tmp_path: Path) -> Path:
    case_dir = tmp_path / "case"
    (case_dir / "private").mkdir(parents=True)
    (case_dir / "case.json").write_text(json.dumps({
        "case_id": "example",
        "source": {"source_id": "source-1", "instruction_sha256": "a" * 64},
        "scenarios": {
            "linear": {"event_release_tick": 0},
            "async": {"event_release_tick": 2},
        },
    }), encoding="utf-8")
    (case_dir / "private/expected.json").write_text(json.dumps({
        "event_id": "event-1",
        "prior_work_ids": ["prior-1"],
        "affected_work_ids": ["affected-1"],
        "superseded_work_ids": ["provisional:affected-1"],
    }), encoding="utf-8")
    return case_dir


def test_oracle_scores_every_point_in_both_modes(tmp_path: Path) -> None:
    case_dir = _capsule(tmp_path)
    for mode in ("linear", "async"):
        result = score_submission(case_dir, oracle_submission(case_dir, mode), mode)
        assert result["score"] == 1.0
        assert result["scored_point_count"] == 8
        assert result["unscored_point_count"] == 0
        assert all(result["checks"].values())


def test_async_rejects_early_intake_and_stale_final_action(tmp_path: Path) -> None:
    case_dir = _capsule(tmp_path)
    submission = oracle_submission(case_dir, "async")
    submission["event_intake"]["sequence"] = 1
    submission["final_action_ids"].append("provisional:affected-1")
    result = score_submission(case_dir, submission, "async")
    assert not result["checks"]["result_intake"]
    assert not result["checks"]["stale_rejection"]
    assert result["score"] < 1.0
