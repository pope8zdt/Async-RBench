"""Audit paired model pilot completeness and point-level score differences."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.trajectory_curation import read_jsonl


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.experiment).resolve()
    sample = json.loads((root / "sample_manifest.json").read_text(encoding="utf-8"))
    episodes = read_jsonl(root / "episodes.jsonl")
    models = ("gpt-5.4-2026-03-05", "deepseek-v4-flash")
    modes = ("linear", "async")
    expected = {
        (case["case_id"], model, mode)
        for case in sample["cases"] for model in models for mode in modes
    }
    actual = {(row["case_id"], row["model"], row["mode"]) for row in episodes}
    errors = []
    if len(sample["cases"]) != 5:
        errors.append("sample must contain five cases")
    if actual != expected:
        errors.append(f"episode key mismatch: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")
    if any(row["status"] != "scored" for row in episodes):
        errors.append("one or more episodes are not scored")
    if any(int(row["unscored_point_count"]) != 0 for row in episodes):
        errors.append("one or more episodes contain unscored points")
    lookup = {(row["case_id"], row["model"], row["mode"]): row for row in episodes}
    paired = []
    point_failures = {model: {mode: Counter() for mode in modes} for model in models}
    for case in sample["cases"]:
        case_id = case["case_id"]
        for model in models:
            mode_scores = {}
            failed = {}
            for mode in modes:
                row = lookup[(case_id, model, mode)]
                score_path = root / "episodes" / model / case_id / mode / "score.json"
                score = json.loads(score_path.read_text(encoding="utf-8"))
                mode_scores[mode] = float(score["score"])
                failed[mode] = sorted(key for key, passed in score["checks"].items() if not passed)
                point_failures[model][mode].update(failed[mode])
                if float(row["score"]) != float(score["score"]):
                    errors.append(f"score mismatch for {case_id}/{model}/{mode}")
            paired.append({
                "case_id": case_id, "benchmark": case["benchmark"], "model": model,
                "linear_score": mode_scores["linear"], "async_score": mode_scores["async"],
                "async_minus_linear": round(mode_scores["async"] - mode_scores["linear"], 6),
                "linear_failed_points": failed["linear"],
                "async_failed_points": failed["async"],
            })
    aggregates = {}
    for model in models:
        rows = [row for row in paired if row["model"] == model]
        aggregates[model] = {
            "linear_mean": round(sum(row["linear_score"] for row in rows) / len(rows), 6),
            "async_mean": round(sum(row["async_score"] for row in rows) / len(rows), 6),
            "mean_delta": round(sum(row["async_minus_linear"] for row in rows) / len(rows), 6),
            "async_lower_case_count": sum(row["async_minus_linear"] < 0 for row in rows),
            "equal_case_count": sum(row["async_minus_linear"] == 0 for row in rows),
            "async_higher_case_count": sum(row["async_minus_linear"] > 0 for row in rows),
            "point_failure_counts": {
                mode: dict(sorted(point_failures[model][mode].items())) for mode in modes
            },
        }
    report = {
        "schema_version": "capsule-model-pilot-audit-1",
        "status": "passed" if not errors else "failed",
        "sample_seed": sample["seed"],
        "sample_size": len(sample["cases"]),
        "episode_count": len(episodes),
        "scored_episode_count": sum(row["status"] == "scored" for row in episodes),
        "unscored_or_failed_count": sum(
            row["status"] != "scored" or int(row["unscored_point_count"]) != 0 for row in episodes
        ),
        "execution_protocol": {
            "gpt-5.4-2026-03-05": {
                "resolved_model": "gpt-5.4", "reasoning_effort": "high",
                "max_completion_tokens": 16384, "response_format": "json_object",
            },
            "deepseek-v4-flash": {
                "resolved_model": "deepseek-v4-flash", "thinking": "disabled",
                "max_tokens": 8192, "response_format": "json_object",
            },
            "linear": "single request with authoritative event already available",
            "async": "two requests: pre-event checkpoint followed by authoritative event interruption",
        },
        "aggregates": aggregates,
        "paired_results": paired,
        "errors": errors,
    }
    output = Path(args.output).resolve()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
