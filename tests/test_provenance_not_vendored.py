"""Collection-wide upstream locks are optional provenance material.

A normal clone of this repository vendors only upstream/README.md; git will
never deliver upstream/<benchmark>/SOURCE_LOCK.json.  validate_sources must
therefore skip lock-based checks when no collection lock is vendored, and stay
strict (any missing/mismatched lock is an error) the moment upstream has been
(partially) vendored - a partial checkout must never pass silently.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from async_rbench.provenance import validate_sources
from async_rbench.spec import CaseSpec


def _case(tmp_path: Path, case_id: str, source: dict, *, benchmark: str = "terminal-bench") -> CaseSpec:
    case_dir = tmp_path / "cases" / case_id
    return CaseSpec(
        path=case_dir / "public_case.yaml",
        raw={
            "case_id": case_id,
            "implementation": "real-instance-derived",
            "source_tasks": [{"id": source["id"], "benchmark": benchmark, **source}],
            "asset_copies": [],
            "delegation_workstreams": [],
            "initial_wave": [],
        },
    )


def test_lockable_case_passes_without_vendored_upstream(tmp_path: Path) -> None:
    # No upstream/ at all: lock-based checks cannot run and must not fail the
    # clone-time static validation.
    case = _case(tmp_path, "example", {"id": "task-1", "upstream_path": "upstream/terminal-bench/original-tasks-locked/task-1"})
    assert validate_sources(tmp_path, [case]) == []


def test_missing_lock_is_strict_once_upstream_is_vendored(tmp_path: Path) -> None:
    # A single vendored collection lock flips the mode: gaia2 cases must then
    # fail when their own collection lock is missing, not pass silently.
    (tmp_path / "upstream/terminal-bench").mkdir(parents=True)
    (tmp_path / "upstream/terminal-bench/SOURCE_LOCK.json").write_text("{}", encoding="utf-8")
    case = _case(tmp_path, "example", {"id": "scenario-1"}, benchmark="gaia2")
    errors = validate_sources(tmp_path, [case])
    assert errors and "missing source lock for gaia2" in errors[0]


def test_source_native_locks_stay_strict_without_vendored_upstream(tmp_path: Path) -> None:
    # The upstream-not-vendored leniency must not leak into per-case
    # source-native locks, which ARE vendored in the repo and validate the
    # exact bytes of the case's own source manifest.
    source = tmp_path / "artifacts/source-native-v4/source.json"
    source.parent.mkdir(parents=True)
    source.write_text("original content\n", encoding="utf-8")
    case_dir = tmp_path / "cases/example"
    (case_dir / "private").mkdir(parents=True)
    relative = source.relative_to(tmp_path).as_posix()
    (case_dir / "private/source_lock.json").write_text(
        json.dumps({
            "source_files": [relative],
            "source_file_sha256": {
                relative: hashlib.sha256(source.read_bytes()).hexdigest(),
            },
        }),
        encoding="utf-8",
    )
    case = CaseSpec(
        path=case_dir / "public_case.yaml",
        raw={
            "case_id": "example",
            "implementation": "real-instance-derived",
            "source_tasks": [{"id": "database:001", "benchmark": "multiagentbench"}],
            "asset_copies": [],
            "delegation_workstreams": [],
            "initial_wave": [],
        },
    )
    # Corrupt the locked file: validation must now flag the hash mismatch.
    source.write_text("tampered content\n", encoding="utf-8")
    errors = validate_sources(tmp_path, [case])
    assert any("source-native hash mismatch" in error for error in errors)


def test_upstream_asset_copies_skipped_without_vendored_upstream(tmp_path: Path) -> None:
    # asset_copies may point at upstream/ originals; without vendored
    # upstream/ the compare is skipped, not an error.
    case = _case(tmp_path, "example", {"id": "task-1", "upstream_path": "upstream/terminal-bench/original-tasks-locked/task-1"})
    case.raw["asset_copies"] = [
        {"from": "upstream/terminal-bench/original-tasks-locked/task-1/solution.sh",
         "to": "task/upstream_solutions/task-1.sh"},
    ]
    # Neither source nor target exists, so a strict run would error.
    assert validate_sources(tmp_path, [case]) == []


def test_upstream_asset_copies_strict_once_vendored(tmp_path: Path) -> None:
    (tmp_path / "upstream/terminal-bench").mkdir(parents=True)
    (tmp_path / "upstream/terminal-bench/SOURCE_LOCK.json").write_text("{}", encoding="utf-8")
    case = _case(tmp_path, "example", {"id": "task-1", "upstream_path": "upstream/terminal-bench/original-tasks-locked/task-1"})
    case.raw["asset_copies"] = [
        {"from": "upstream/terminal-bench/original-tasks-locked/task-1/solution.sh",
         "to": "task/upstream_solutions/task-1.sh"},
    ]
    errors = validate_sources(tmp_path, [case])
    assert any("copied asset differs" in error for error in errors)
