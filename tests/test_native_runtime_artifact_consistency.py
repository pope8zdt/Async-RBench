import json
from collections import Counter
from pathlib import Path

from async_rbench.native_runtime_registry import (
    NATIVE_ENVIRONMENT_INITIALIZATION_STATUS,
    NATIVE_RUNTIME_READY_STATUS,
    READY_STATUS,
    RUNTIME_REPORT_FIELDS,
    environment_smoke_qualification,
    native_environment_initialization_qualification,
    read_registry,
    synchronize_runtime_metadata,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "source-native-v4"


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_canonical_runtime_artifacts_are_synchronized_and_smoke_is_not_runtime_ready():
    manifest = read_jsonl(ARTIFACT / "native_manifest.jsonl")
    report = json.loads((ARTIFACT / "production_report.json").read_text(encoding="utf-8"))
    registry_root = ROOT / "artifacts" / "native-runtime-v4"
    registry = read_registry(registry_root / "runtime_registry.jsonl")
    expected_manifest, expected_report, _ = synchronize_runtime_metadata(
        manifest, report, registry, model_evidence_root=registry_root
    )

    assert manifest == expected_manifest
    assert all(report.get(field) == expected_report[field] for field in RUNTIME_REPORT_FIELDS)
    assert Counter(row["benchmark"] for row in manifest if row["benchmark"] in {"OSWorld", "MultiAgentBench"}) == {
        "OSWorld": 91,
        "MultiAgentBench": 341,
    }
    assert report["environment_smoke_ready_count"] == 432
    assert report["environment_smoke_ready_benchmark_counts"] == {
        "MultiAgentBench": 341,
        "OSWorld": 91,
    }
    assert report["native_environment_initialization_count"] == 341
    assert report["native_environment_initialization_benchmark_counts"] == {"MultiAgentBench": 341}
    assert report["runtime_ready_count"] == 95
    assert report["runtime_ready_benchmark_counts"] == {"OSWorld": 91, "SWE-bench": 4}
    assert report["runtime_executed_count"] == 0
    assert report["runtime_executed_benchmark_counts"] == {}
    assert report["runtime_registry_status_counts"] == {
        READY_STATUS: 4,
        NATIVE_ENVIRONMENT_INITIALIZATION_STATUS: 341,
        NATIVE_RUNTIME_READY_STATUS: 91,
        "unregistered": 165,
    }
    assert Counter(entry["status"] for entry in registry.values()) == {
        READY_STATUS: 4,
        NATIVE_ENVIRONMENT_INITIALIZATION_STATUS: 341,
        NATIVE_RUNTIME_READY_STATUS: 91,
    }
    for row in manifest:
        if row["benchmark"] in {"OSWorld", "MultiAgentBench"}:
            entry = registry.get(row["case_id"])
            assert environment_smoke_qualification(
                entry,
                benchmark=row["benchmark"],
                source_task_id=row["source_task_id"],
            ) == (True, None)
            if row["benchmark"] == "OSWorld":
                assert entry["status"] == NATIVE_RUNTIME_READY_STATUS
                assert row["runtime_ready"] is True
                assert row["runtime_blocker"] is None
            else:
                assert entry["status"] == NATIVE_ENVIRONMENT_INITIALIZATION_STATUS
                assert native_environment_initialization_qualification(
                    entry,
                    benchmark=row["benchmark"],
                    source_task_id=row["source_task_id"],
                ) == (True, None)
                assert row["runtime_ready"] is False
                assert row["runtime_blocker"] == "native_environment_initialization_only_not_runtime_ready"
