from __future__ import annotations

from copy import deepcopy
import json

from scripts.audit_selected_cases_to_100 import DEFAULT_CASES, DEFAULT_MANIFEST, ROOT, _read_jsonl, audit_selection


def test_selected_batch_is_absorbed_by_the_registered_registry() -> None:
    # The 82-case selection was superseded: its absorbable sources have since been
    # promoted into cases/registry.json, so re-auditing against the live registry
    # must reject exactly those rows as already registered and nothing else.
    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    report = audit_selection(manifest, _read_jsonl(DEFAULT_CASES), root=ROOT)
    assert report["summary"]["selected_count"] == 82
    assert report["summary"]["passed_count"] + report["summary"]["failed_count"] == 82
    for result in report["cases"]:
        for error in result["errors"]:
            assert (
                "source_task_id already registered" in error
                or "selection must resolve to exactly one blueprint row" in error
            ), error
    assert report["summary"]["failed_count"] > 0


def test_gate_rejects_duplicate_design_and_non_directional_control_mutation() -> None:
    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    manifest["cases"] = deepcopy(manifest["cases"][:2])
    manifest["new_case_count"] = 2
    manifest["target_task_count"] = manifest["registered_task_count_before"] + 2
    rows_by_id = {row["case_id"]: row for row in _read_jsonl(DEFAULT_CASES)}
    rows = [deepcopy(rows_by_id[item["case_id"]]) for item in manifest["cases"]]
    rows[1]["semantic_design_digest"] = rows[0]["semantic_design_digest"]
    rows[0]["negative_mutation_blueprint"][0]["must_fail"] = []

    report = audit_selection(manifest, rows, root=ROOT, registered_source_ids=set())

    assert not report["passed"]
    errors = [error for result in report["cases"] for error in result["errors"]]
    assert any("does not target its point" in error for error in errors)
    assert errors.count("semantic_design_digest is not unique within selection") == 2
