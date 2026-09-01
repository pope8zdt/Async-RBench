#!/usr/bin/env python3
"""Concurrent repair/validation queue with serialized safe promotion.

Each worker owns exactly one candidate directory and one hash-addressed
quality output. Registry mutation is intentionally kept on the coordinator
thread because cases/registry.json is one shared atomic resource.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from async_rbench.evaluation.runner import _case_digest
from async_rbench.evaluation.version import EVALUATION_CONTRACT_VERSION
from async_rbench.evaluation.weighting import SCORE_POLICY_VERSION


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts/case-200-pipeline"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    return value


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=ROOT, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )


def infer_prefix(case_dir: Path) -> str:
    registry = load(case_dir / "task/tests/control_flow_checks.json")
    point_id = str((registry.get("checks") or [{}])[0].get("id") or "")
    if ".cf." not in point_id:
        raise ValueError(f"cannot infer control prefix from {point_id!r}")
    return point_id.split(".cf.", 1)[0]


def validate_one(case_id: str, output_root: Path, seed: int) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()
    case_dir = ROOT / "candidate_cases" / case_id
    row: dict[str, Any] = {
        "case_id": case_id, "started_at": started, "passed": False,
        "stages": {},
    }
    rebuilt = run([
        sys.executable, "-m", "scripts.rebuild_candidate_from_blueprint_v91",
        "--case-id", case_id,
    ])
    row["stages"]["rebuild"] = {
        "exit_code": rebuilt.returncode, "output_tail": rebuilt.stdout[-4000:],
    }
    if rebuilt.returncode:
        return row
    prefix = infer_prefix(case_dir)
    row["control_prefix"] = prefix
    digest = _case_digest(case_dir)
    row["case_bundle_sha256"] = digest
    dry = run([
        sys.executable, "-m", "async_rbench.cli", "case-promote",
        "--candidate", case_id, "--control-prefix", prefix, "--dry-run",
    ])
    row["stages"]["static_preflight"] = {
        "exit_code": dry.returncode, "output_tail": dry.stdout[-6000:],
    }
    if dry.returncode:
        return row
    quality_root = output_root / "quality" / f"{case_id}-{digest[:12]}"
    quality_report = quality_root / "quality-execution-report.json"
    if quality_report.is_file() and load(quality_report).get("passed") is True:
        quality_exit = 0
        quality_output = "resumed hash-matched passing quality report"
    else:
        quality = run([
            sys.executable, "-m", "async_rbench.cli", "candidate-quality-preflight",
            "--candidate", case_id, "--control-prefix", prefix,
            "--output", str(quality_root), "--seed", str(seed),
        ])
        quality_exit = quality.returncode
        quality_output = quality.stdout[-8000:]
    row["stages"]["quality_preflight"] = {
        "exit_code": quality_exit, "output_tail": quality_output,
        "report": str(quality_report),
    }
    if quality_exit or not quality_report.is_file():
        return row
    quality_payload = load(quality_report)
    if quality_payload.get("passed") is not True:
        return row
    if _case_digest(case_dir) != digest:
        row["stages"]["integrity"] = {
            "exit_code": 1, "output_tail": "candidate changed during quality execution",
        }
        return row
    status_path = case_dir / "STATUS.json"
    status = load(status_path)
    status.update({
        "status": "v9.1_release_gates_passed_pending_registry_promotion",
        "quality_execution_passed": True,
        "fresh_quality_report": str(quality_report.relative_to(ROOT)).replace("\\", "/"),
        "fresh_case_bundle_sha256": digest,
        "evaluation_contract_version": EVALUATION_CONTRACT_VERSION,
        "score_policy_version": SCORE_POLICY_VERSION,
        "fresh_validation_completed_at": datetime.now(timezone.utc).isoformat(),
    })
    dump(status_path, status)
    row["passed"] = True
    row["completed_at"] = datetime.now(timezone.utc).isoformat()
    return row


def promote_one(row: dict[str, Any]) -> dict[str, Any]:
    command = [
        sys.executable, "-m", "async_rbench.cli", "case-promote",
        "--candidate", str(row["case_id"]),
        "--control-prefix", str(row["control_prefix"]), "--yes",
    ]
    result = run(command)
    return {
        "exit_code": result.returncode,
        "output_tail": result.stdout[-10000:],
        "passed": result.returncode == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", action="append", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260901)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--promote", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(validate_one, case_id, output, args.seed): case_id
            for case_id in args.case_id
        }
        for future in as_completed(futures):
            case_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:  # fail closed but keep other cases running
                row = {
                    "case_id": case_id, "passed": False,
                    "coordinator_error": f"{type(exc).__name__}: {exc}",
                }
            if row.get("passed") and args.promote:
                row["promotion"] = promote_one(row)
                row["passed"] = bool(row["promotion"]["passed"])
            rows.append(row)
            dump(output / "latest.json", {
                "schema_version": "case-200-pipeline-v1",
                "target_case_count": 200,
                "rows": sorted(rows, key=lambda value: str(value["case_id"])),
            })
            print(json.dumps({
                "case_id": case_id, "passed": row.get("passed"),
                "promoted": (row.get("promotion") or {}).get("passed"),
            }, ensure_ascii=False), flush=True)
    passed = sum(bool(row.get("passed")) for row in rows)
    summary = {
        "schema_version": "case-200-pipeline-v1",
        "target_case_count": 200,
        "attempted": len(rows), "passed": passed, "failed": len(rows) - passed,
        "rows": sorted(rows, key=lambda value: str(value["case_id"])),
    }
    dump(output / "latest.json", summary)
    print(json.dumps({k: summary[k] for k in ("attempted", "passed", "failed")}, indent=2))
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
