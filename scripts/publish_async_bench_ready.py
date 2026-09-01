from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INTAKE = ROOT / "artifacts" / "async-bench-intake"
READY = INTAKE / "ready.jsonl"
LOCK = INTAKE / "ready.lock"
SCHEMA = INTAKE / "ready.schema.json"

REQUIRED_CASE_FILES = (
    "public_case.yaml",
    "private/private_case.yaml",
    "private/score_plan.json",
    "private/quality_contract.yaml",
    "generate.py",
    "oracle.py",
    "verify.py",
    "task/Dockerfile",
    "task/docker-compose.yaml",
    "task/oracle.sh",
    "task/run-tests.sh",
    "task/tests/semantic_checks.json",
    "task/tests/control_flow_checks.json",
)


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = str(path.relative_to(root)).replace("\\", "/")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _initialize() -> None:
    INTAKE.mkdir(parents=True, exist_ok=True)
    READY.touch(exist_ok=True)
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Async-RBench case ready handoff",
        "type": "object",
        "required": [
            "case_id", "absolute_path", "source_category", "completed_at",
            "static_checks", "status", "revision", "bundle_sha256", "control_prefix",
        ],
        "properties": {
            "case_id": {"type": "string", "minLength": 1},
            "absolute_path": {"type": "string", "minLength": 3},
            "source_category": {"type": "string", "minLength": 1},
            "completed_at": {"type": "string", "format": "date-time"},
            "static_checks": {"type": "object", "minProperties": 1},
            "status": {"const": "ready"},
            "revision": {"type": "integer", "minimum": 1},
            "bundle_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "control_prefix": {"type": "string", "minLength": 1},
        },
        "additionalProperties": True,
    }
    SCHEMA.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def _acquire_lock() -> int:
    INTAKE.mkdir(parents=True, exist_ok=True)
    for _ in range(200):
        try:
            return os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            time.sleep(0.05)
    raise TimeoutError(f"ready manifest lock remained busy: {LOCK}")


def _release_lock(handle: int) -> None:
    os.close(handle)
    LOCK.unlink(missing_ok=True)


def _records() -> list[dict[str, Any]]:
    if not READY.is_file():
        return []
    return [json.loads(line) for line in READY.read_text(encoding="utf-8").splitlines() if line.strip()]


def publish(
    *, case_id: str, case_path: Path, source_category: str,
    static_checks: dict[str, str], revision: int, control_prefix: str,
) -> dict[str, Any]:
    _initialize()
    absolute = case_path.resolve()
    if not absolute.is_dir():
        raise FileNotFoundError(f"case directory does not exist: {absolute}")
    missing = [relative for relative in REQUIRED_CASE_FILES if not (absolute / relative).is_file()]
    if missing:
        raise ValueError(f"case family is incomplete; missing required files: {missing}")
    if not static_checks or any(value != "passed" for value in static_checks.values()):
        raise ValueError("every declared static check must equal 'passed'")
    for required_check in ("candidate_family_pair_smoke", "case_promote_dry_run"):
        if static_checks.get(required_check) != "passed":
            raise ValueError(f"missing required ready check: {required_check}=passed")
    if not control_prefix.strip():
        raise ValueError("control_prefix must be non-empty")
    handle = _acquire_lock()
    try:
        prior = [row for row in _records() if row.get("case_id") == case_id]
        maximum = max((int(row["revision"]) for row in prior), default=0)
        if revision != maximum + 1:
            raise ValueError(
                f"{case_id}: revision must be {maximum + 1}; got {revision}"
            )
        record = {
            "case_id": case_id,
            "absolute_path": str(absolute),
            "source_category": source_category,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "static_checks": static_checks,
            "status": "ready",
            "revision": revision,
            "bundle_sha256": _tree_digest(absolute),
            "control_prefix": control_prefix,
        }
        with READY.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return record
    finally:
        _release_lock(handle)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--case-id")
    parser.add_argument("--case-path", type=Path)
    parser.add_argument("--source-category")
    parser.add_argument("--control-prefix")
    parser.add_argument("--static-check", action="append", default=[])
    parser.add_argument("--revision", type=int, default=1)
    args = parser.parse_args()
    if args.init:
        _initialize()
        print(json.dumps({"ready_manifest": str(READY), "record_count": len(_records())}))
        return 0
    if not args.case_id or not args.case_path or not args.source_category or not args.control_prefix:
        parser.error("publication requires --case-id, --case-path, --source-category, and --control-prefix")
    checks: dict[str, str] = {}
    for item in args.static_check:
        if "=" not in item:
            parser.error("--static-check must be NAME=passed")
        name, value = item.split("=", 1)
        checks[name] = value
    record = publish(
        case_id=args.case_id,
        case_path=args.case_path,
        source_category=args.source_category,
        static_checks=checks,
        revision=args.revision,
        control_prefix=args.control_prefix,
    )
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
