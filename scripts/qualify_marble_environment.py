"""Qualify every source-native MARBLE case without running a model episode."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.marble_runtime import (  # noqa: E402
    MARBLE_BENCHMARK,
    MARBLE_SMOKE_SCHEMA,
    MARBLE_SMOKE_SCOPE,
    MARBLE_SMOKE_STATUS,
    MarbleUpstreamBindings,
    qualify_marble_case,
    write_jsonl,
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"non-object JSONL row at {path}:{line_number}")
        rows.append(row)
    return rows


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve MARBLE Config/Engine/Environment/Evaluator bindings using a "
            "zero-network deterministic healthcheck. This is not a model episode."
        )
    )
    parser.add_argument("--source-root", default="artifacts/source-native-v4")
    parser.add_argument("--upstream", default="upstream/marble")
    parser.add_argument(
        "--output",
        default="artifacts/native-runtime-v4/marble_environment_smoke.jsonl",
    )
    parser.add_argument(
        "--report",
        default="artifacts/native-runtime-v4/marble_environment_smoke_report.json",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Limit qualification to one or more case IDs; default is all MARBLE cases.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = (ROOT / args.source_root).resolve()
    upstream_root = (ROOT / args.upstream).resolve()
    output = (ROOT / args.output).resolve()
    report_path = (ROOT / args.report).resolve()
    selected = set(args.case_id)

    manifest_path = source_root / "native_manifest.jsonl"
    if not manifest_path.is_file():
        print(f"source-native manifest not found: {manifest_path}", file=sys.stderr)
        return 2
    rows = [
        row
        for row in read_jsonl(manifest_path)
        if row.get("benchmark") == MARBLE_BENCHMARK
        and (not selected or str(row.get("case_id")) in selected)
    ]
    found = {str(row.get("case_id")) for row in rows}
    missing = sorted(selected - found)
    if missing:
        print("unknown MARBLE case IDs: " + ", ".join(missing), file=sys.stderr)
        return 2

    try:
        bindings = MarbleUpstreamBindings(upstream_root)
    except Exception as exc:
        print(f"MARBLE upstream binding preflight failed: {exc}", file=sys.stderr)
        return 1

    evidence: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for row in rows:
        case_id = str(row["case_id"])
        native_path = str(row.get("native_path") or "")
        case_dir = (source_root / native_path).resolve()
        try:
            entry = qualify_marble_case(
                case_dir,
                row,
                repository_root=ROOT,
                upstream_root=upstream_root,
                bindings=bindings,
            )
        except Exception as exc:
            failures.append(
                {
                    "case_id": case_id,
                    "source_task_id": str(row.get("source_task_id") or ""),
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )
        else:
            evidence.append(entry)

    counts = Counter(entry["scenario"] for entry in evidence)
    report = {
        "schema_version": MARBLE_SMOKE_SCHEMA,
        "status": MARBLE_SMOKE_STATUS if rows and not failures else "environment_smoke_failed",
        "execution_scope": MARBLE_SMOKE_SCOPE,
        "qualification_profile": "marble_environment_smoke_v1",
        "selected_count": len(rows),
        "validated_count": len(evidence),
        "failed_count": len(failures),
        "scenario_counts": dict(sorted(counts.items())),
        "expected_full_collection": {
            "total": 341,
            "bargaining": 96,
            "coding": 97,
            "database": 98,
            "research": 50,
        },
        "claims": {
            "model_episode_executed": False,
            "gold_evaluator_executed": False,
            "task_scored": False,
            "formal_promotion_ready": False,
        },
        "failures": failures,
    }
    if not selected:
        expected = report["expected_full_collection"]
        actual = {"total": len(evidence), **dict(counts)}
        if any(actual.get(key, 0) != value for key, value in expected.items()):
            report["status"] = "environment_smoke_failed"
            report["collection_error"] = {
                "expected": expected,
                "actual": actual,
            }

    write_jsonl(output, evidence)
    _write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == MARBLE_SMOKE_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
