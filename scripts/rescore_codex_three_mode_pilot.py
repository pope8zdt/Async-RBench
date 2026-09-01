"""Offline audit/rescore for the Codex three-mode pilot without rerunning models."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.authoritative_capsule import load_capsule, score_submission  # noqa: E402
from async_rbench.react_baseline import score_react_state  # noqa: E402
from async_rbench.shared_task_scoring import (  # noqa: E402
    score_capsule_task_outcome,
    score_react_task_outcome,
)
from async_rbench.trajectory_curation import read_jsonl, write_jsonl  # noqa: E402
from scripts.run_codex_three_mode_pilot import MODES, _report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--production",
        default="artifacts/authoritative-case-300/04-case-production",
    )
    parser.add_argument(
        "--run",
        default="artifacts/authoritative-case-300/08-codex-5.6-sol-three-mode-10",
    )
    args = parser.parse_args()
    production = Path(args.production).resolve()
    run_dir = Path(args.run).resolve()
    sample = json.loads((run_dir / "sample_manifest.json").read_text(encoding="utf-8"))
    original = {
        (str(row["case_id"]), str(row["mode"])): row
        for row in read_jsonl(run_dir / "episodes.jsonl")
    }
    rescored: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    integrity_issues: list[str] = []

    for case in sample["cases"]:
        case_id = str(case["case_id"])
        case_dir = production / str(case["path"])
        public, expected = load_capsule(case_dir)
        for mode in MODES:
            episode_dir = run_dir / "episodes" / case_id / mode
            row = dict(original[(case_id, mode)])
            turns = json.loads((episode_dir / "turns.json").read_text(encoding="utf-8"))
            thread_ids = {str(turn.get("thread_id") or "") for turn in turns}
            if len(turns) != int(row.get("request_count") or 0):
                integrity_issues.append(f"{case_id}/{mode}: request_count mismatch")
            if len(thread_ids) != 1 or "" in thread_ids:
                integrity_issues.append(f"{case_id}/{mode}: turns do not share one valid Codex thread")
            if mode == "linear" and len(turns) != 1:
                integrity_issues.append(f"{case_id}/{mode}: expected exactly one turn")
            if mode == "async" and len(turns) != 2:
                integrity_issues.append(f"{case_id}/{mode}: expected pre-event and post-event turns")
            if str(row.get("model_requested")) != "gpt-5.6-sol":
                integrity_issues.append(f"{case_id}/{mode}: requested model mismatch")
            if mode == "react":
                state = json.loads((episode_dir / "state.json").read_text(encoding="utf-8"))
                task_score = score_react_task_outcome(public, expected, state)
                diagnostic = score_react_state(public, expected, state)
            else:
                submission = json.loads((episode_dir / "submission.json").read_text(encoding="utf-8"))
                if str(submission.get("case_id")) != case_id:
                    integrity_issues.append(f"{case_id}/{mode}: submission case_id mismatch")
                task_score = score_capsule_task_outcome(public, expected, submission)
                diagnostic = score_submission(case_dir, submission, mode)
            previous_task = row.get("task_score")
            previous_diagnostic = row.get("process_diagnostic_score")
            row.update({
                "task_score": task_score["score"],
                "task_test_point_count": task_score["test_point_count"],
                "task_passed_point_count": task_score["passed_point_count"],
                "task_unscored_point_count": task_score["unscored_point_count"],
                "process_diagnostic_score": diagnostic["score"],
                "rescore_version": "prior-work-final-state-equivalence-1",
            })
            (episode_dir / "task_score_rescored.json").write_text(
                json.dumps(task_score, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            (episode_dir / "process_diagnostic_rescored.json").write_text(
                json.dumps(diagnostic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            if previous_task != row["task_score"] or previous_diagnostic != row["process_diagnostic_score"]:
                changes.append({
                    "case_id": case_id,
                    "mode": mode,
                    "task_score_before": previous_task,
                    "task_score_after": row["task_score"],
                    "diagnostic_before": previous_diagnostic,
                    "diagnostic_after": row["process_diagnostic_score"],
                    "classification": "benchmark_scorer_semantic-ambiguity correction",
                })
            rescored.append(row)

    rescored.sort(key=lambda row: (str(row["case_id"]), MODES.index(str(row["mode"]))))
    write_jsonl(run_dir / "episodes_rescored.jsonl", rescored)
    run_config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
    report = _report(
        rescored,
        sample,
        SimpleNamespace(reasoning_effort=run_config["reasoning_effort"]),
    )
    report["schema_version"] = "codex-three-mode-pilot-rescored-1"
    report["rescore_policy"] = {
        "reason": (
            "final_action_ids was ambiguous between delta actions and the final committed action state; "
            "preserved prior work is accepted in either representation"
        ),
        "event_id_in_final_action_ids": (
            "still rejected because an observation is not an executed action"
        ),
        "raw_model_outputs_modified": False,
    }
    (run_dir / "report_rescored.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    audit = {
        "episode_count": len(rescored),
        "raw_output_mutation_count": 0,
        "score_change_count": len(changes),
        "changes": changes,
        "integrity_issues": integrity_issues,
        "all_episodes_scored": all(row.get("task_score") is not None for row in rescored),
        "all_unscored_counts_zero": all(
            int(row.get("task_unscored_point_count") or 0) == 0 for row in rescored
        ),
    }
    (run_dir / "rescore_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"report": report, "audit": audit}, ensure_ascii=False, indent=2))
    return 0 if not integrity_issues and report["all_modes_full_coverage"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
