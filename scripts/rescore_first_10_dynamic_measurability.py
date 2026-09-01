#!/usr/bin/env python3
"""Offline diagnostic re-score of the frozen first-10 async traces under V9.1."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from async_rbench.evaluation.protocol import load_trace
from async_rbench.evaluation.scoring import score_trace
from async_rbench.evaluation.version import EVALUATION_CONTRACT_VERSION
from async_rbench.spec import load_case, resolve_case_instance


ROOT = Path(__file__).resolve().parents[1]
MODELS = ("sol", "terra", "luna")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "artifacts/first-10-model-eval/final-20260831",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/dynamic-measurability-fix/historical-rescore-v9.1",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    summaries: dict[str, Any] = {}
    for model in MODELS:
        rows: list[dict[str, Any]] = []
        for trace_path in sorted((args.source / model / "runs").glob("*-async-*/trace.jsonl")):
            old_score = _load(trace_path.with_name("score.json"))
            case_id = str(old_score["case_id"])
            instance_id = str(old_score["instance_id"])
            instance = resolve_case_instance(ROOT, case_id, instance_id)
            case_spec = load_case(instance.contract_path).raw
            semantic = _load(instance.case_dir / "task/tests/semantic_checks.json")
            control = _load(instance.case_dir / "task/tests/control_flow_checks.json")
            rescored = score_trace(
                load_trace(trace_path), case_spec, "async",
                semantic_registry=semantic,
                control_flow_checks=list(control.get("checks") or []),
                event_contracts=list(control.get("event_contracts") or []),
            )
            rescored.update({
                "episode_id": old_score["episode_id"],
                "case_id": case_id,
                "instance_id": instance_id,
                "execution_mode": "async",
                "requested_model": old_score.get("requested_model"),
                "resolved_model": old_score.get("resolved_model"),
                "evaluation_contract_version": EVALUATION_CONTRACT_VERSION,
                "offline_rescore": True,
                "historical_source_score_status": old_score.get("score_status"),
                "historical_source_case_sha256": old_score.get("case_sha256"),
                "score_status": (
                    "scored"
                    if rescored.get("scenario_constructed") is True
                    and rescored.get("semantic_task_score") is not None
                    and rescored.get("dynamic_control_score") is not None
                    else "unscored"
                ),
            })
            output_dir = args.output / model / rescored["episode_id"]
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "score.json").write_text(
                json.dumps(rescored, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            rows.append({
                "case_id": case_id,
                "old_status": old_score.get("score_status"),
                "new_status": rescored["score_status"],
                "semantic_task_score": rescored.get("semantic_task_score"),
                "dynamic_control_score": rescored.get("dynamic_control_score"),
                "dt_score": rescored.get("dt_score"),
                "scenario_constructed": rescored.get("scenario_constructed"),
                "scenario_exposure_complete": rescored.get("scenario_exposure_complete"),
                "dynamic_scenario_qualified": rescored.get("dynamic_scenario_qualified"),
                "dynamic_opportunity_complete": rescored.get("dynamic_opportunity_complete"),
                "dynamic_event_exposure": rescored.get("dynamic_event_exposure"),
                "dynamic_opportunity_errors": rescored.get("dynamic_opportunity_errors"),
            })
        exposure_counts = Counter(
            status
            for row in rows
            for status in (row.get("dynamic_event_exposure") or {}).values()
        )
        summaries[model] = {
            "episode_count": len(rows),
            "old_scored_count": sum(row["old_status"] == "scored" for row in rows),
            "new_scored_count": sum(row["new_status"] == "scored" for row in rows),
            "dynamic_denominator_count": sum(
                row["dynamic_control_score"] is not None for row in rows
            ),
            "mean_dynamic_control_score": _mean([
                float(row["dynamic_control_score"])
                for row in rows if row["dynamic_control_score"] is not None
            ]),
            "mean_dt_score": _mean([
                float(row["dt_score"]) for row in rows if row["dt_score"] is not None
            ]),
            "opportunity_complete_count": sum(
                row["dynamic_opportunity_complete"] is True for row in rows
            ),
            "event_exposure_counts": dict(sorted(exposure_counts.items())),
            "rows": rows,
        }
    report = {
        "report_version": 1,
        "evaluation_contract_version": EVALUATION_CONTRACT_VERSION,
        "source": str(args.source),
        "warning": (
            "Diagnostic only: traces were generated with the frozen V9.0 case bundles. "
            "This re-score proves denominator semantics but does not replace a fresh V9.1 run."
        ),
        "models": summaries,
    }
    (args.output / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        model: {
            key: value for key, value in summary.items() if key != "rows"
        }
        for model, summary in summaries.items()
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
