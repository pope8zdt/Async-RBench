"""Fail-closed protection for candidate materialization and repair tools."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CandidateWriteConflict(RuntimeError):
    pass


def _ready_case_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    ids: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CandidateWriteConflict(f"invalid ready ledger line {number}: {exc}") from exc
        if row.get("case_id"):
            ids.add(str(row["case_id"]))
    return ids


def _consumer_case_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        state: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CandidateWriteConflict(f"invalid consumer state: {exc}") from exc
    ids: set[str] = set()
    if isinstance(state, dict):
        for key, value in state.items():
            if "@r" in str(key):
                ids.add(str(key).split("@r", 1)[0])
            if isinstance(value, dict) and value.get("case_id"):
                ids.add(str(value["case_id"]))
    return ids


def assert_candidate_write_allowed(
    *, case_id: str, candidate_dir: Path, ready_path: Path,
    consumer_state_path: Path, case_local_repair: bool = False,
) -> dict[str, Any]:
    conflicts = {
        "candidate_exists": candidate_dir.exists(),
        "ready_record_exists": case_id in _ready_case_ids(ready_path),
        "consumer_record_exists": case_id in _consumer_case_ids(consumer_state_path),
    }
    # Published or consumed candidates are immutable even in repair mode.
    if conflicts["ready_record_exists"] or conflicts["consumer_record_exists"]:
        raise CandidateWriteConflict(f"immutable candidate {case_id}: {conflicts}")
    if conflicts["candidate_exists"] and not case_local_repair:
        raise CandidateWriteConflict(f"candidate already exists: {candidate_dir}")
    return {"case_id": case_id, "allowed": True, "case_local_repair": case_local_repair, **conflicts}


def guard_for_root(root: Path, case_id: str, *, case_local_repair: bool = False) -> dict[str, Any]:
    return assert_candidate_write_allowed(
        case_id=case_id,
        candidate_dir=root / "candidate_cases" / case_id,
        ready_path=root / "artifacts/async-bench-intake/ready.jsonl",
        consumer_state_path=root / "artifacts/async-bench-intake/consumer-state.json",
        case_local_repair=case_local_repair,
    )
