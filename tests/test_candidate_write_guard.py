from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.candidate_write_guard import CandidateWriteConflict, assert_candidate_write_allowed


def check(tmp_path: Path, case_id: str = "case-a", repair: bool = False):
    return assert_candidate_write_allowed(
        case_id=case_id, candidate_dir=tmp_path / "candidate_cases" / case_id,
        ready_path=tmp_path / "ready.jsonl", consumer_state_path=tmp_path / "consumer.json",
        case_local_repair=repair,
    )


def test_new_candidate_is_allowed(tmp_path: Path):
    assert check(tmp_path)["allowed"] is True


def test_existing_candidate_requires_case_local_repair(tmp_path: Path):
    (tmp_path / "candidate_cases/case-a").mkdir(parents=True)
    with pytest.raises(CandidateWriteConflict, match="already exists"):
        check(tmp_path)
    assert check(tmp_path, repair=True)["candidate_exists"] is True


@pytest.mark.parametrize("ledger", ["ready", "consumer"])
@pytest.mark.parametrize("repair", [False, True])
def test_published_or_consumed_candidate_is_never_writable(tmp_path: Path, ledger: str, repair: bool):
    if ledger == "ready":
        (tmp_path / "ready.jsonl").write_text(json.dumps({"case_id": "case-a", "revision": 1}) + "\n")
    else:
        (tmp_path / "consumer.json").write_text(json.dumps({"case-a@r1": {"case_id": "case-a"}}))
    with pytest.raises(CandidateWriteConflict, match="immutable"):
        check(tmp_path, repair=repair)


def test_any_consumer_revision_blocks(tmp_path: Path):
    (tmp_path / "consumer.json").write_text(json.dumps({"case-a@r7": {"status": "failed"}}))
    with pytest.raises(CandidateWriteConflict):
        check(tmp_path, repair=True)


@pytest.mark.parametrize("script", [
    "rebuild_candidate_from_blueprint_v91.py",
    "materialize_swe_runtime_first5.py",
    "materialize_swe_runtime_next.py",
    "materialize_mab_database_runtime.py",
])
def test_help_is_read_only_and_successful(script: str):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / script), "--help"],
        cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    assert result.returncode == 0
    assert "--help" in result.stdout
