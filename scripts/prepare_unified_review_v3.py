"""Build a normalized 965-case inventory and deterministic fine-review queue."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.unified_case_v3 import compact_review_record, read_json, read_jsonl  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def ingest(root: Path, collection: str) -> list[dict]:
    result = []
    for row in read_jsonl(root / "case_manifest.jsonl"):
        case_dir = root / str(row["path"])
        case = read_json(case_dir / "case.json")
        expected = read_json(case_dir / "private" / "expected.json")
        compact = compact_review_record(case, expected, collection, str(case_dir))
        compact["source_manifest_record"] = row
        result.append(compact)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy", default="artifacts/authoritative-case-300/04-case-production")
    parser.add_argument("--v2", default="artifacts/authoritative-expansion-v2/03-case-production")
    parser.add_argument("--output", default="artifacts/unified-case-set-v3/00-inventory")
    args = parser.parse_args()
    legacy = Path(args.legacy).resolve()
    v2 = Path(args.v2).resolve()
    output = Path(args.output).resolve()
    rows = ingest(legacy, "legacy-300") + ingest(v2, "expansion-v2-665")

    ids = [str(row["unified_candidate_id"]) for row in rows]
    if len(ids) != len(set(ids)):
        duplicates = [key for key, count in Counter(ids).items() if count > 1]
        raise RuntimeError(f"unified candidate ID collision: {duplicates[:10]}")
    task_keys = [(str(row["benchmark"]), str(row["source_task_id"])) for row in rows]
    duplicate_tasks = {key: count for key, count in Counter(task_keys).items() if count > 1}
    write_jsonl(output / "unified_inventory.jsonl", rows)
    write_jsonl(output / "fine_review_queue.jsonl", rows)
    issue_counts = Counter(
        issue["code"] for row in rows for issue in row["deterministic_issues"]
    )
    report = {
        "schema_version": "async-rbench-unified-inventory-v3",
        "case_count": len(rows),
        "collection_counts": dict(sorted(Counter(row["collection"] for row in rows).items())),
        "benchmark_counts": dict(sorted(Counter(row["benchmark"] for row in rows).items())),
        "family_counts": dict(sorted(Counter(row["current_family"] for row in rows).items())),
        "evidence_class_counts": dict(sorted(Counter(row["evidence_class"] for row in rows).items())),
        "fatal_case_count": sum(row["fatal_issue_count"] > 0 for row in rows),
        "major_case_count": sum(row["major_issue_count"] > 0 for row in rows),
        "issue_counts": dict(sorted(issue_counts.items())),
        "duplicate_source_task_groups": len(duplicate_tasks),
        "duplicate_source_task_records": sum(duplicate_tasks.values()),
        "duplicate_source_tasks": [
            {"benchmark": key[0], "source_task_id": key[1], "count": count}
            for key, count in sorted(duplicate_tasks.items())
        ],
    }
    write_json(output / "inventory_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
