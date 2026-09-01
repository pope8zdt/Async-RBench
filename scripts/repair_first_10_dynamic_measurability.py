#!/usr/bin/env python3
"""Repair the first ten packages after the dynamic-measurability pilot.

The original materializer emitted a non-result causal root event plus a
separate ``.authority_result`` delivery.  The runtime scheduler drains only
result-bearing events, so the contract root could never be observed.  This
migration folds the stimulus metadata and causal boundary into the authority
delivery and makes the semantic anchor diagnostic-only for control scoring.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "candidate_cases" / "rebuild-batch-001"


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    # JSON is a strict YAML subset and matches the existing first-10 private
    # package style while keeping deterministic diffs.
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _repair_private_case(path: Path) -> bool:
    private = _load(path)
    contracts = list(private.get("event_contracts") or [])
    if len(contracts) != 1:
        raise ValueError(f"{path}: expected exactly one event contract")
    event_id = str(contracts[0].get("event_id") or "")
    authority_kind = str(private.get("authoritative_result_kind") or "")
    events = list(
        ((private.get("scenarios") or {}).get("async") or {}).get("events") or []
    )
    root_matches = [item for item in events if str(item.get("id") or "") == event_id]
    authority_matches = [
        item for item in events if str(item.get("result") or "") == authority_kind
    ]
    if len(root_matches) != 1 or len(authority_matches) != 1:
        raise ValueError(
            f"{path}: expected one root event and one authority event; "
            f"found {len(root_matches)} and {len(authority_matches)}"
        )
    root_event = root_matches[0]
    authority_event = authority_matches[0]
    changed = False
    if root_event is not authority_event:
        authority_index = events.index(authority_event)
        merged = dict(authority_event)
        merged["id"] = event_id
        merged["result"] = authority_kind
        merged.pop("at", None)
        stimulus_type = str(root_event.get("type") or "")
        if stimulus_type and stimulus_type != "result_delivery":
            merged["stimulus_type"] = stimulus_type
        for key, value in root_event.items():
            if key not in {"id", "type"}:
                merged[key] = value
        merged["id"] = event_id
        merged["result"] = authority_kind
        events = [
            item for item in events if item is not root_event and item is not authority_event
        ]
        events.insert(min(authority_index, len(events)), merged)
        private["scenarios"]["async"]["events"] = events
        changed = True
    root = next(item for item in events if str(item.get("id") or "") == event_id)
    if str(root.get("result") or "") != authority_kind:
        raise ValueError(f"{path}: repaired root is not authority-bearing")
    if not root.get("invalidates_artifacts") or not root.get("reopens_milestones"):
        raise ValueError(f"{path}: causal authority delivery lacks invalidation semantics")
    if changed:
        _write(path, private)
    return changed


def _make_control_anchors_diagnostic(path: Path) -> int:
    payload = _load(path)
    points = payload.get("checks")
    if not isinstance(points, list):
        points = payload.get("points")
    if not isinstance(points, list):
        raise ValueError(f"{path}: expected checks or points")
    changed = 0
    for point in points:
        if point.get("requires_outcome_anchor") is not False:
            point["requires_outcome_anchor"] = False
            changed += 1
        precondition = point.get("precondition_contract")
        if isinstance(precondition, dict) and precondition.get("on_missing") != "fail_point":
            precondition["on_missing"] = "fail_point"
            changed += 1
    if changed:
        _write(path, payload)
    return changed


def repair_case(case_dir: Path) -> dict[str, Any]:
    event_changed = _repair_private_case(case_dir / "private/private_case.yaml")
    point_changes = 0
    for relative in (
        "task/tests/control_flow_checks.json",
        "private/dynamic_point_plan.json",
        "private/score_plan.json",
    ):
        point_changes += _make_control_anchors_diagnostic(case_dir / relative)
    return {
        "case_id": case_dir.name,
        "event_binding_changed": event_changed,
        "control_records_changed": point_changes,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    batch = args.root / "candidate_cases/rebuild-batch-001"
    manifest = json.loads((batch / "batch-manifest.json").read_text(encoding="utf-8"))
    case_ids = [str(item["case_id"]) for item in manifest["cases"]]
    rows: list[dict[str, Any]] = []
    for package_root in (batch, args.root / "cases"):
        for case_id in case_ids:
            case_dir = package_root / case_id
            if not case_dir.is_dir():
                raise FileNotFoundError(case_dir)
            rows.append({"package_root": str(package_root), **repair_case(case_dir)})
    print(json.dumps({"case_count": len(case_ids), "package_count": len(rows), "rows": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
