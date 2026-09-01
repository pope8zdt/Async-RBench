from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from author_local import requires_author_local


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "candidate_cases" / "mab-state-reconciliation-bda6dda56f"
pytestmark = requires_author_local(
    "candidate_cases/mab-state-reconciliation-bda6dda56f",
)
RUNTIME = CASE / "task" / "task_file" / "scripts" / "state_reconciliation.py"


def _runtime():
    spec = importlib.util.spec_from_file_location("mab_db017_runtime", RUNTIME)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(workspace: Path, name: str) -> dict:
    return json.loads((workspace / "output_data" / name).read_text(encoding="utf-8"))


def test_database017_source_binding_and_state_reconciliation_contract(tmp_path: Path) -> None:
    runtime = _runtime()
    runtime.build(tmp_path)
    source = json.loads((CASE / "private" / "source_manifests" / "01-native_case.json").read_text(encoding="utf-8"))
    receipt = _read(tmp_path, "event_receipt.json")
    diagnosis = _read(tmp_path, "database_diagnosis.json")
    closure = _read(tmp_path, "reconciliation_closure.json")

    assert source["source_binding"]["task_id"] == "database:017"
    assert source["source_binding"]["record_sha256"] == receipt["native_state_digest"]
    assert receipt["pg_stat_statements"]["insert_threads"] == 100
    assert receipt["native_action_sequence"] > receipt["release_after_native_action_sequence"]
    assert diagnosis["selected_causes"] == ["INSERT_LARGE_DATA"]
    assert diagnosis["retracted_causes"] == ["MISSING_INDEXES", "POOR_JOIN_PERFORMANCE"]
    assert diagnosis["preserved_probes"] == [
        "LOCK_CONTENTION probe completed", "VACUUM catalog probe completed",
    ]
    assert closure["closure_complete"] is True
    assert closure["reverified_after_action_sequence"] > receipt["native_action_sequence"]


def test_database017_directed_mutations_change_the_intended_contract(tmp_path: Path) -> None:
    runtime = _runtime()
    expectations = {
        "wrong_cause": lambda d, r, c: d["selected_causes"] != ["INSERT_LARGE_DATA"],
        "stale_join": lambda d, r, c: d["retracted_causes"] != ["MISSING_INDEXES", "POOR_JOIN_PERFORMANCE"],
        "forged_receipt": lambda d, r, c: r["native_action_sequence"] <= r["release_after_native_action_sequence"],
        "broken_closure": lambda d, r, c: c["closure_complete"] is False,
    }
    for mutation, expected in expectations.items():
        workspace = tmp_path / mutation
        runtime.build(workspace, mutation=mutation)
        assert expected(
            _read(workspace, "database_diagnosis.json"),
            _read(workspace, "event_receipt.json"),
            _read(workspace, "reconciliation_closure.json"),
        ), mutation
