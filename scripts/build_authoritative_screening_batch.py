"""Build a deterministic 350-record authoritative trajectory screening batch."""

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

from async_rbench.trajectory_curation import (
    AUTHORITATIVE_SOURCE_CATALOG,
    CHOICES,
    decision_review_template,
    read_jsonl,
    render_review_html,
    select_authoritative_batch,
    trajectory_review_record,
    write_jsonl,
)


SOURCE_AUDIT = [
    {
        "benchmark": "Terminal-Bench",
        "official_url": "https://github.com/laude-institute/terminal-bench-leaderboard",
        "public_content": "official run logs, commands, terminal recordings, and results",
        "execution_trajectories_used": True,
        "reason": "Official repository contains per-trial agent logs and results.",
    },
    {
        "benchmark": "SWE-bench",
        "official_url": "https://github.com/SWE-bench/experiments",
        "public_content": "predictions, evaluation logs, and reasoning trajectories",
        "execution_trajectories_used": True,
        "reason": "Official experiments repository documents public inference trajectories.",
    },
    {
        "benchmark": "GAIA2",
        "official_url": "https://huggingface.co/datasets/meta-agents-research-environments/gaia2",
        "public_content": "963 scenario records and evaluator/environment data",
        "execution_trajectories_used": False,
        "reason": "Public dataset is task/scenario data, not a corpus of baseline execution logs.",
    },
    {
        "benchmark": "OSWorld",
        "official_url": "https://github.com/xlang-ai/OSWorld",
        "public_content": "tasks, environment, evaluation code, and limited gold examples",
        "execution_trajectories_used": False,
        "reason": "The checked public repository does not contain a baseline trajectory corpus.",
    },
    {
        "benchmark": "MultiAgentBench",
        "official_url": "https://github.com/MultiagentBench/MARBLE",
        "public_content": "task/config corpus and multi-agent runtime",
        "execution_trajectories_used": False,
        "reason": "The checked public repository does not commit the paper's run-log corpus.",
    },
    {
        "benchmark": "SentinelBench",
        "official_url": "https://github.com/microsoft/sentinel_environments",
        "public_content": "100 scenarios, environments, harness, and aggregate baseline report",
        "execution_trajectories_used": False,
        "reason": "The repository defines generated result files but does not commit baseline step logs.",
    },
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--terminal-bench", type=int, default=225)
    parser.add_argument("--swe-bench", type=int, default=125)
    args = parser.parse_args()

    manifest = Path(args.manifest).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = read_jsonl(manifest)
    selected, report = select_authoritative_batch(
        rows,
        source_quotas={
            "terminal_bench": args.terminal_bench,
            "swe_bench": args.swe_bench,
        },
    )
    reviews = [trajectory_review_record(row) for row in selected]
    write_jsonl(output / "selected_manifest.jsonl", selected)
    write_jsonl(output / "trajectory_reviews.jsonl", reviews)
    render_review_html(reviews, output / "trajectory_review.html")
    (output / "decision_review.template.json").write_text(
        json.dumps(decision_review_template(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "choice_catalog.json").write_text(
        json.dumps(CHOICES, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    report.update({
        "manifest_path": str(manifest),
        "manifest_sha256": _sha256(manifest),
        "manifest_row_count": len(rows),
        "archive_layer": "Contextbench/Tracebench",
        "archive_url": "https://huggingface.co/datasets/Contextbench/Tracebench",
        "source_audit": SOURCE_AUDIT,
        "selected_agents": dict(sorted(Counter(
            str(row.get("agent") or "unknown") for row in selected
        ).items())),
        "selected_models": dict(sorted(Counter(
            str(row.get("model") or "unknown") for row in selected
        ).items())),
        "selected_categories": dict(sorted(Counter(
            str(row.get("category") or "unknown") for row in selected
        ).items())),
        "review_state": "pending_agent_screen",
    })
    report["source_catalog"] = AUTHORITATIVE_SOURCE_CATALOG
    (output / "selection_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
