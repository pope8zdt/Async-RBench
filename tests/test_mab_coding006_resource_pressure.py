"""Filesystem-only regression coverage for the coding:006 event runtime."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from author_local import requires_author_local


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "candidate_cases/mab-dependency-unblock-895f0a4354/task/task_file/scripts/projectorganizer_pressure.py"
pytestmark = requires_author_local(
    "candidate_cases/mab-dependency-unblock-895f0a4354",
)


def load_runtime():
    spec = importlib.util.spec_from_file_location("projectorganizer_pressure", RUNTIME)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(workspace: Path, name: str) -> dict:
    return json.loads((workspace / "output_data" / name).read_text(encoding="utf-8"))


def test_canonical_resource_pressure_path(tmp_path: Path) -> None:
    runtime = load_runtime()
    runtime.build(tmp_path)
    receipt = read(tmp_path, "event_receipt.json")
    plan = read(tmp_path, "allocation_plan.json")
    closure = read(tmp_path, "projectorganizer_closure.json")
    assert receipt["source_task_id"] == "coding:006"
    assert receipt["capacity"] == {"allocation_slots": 1, "active_slots": 1}
    assert plan["critical_path_preserved"] == ["task_service", "scheduler", "allocation"]
    assert plan["cancelled_workstreams"] == ["ui_snapshot", "notification_digest"]
    assert closure["task_service_before_scheduler"]
    assert closure["scheduler_before_allocation"]
    assert closure["notifications_after_allocation"]


def test_directed_mutations_break_their_contract(tmp_path: Path) -> None:
    runtime = load_runtime()
    runtime.build(tmp_path, mutation="wait_low_value")
    assert not read(tmp_path, "decision_manifest.json")["resource_triage_applied"]
    runtime.build(tmp_path, mutation="cancel_critical")
    assert not read(tmp_path, "decision_manifest.json")["critical_path_preserved"]
    runtime.build(tmp_path, mutation="false_closure")
    assert not read(tmp_path, "projectorganizer_closure.json")["closure_complete"]
