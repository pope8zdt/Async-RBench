"""Collect and structurally screen OSWorld, SWE-bench and MultiAgentBench."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.expansion_v2 import (  # noqa: E402
    collect_multiagentbench,
    collect_osworld,
    collect_swe,
    source_report,
    structural_screen,
    write_json,
    write_jsonl,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--osworld", required=True)
    parser.add_argument("--swe-dossiers", required=True)
    parser.add_argument("--multiagentbench", required=True)
    parser.add_argument("--multiagent-results")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()

    os_artifacts, os_tasks = collect_osworld(Path(args.osworld).resolve())
    swe_artifacts, swe_tasks = collect_swe(Path(args.swe_dossiers).resolve())
    mab_artifacts, mab_tasks = collect_multiagentbench(
        Path(args.multiagentbench).resolve(),
        Path(args.multiagent_results).resolve() if args.multiagent_results else None,
    )
    artifacts = os_artifacts + swe_artifacts + mab_artifacts
    tasks = os_tasks + swe_tasks + mab_tasks
    for task in tasks:
        task["structural_screen"] = structural_screen(task)

    write_jsonl(output / "source_artifacts.jsonl", artifacts)
    write_jsonl(output / "semantic_candidates.jsonl", tasks)
    write_jsonl(
        output / "semantic_review_queue.jsonl",
        [task for task in tasks if task["structural_screen"]["decision"] == "semantic_review"],
    )
    write_jsonl(
        output / "evidence_expansion_queue.jsonl",
        [task for task in tasks if task["structural_screen"]["decision"] == "expand_evidence"],
    )
    report = source_report(artifacts, tasks)
    write_json(output / "source_report.json", report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
