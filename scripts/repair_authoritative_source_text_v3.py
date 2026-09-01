"""Restore complete authoritative SWE-bench and Terminal-Bench instructions."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import duckdb
import yaml
from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.unified_case_v3 import read_jsonl  # noqa: E402


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def swe_records() -> dict[str, dict]:
    result: dict[str, dict] = {}
    sources = (
        ("princeton-nlp/SWE-bench", ("train", "dev", "test")),
        ("SWE-bench/SWE-bench_Verified", ("test",)),
        ("SWE-bench/SWE-bench_Multilingual", ("test",)),
        ("princeton-nlp/SWE-bench_Multimodal", ("dev", "test")),
    )
    for dataset, splits in sources:
      for split in splits:
        filename = f"data/{split}-00000-of-00001.parquet"
        local = hf_hub_download(dataset, filename, repo_type="dataset")
        records = duckdb.execute(
            "SELECT instance_id, problem_statement FROM read_parquet(?)", [local]
        ).fetchall()
        for instance_id, problem_statement in records:
            result[str(instance_id)] = {
                "instruction": str(problem_statement),
                "split": split,
                "source_url": f"https://huggingface.co/datasets/{dataset}",
                "source_kind": "official_problem_statement_plus_public_reasoning_execution_trace",
                "source_revision": "dataset parquet snapshot resolved by huggingface_hub",
            }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="artifacts/unified-case-set-v3/00-inventory/unified_inventory.jsonl")
    parser.add_argument("--output", default="artifacts/unified-case-set-v3/00-inventory/unified_inventory_repaired.jsonl")
    parser.add_argument("--queue", default="artifacts/unified-case-set-v3/00-inventory/fine_review_queue_repaired.jsonl")
    parser.add_argument("--report", default="artifacts/unified-case-set-v3/00-inventory/source_repair_report.json")
    args = parser.parse_args()
    rows = read_jsonl(Path(args.input).resolve())
    swe = swe_records()
    terminal_lock = json.loads((ROOT / "upstream" / "terminal-bench" / "SOURCE_LOCK.json").read_text(encoding="utf-8"))
    lock_tasks = terminal_lock.get("tasks") or terminal_lock.get("task_sha256") or terminal_lock
    repaired = Counter()
    missing: list[str] = []
    for row in rows:
        benchmark = str(row.get("benchmark"))
        task_id = str(row.get("source_task_id"))
        repair = None
        if benchmark == "SWE-bench":
            record = swe.get(task_id)
            if record is None:
                missing.append(task_id)
            else:
                repair = {**record, "instance_id": task_id}
        elif benchmark == "Terminal-Bench":
            task_path = ROOT / "upstream" / "terminal-bench" / "original-tasks-locked" / task_id / "task.yaml"
            if not task_path.is_file():
                missing.append(task_id)
            else:
                payload = yaml.safe_load(task_path.read_text(encoding="utf-8"))
                repair = {
                    "instruction": str(payload["instruction"]),
                    "source_url": "https://github.com/laude-institute/terminal-bench",
                    "source_kind": "locked_official_terminal_bench_task_plus_public_execution_trace",
                    "source_revision": str(lock_tasks.get(task_id) or "locked-local-source"),
                    "instance_id": task_id,
                }
        if repair is None:
            continue
        old_instruction = str(row.get("instruction") or "")
        repair["instruction_sha256"] = sha256_text(str(repair["instruction"]))
        repair["replaced_instruction_sha256"] = sha256_text(old_instruction)
        repair["repair_method"] = "restored_from_authoritative_source"
        row["instruction"] = repair["instruction"]
        row["source_repair"] = repair
        row["deterministic_issues"] = [
            issue for issue in row.get("deterministic_issues") or []
            if issue.get("code") not in {"truncated_instruction", "incomplete_source_provenance"}
        ]
        row["fatal_issue_count"] = sum(
            issue.get("severity") == "fatal" for issue in row["deterministic_issues"]
        )
        row["major_issue_count"] = sum(
            issue.get("severity") == "major" for issue in row["deterministic_issues"]
        )
        repaired[benchmark] += 1
    write_jsonl(Path(args.output).resolve(), rows)
    write_jsonl(Path(args.queue).resolve(), rows)
    report = {
        "schema_version": "authoritative-source-repair-v3",
        "input_count": len(rows),
        "repaired_count": sum(repaired.values()),
        "repaired_benchmark_counts": dict(sorted(repaired.items())),
        "remaining_truncated_instruction_count": sum(
            any(issue.get("code") == "truncated_instruction" for issue in row.get("deterministic_issues") or [])
            for row in rows
        ),
        "remaining_incomplete_source_provenance_count": sum(
            any(issue.get("code") == "incomplete_source_provenance" for issue in row.get("deterministic_issues") or [])
            for row in rows
        ),
        "missing_count": len(missing),
        "missing_task_ids": sorted(missing),
    }
    write_json(Path(args.report).resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
