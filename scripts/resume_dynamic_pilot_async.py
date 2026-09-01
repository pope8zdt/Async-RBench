from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from async_rbench.evaluation.runner import EpisodeConfig, run_episode
from async_rbench.spec import load_case


def _result_row(score: dict[str, Any]) -> dict[str, Any]:
    semantic_results = score.get("semantic_check_results") or []
    dynamic_counts = score.get("control_flow_check_counts") or {}
    return {
        "episode_id": score.get("episode_id"),
        "execution_mode": score.get("execution_mode"),
        "score_status": score.get("score_status"),
        "semantic_task_score": score.get("semantic_task_score"),
        "dynamic_control_score": score.get("dynamic_control_score"),
        "dt_score": score.get("dt_score"),
        "dynamic_dimension_scores": score.get("dynamic_dimension_scores"),
        "semantic_points": len(semantic_results),
        "semantic_passed": sum(item.get("passed") is True for item in semantic_results),
        "dynamic_points_applicable": dynamic_counts.get("applicable"),
        "dynamic_points_passed": dynamic_counts.get("passed"),
        "scenario_constructed": score.get("scenario_constructed"),
        "scenario_exposed": score.get("scenario_exposure_complete"),
        "infrastructure_failures": score.get("infrastructure_failures"),
        "gateway_failure_count": score.get("gateway_failure_count"),
    }


async def _main(args: argparse.Namespace) -> int:
    batch = Path(args.batch).resolve()
    output = Path(args.output).resolve()
    config_path = Path(args.config).resolve()
    report = json.loads((batch / "batch-report.json").read_text(encoding="utf-8"))
    row = next(item for item in report["cases"] if item["pilot_id"] == args.pilot_id)
    case = load_case(Path(row["case_dir"]).resolve() / "public_case.yaml")
    model_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    model = str(model_config.get("main_model") or "unknown")
    pair_id = f"dynamic-pilot-{args.pilot_id}-{model}-{args.seed}"
    linear_id = f"{pair_id}-linear"
    async_id = f"{pair_id}-async"
    linear_score_path = output / "episodes" / linear_id / "score.json"
    if not linear_score_path.is_file():
        raise FileNotFoundError(f"completed linear score is missing: {linear_score_path}")
    async_output = output / "episodes" / async_id
    if async_output.exists():
        raise FileExistsError(f"async output already exists: {async_output}")
    adapter = [
        sys.executable,
        str(ROOT / "adapters" / "reference_scaffold_api.py"),
        "--config",
        str(config_path),
    ]
    async_score = await run_episode(
        ROOT,
        EpisodeConfig(
            episode_id=async_id,
            case_id=case.case_id,
            instance_id=args.pilot_id,
            execution_mode="async",
            guidance="incentive",
            agent_seed=args.seed,
            adapter_command=adapter,
            output_dir=async_output,
            repeat=0,
            counterfactual_pair_id=pair_id,
            timeout_sec=args.timeout,
            gateway_grace_sec=15,
            use_container=True,
            build_image=False,
            keep_container=False,
            progress=True,
            episode_index=2,
            episode_total=2,
            adapter_profile="reference_scaffold_api",
            runtime_mode="api_only",
            official_track=False,
            case_dir_override=Path(row["case_dir"]).resolve(),
        ),
    )
    linear_score = json.loads(linear_score_path.read_text(encoding="utf-8"))
    result = {
        "schema_version": "dynamic-pilot-pair-1",
        "pilot_id": args.pilot_id,
        "case_id": case.case_id,
        "model": model,
        "model_config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "status": "completed",
        "simulation_only": True,
        "official_track": False,
        "semantic_registry_points": row["semantic_points"],
        "dynamic_registry_points": row["dynamic_points"],
        "scores": [_result_row(linear_score), _result_row(async_score)],
        "resume_metadata": {
            "resumed_mode": "async",
            "reason": "original terminal session was interrupted after the linear score was finalized",
        },
    }
    (output / "pair-results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    parser.add_argument("--pilot-id", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=3600)
    raise SystemExit(asyncio.run(_main(parser.parse_args())))
