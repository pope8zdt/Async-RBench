from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from async_rbench.track_b import cli as track_b_cli


VALIDATION_INSTANCES = (
    "mab-dependency-unblock-8b943d725b::seed-1",
    "mab-late-test-evidence-4c6c77884e::seed-1",
)


def run_validation(root: Path, output: Path) -> dict[str, Any]:
    root = root.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = root / "configs" / "track-b" / "deterministic-validation.yaml"
    manifest = output / "manifest.json"
    runs = output / "runs"

    make_result = track_b_cli.main([
        "make-manifest",
        "--instances", *VALIDATION_INSTANCES,
        "--model", "track-b-deterministic",
        "--repetitions", "1",
        "--seed", "2026",
        "--output", str(manifest),
    ])
    if make_result != 0:
        raise RuntimeError(f"Track B validation manifest failed with exit {make_result}")

    run_result = track_b_cli.main([
        "run",
        "--config", str(config),
        "--manifest", str(manifest),
        "--output", str(runs),
        "--no-container",
    ])
    if run_result != 0:
        raise RuntimeError(f"Track B validation run failed with exit {run_result}")

    conformance_path = runs / ".conformance" / "conformance.json"
    conformance = json.loads(conformance_path.read_text(encoding="utf-8"))
    score_paths = sorted(runs.glob("*/score.json"))
    scores = [json.loads(path.read_text(encoding="utf-8")) for path in score_paths]
    report = {
        "validation_kind": "engineering_acceptance",
        "case_count": len(VALIDATION_INSTANCES),
        "episode_count": len(scores),
        "instances": list(VALIDATION_INSTANCES),
        "execution_modes": ["linear", "async"],
        "framework": "deterministic",
        "model_calls": 0,
        "docker_started": False,
        "conformance_passed": bool(conformance.get("conformance_passed")),
        "score_files": [str(path.relative_to(output)).replace("\\", "/") for path in score_paths],
        "score_statuses": [score.get("score_status") for score in scores],
        "leaderboard_eligible": False,
        "publication_note": (
            "Validates Track B integration mechanics only; it is not a model-quality "
            "result and is not eligible for any leaderboard."
        ),
    }
    (output / "track-b-validation.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run safe two-case Track B validation")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    report = run_validation(root, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["conformance_passed"] and report["episode_count"] == 4 else 1


if __name__ == "__main__":
    raise SystemExit(main())
