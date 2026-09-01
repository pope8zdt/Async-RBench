"""Recompute and audit a completed blocking-ReAct pilot."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.authoritative_capsule import load_capsule  # noqa: E402
from async_rbench.react_baseline import score_react_state  # noqa: E402
from async_rbench.trajectory_curation import read_jsonl  # noqa: E402


ALLOWED_TOOLS = {
    "inspect_current_state", "query_authoritative_evidence", "execute_action",
    "inspect_final_state", "finish",
}
COMPLETION_LANGUAGE = re.compile(
    r"\b(complete|completed|booked|scheduled|purchased|sent|added)\b", re.IGNORECASE,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", required=True)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    production = Path(args.production).resolve()
    run = Path(args.run).resolve()
    sample = json.loads((run / "sample_manifest.json").read_text(encoding="utf-8"))
    records = read_jsonl(run / "episodes.jsonl")
    path_by_case = {str(row["case_id"]): str(row["path"]) for row in sample["cases"]}
    errors: list[str] = []
    rows = []
    point_failures: dict[str, Counter[str]] = defaultdict(Counter)
    case_flags = []

    for case_id, relative in path_by_case.items():
        case_dir = production / relative
        public, expected = load_capsule(case_dir)
        prior_descriptions = [
            str(item.get("description") or "")
            for item in list((public.get("causal_record") or {}).get("prior_work") or [])
        ]
        affected = list((public.get("causal_record") or {}).get("affected_work") or [])
        flags = []
        if any(COMPLETION_LANGUAGE.search(value) for value in prior_descriptions):
            flags.append("prior_state_contains_task_completion_language")
        if any(str(item.get("function") or "").startswith(("delete_", "cancel_")) for item in affected):
            flags.append("required_destructive_action_depends_on_implicit_prior_object")
        case_flags.append({
            "case_id": case_id,
            "benchmark": public["source"].get("benchmark"),
            "interpretation_flags": flags,
        })

    for record in records:
        case_id = str(record["case_id"])
        model = str(record["model"])
        episode_dir = run / "episodes" / model / case_id
        state = json.loads((episode_dir / "state.json").read_text(encoding="utf-8"))
        stored = json.loads((episode_dir / "score.json").read_text(encoding="utf-8"))
        trace = read_jsonl(episode_dir / "react_trace.jsonl")
        public, expected = load_capsule(production / path_by_case[case_id])
        recomputed = score_react_state(public, expected, state)
        if recomputed != stored:
            errors.append(f"score recomputation mismatch: {model}/{case_id}")
        if record.get("status") != "scored" or not record.get("finished"):
            errors.append(f"episode not cleanly finished: {model}/{case_id}")
        if int(record.get("unscored_point_count") or 0) != 0:
            errors.append(f"unscored points: {model}/{case_id}")
        if int(record.get("parse_error_count") or 0) != 0:
            errors.append(f"parse errors: {model}/{case_id}")
        steps = [int(item.get("step") or 0) for item in trace]
        if steps != list(range(1, len(trace) + 1)):
            errors.append(f"non-contiguous blocking trace: {model}/{case_id}")
        unknown_tools = sorted({str(item.get("tool")) for item in trace} - ALLOWED_TOOLS)
        if unknown_tools:
            errors.append(f"non-ReAct tools {unknown_tools}: {model}/{case_id}")
        failed_points = [str(item["id"]) for item in stored["test_points"] if not item["passed"]]
        point_failures[model].update(failed_points)
        rows.append({
            "case_id": case_id,
            "benchmark": record.get("benchmark"),
            "model": model,
            "score": stored["score"],
            "passed_points": stored["passed_point_count"],
            "test_points": stored["test_point_count"],
            "failed_points": failed_points,
            "tool_steps": len(trace),
            "resolved_model": record.get("resolved_model"),
        })

    aggregates = {}
    for model in sorted({str(row["model"]) for row in rows}):
        model_rows = [row for row in rows if row["model"] == model]
        aggregates[model] = {
            "mean_score": round(sum(float(row["score"]) for row in model_rows) / len(model_rows), 6),
            "scored_case_count": len(model_rows),
            "point_failure_counts": dict(sorted(point_failures[model].items())),
        }
    report = {
        "schema_version": "react-baseline-pilot-audit-1",
        "status": "passed" if not errors else "failed",
        "episode_count": len(records),
        "scored_episode_count": sum(row.get("status") == "scored" for row in records),
        "unscored_or_failed_count": sum(
            row.get("status") != "scored" or int(row.get("unscored_point_count") or 0) > 0
            for row in records
        ),
        "blocking_trace_integrity": not errors,
        "aggregates": aggregates,
        "case_interpretation_flags": case_flags,
        "results": sorted(rows, key=lambda row: (row["model"], row["case_id"])),
        "errors": errors,
    }
    output = run / "audit_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

