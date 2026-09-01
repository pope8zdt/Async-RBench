"""Build a large, deterministic run-level authoritative trajectory batch."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.trajectory_curation import (  # noqa: E402
    AUTHORITATIVE_SOURCE_CATALOG,
    read_jsonl,
    render_review_html,
    select_authoritative_trajectory_batch,
    trajectory_review_record,
    write_jsonl,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--output", required=True)
    parser.add_argument("--terminal-bench", type=int, default=2100)
    parser.add_argument("--swe-bench", type=int, default=600)
    parser.add_argument("--max-per-task", type=int, default=11)
    args = parser.parse_args()
    manifest, seed_path = Path(args.manifest).resolve(), Path(args.seed).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows, seeds = read_jsonl(manifest), read_jsonl(seed_path)
    excluded_ids: set[str] = set()
    for path_text in args.exclude:
        for row in read_jsonl(Path(path_text).resolve()):
            excluded_ids.add(str(row.get("review_id") or row.get("traj_id") or ""))
    selected, report = select_authoritative_trajectory_batch(
        rows,
        source_quotas={"terminal_bench": args.terminal_bench, "swe_bench": args.swe_bench},
        seed_ids=(str(row.get("traj_id") or "") for row in seeds),
        excluded_ids=excluded_ids,
        max_per_task=args.max_per_task,
    )
    reviews = [trajectory_review_record(row) for row in selected]
    write_jsonl(output / "selected_manifest.jsonl", selected)
    write_jsonl(output / "trajectory_reviews.jsonl", reviews)
    render_review_html(reviews, output / "trajectory_review.html")
    task_counts = Counter(str(row.get("task_name") or "") for row in selected)
    report.update({
        "selection_level": "independent_execution_run",
        "duplicate_task_policy": "allowed_and_bounded",
        "manifest_path": str(manifest), "manifest_sha256": _sha256(manifest),
        "seed_path": str(seed_path), "seed_sha256": _sha256(seed_path),
        "excluded_ids": sorted(excluded_ids),
        "selected_agents": dict(sorted(Counter(str(row.get("agent") or "unknown") for row in selected).items())),
        "selected_models": dict(sorted(Counter(str(row.get("model") or "unknown") for row in selected).items())),
        "selected_outcomes": dict(sorted(Counter(
            "solved" if row.get("solved") is True else "unsolved" if row.get("solved") is False else "unknown"
            for row in selected
        ).items())),
        "task_repeat_histogram": dict(sorted(Counter(task_counts.values()).items())),
        "source_catalog": AUTHORITATIVE_SOURCE_CATALOG,
        "external_model_api_calls": 0,
        "review_state": "pending_local_normalization",
    })
    (output / "selection_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
