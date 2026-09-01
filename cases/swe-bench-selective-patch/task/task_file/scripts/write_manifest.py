#!/usr/bin/env python3
"""Assemble a summary from the recorded fix and test artifacts.

This script reads, in order of authority:
  - /app/task_file/src/BASE_MANIFEST.json   (build-time base revisions)
  - /app/output_data/fix_initial.json       (first fix attempt, if recorded)
  - /app/output_data/applied_fix.json       (final fix, written by record_fix.py)
  - /app/output_data/module_groups/*_result.json (final per-group runs)
  - /app/output_data/module_groups/*_result_initial.json (archived first runs)
  - /app/output_data/regression_result.json (full regression)
  - /app/output_data/integrated_fix.json    (integration verdict)

It then writes /app/output_data/decision_manifest.json.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT_DIR = Path("/app/output_data")
GROUPS_OUT = OUT_DIR / "module_groups"
SRC_ROOT = Path("/app/task_file/src")
BASE_MANIFEST = SRC_ROOT / "BASE_MANIFEST.json"

GROUPS = ["A", "B", "C"]

# Non-fix modules whose base content must be preserved byte-for-byte.
# Keys are relative to the sklearn package root, matching BASE_MANIFEST.json.
PRESERVED_MODULES = [
    "metrics/_classification.py",
    "preprocessing/_label.py",
]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _maybe(path: Path) -> dict | None:
    if path.is_file():
        return _load(path)
    return None


def _group_first_status(group: str, final_report: dict) -> str:
    archived = _maybe(GROUPS_OUT / f"{group}_result_initial.json")
    source = archived if archived is not None else final_report
    return "pass" if source.get("passed") is True else "fail"


def run() -> int:
    base = _load(BASE_MANIFEST)
    base_fix_revision = base.get("utils/multiclass.py", "")
    if not base_fix_revision:
        print("error: base revision for utils/multiclass.py is missing")
        return 1

    final_fix = _maybe(OUT_DIR / "applied_fix.json")
    if final_fix is None:
        print("error: applied_fix.json missing; run record_fix.py --stage final first")
        return 1
    final_fix_revision = final_fix["fix_revision"]
    changed_files_final = final_fix.get("changed_files", [])

    initial_fix = _maybe(OUT_DIR / "fix_initial.json")
    initial_fix_revision = (
        initial_fix["fix_revision"] if initial_fix is not None else final_fix_revision
    )
    changed_files_initial = (
        initial_fix.get("changed_files", []) if initial_fix is not None else []
    )

    module_groups: dict[str, dict[str, str]] = {}
    failed_groups: list[str] = []
    passing_branches_preserved: list[str] = []
    all_final_pass = True
    for group in GROUPS:
        final_report = _maybe(GROUPS_OUT / f"{group}_result.json")
        if final_report is None:
            print(f"error: missing final report for group {group}")
            return 1
        first = _group_first_status(group, final_report)
        final = "pass" if final_report.get("passed") is True else "fail"
        module_groups[group] = {"first": first, "final": final}
        if first == "fail":
            failed_groups.append(group)
        else:
            passing_branches_preserved.append(group)
        if final != "pass":
            all_final_pass = False

    regression = _maybe(OUT_DIR / "regression_result.json")
    if regression is None:
        print("error: regression_result.json missing; run run_regression.py first")
        return 1

    repair_applied = initial_fix_revision != final_fix_revision or bool(failed_groups)
    waited_for_all_groups = all_final_pass and regression.get("passed") is True
    preserved_modules = {
        module: base.get(module, "") for module in PRESERVED_MODULES if base.get(module)
    }

    manifest = {
        "case_id": "swe-bench-selective-patch",
        "source_task_id": "scikit-learn__scikit-learn-25638",
        "authoritative_result_kind": "applied_fix",
        "superseded_result_kind": (
            f"module_group_{failed_groups[0]}_result" if failed_groups else ""
        ),
        "base_fix_revision": base_fix_revision,
        "initial_fix_revision": initial_fix_revision,
        "final_fix_revision": final_fix_revision,
        "authority_receipt": final_fix.get("authority_receipt"),
        "changed_files_initial": changed_files_initial,
        "changed_files_final": changed_files_final,
        "module_groups": module_groups,
        "failed_groups": failed_groups,
        "repair_applied": repair_applied,
        "repair_revision": final_fix_revision,
        "passing_branches_preserved": passing_branches_preserved,
        "waited_for_all_groups": waited_for_all_groups,
        "regression_passed": regression.get("passed") is True,
        "regression_revision": regression.get("regression_revision", ""),
        "regression_groups": regression.get("groups", {}),
        "preserved_modules": preserved_modules,
    }
    (OUT_DIR / "decision_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
