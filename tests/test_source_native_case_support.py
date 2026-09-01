from __future__ import annotations

import hashlib
import json
from pathlib import Path

from async_rbench.provenance import validate_sources
from async_rbench.spec import (
    CaseSpec,
    SUPPORTED_CASE_BENCHMARKS,
    normalize_case_benchmark,
)


def test_multiagentbench_and_osworld_are_canonical_supported_sources(tmp_path: Path) -> None:
    assert normalize_case_benchmark("MultiAgentBench") == "multiagentbench"
    assert normalize_case_benchmark("OSWorld") == "osworld"
    assert {"multiagentbench", "osworld"} <= set(SUPPORTED_CASE_BENCHMARKS)

    source = tmp_path / "artifacts/source-native-v4/source.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"source": true}\n', encoding="utf-8")
    case_dir = tmp_path / "candidate_cases/example"
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
            "source_tasks": [{"id": "database:001", "benchmark": "MultiAgentBench"}],
            "asset_copies": [],
            "delegation_workstreams": [],
            "initial_wave": [],
        },
    )
    assert validate_sources(tmp_path, [case]) == []

