from __future__ import annotations

import json
from pathlib import Path

from async_rbench.dynamic_pilot import _event_contract, _gaia_points
from async_rbench.dynamic_points import (
    participant_leakage_hits, participant_strategy_leakage_hits,
    validate_dynamic_point_plan, validate_event_contracts,
)


def _contracts():
    return [_event_contract(
        "late_zip4_reply", "task_scope_or_dependency_change",
        affected=["saved_list_artifact", "email_artifact"],
        unaffected=["group_message_artifact"],
        opportunities=[
            "stale_completion", "pre_event_affected_commit",
            "pre_event_unaffected_commit",
        ],
        trigger_after=["saved_list_artifact", "group_message_artifact"],
    )]


def test_v6_plan_derives_count_and_dimensions_from_event_contract() -> None:
    points = _gaia_points()
    assert validate_event_contracts(
        _contracts(), event_ids={"late_zip4_reply"},
    ) == []
    assert validate_dynamic_point_plan(
        points, event_ids={"late_zip4_reply"}, expected_prefix="sm",
        event_contracts=_contracts(),
    ) == []
    too_small = points[:3]
    errors = validate_dynamic_point_plan(
        too_small, event_ids={"late_zip4_reply"}, event_contracts=_contracts(),
    )
    assert any("at least 4" in error for error in errors)


def test_legacy_v5_keeps_frozen_eight_point_contract() -> None:
    points = _gaia_points()
    errors = validate_dynamic_point_plan(points, registry_version="5")
    assert any("8-12" in error for error in errors)


def test_v5_plan_rejects_duplicate_gate_evidence_and_mutation() -> None:
    points = json.loads(json.dumps(_gaia_points()))
    points[1]["gate"] = points[0]["gate"]
    points[1]["gate_args"] = points[0]["gate_args"]
    points[1]["mutation_id"] = points[0]["mutation_id"]
    errors = validate_dynamic_point_plan(points, event_contracts=_contracts())
    assert any("gate and gate_args duplicate" in error for error in errors)
    assert any("mutation_id must be unique" in error for error in errors)


def test_participant_leakage_scan_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "task").mkdir()
    (tmp_path / "public_case.yaml").write_text("case_id: safe\n", encoding="utf-8")
    hidden_id = _gaia_points()[0]["id"]
    (tmp_path / "task/task.yaml").write_text(
        f"instruction: leaked {hidden_id}\n", encoding="utf-8",
    )
    hits = participant_leakage_hits(tmp_path, _gaia_points())
    assert hits == [{
        "path": str(tmp_path / "task/task.yaml"),
        "hidden_identifier": hidden_id,
    }]


def test_participant_strategy_hint_scan_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "task").mkdir()
    (tmp_path / "task/task.yaml").write_text(
        "instruction: cancel work that is no longer useful\n", encoding="utf-8",
    )
    assert participant_strategy_leakage_hits(tmp_path) == [{
        "path": str(tmp_path / "task/task.yaml"),
        "procedural_hint": "cancel work that is no longer useful",
    }]
