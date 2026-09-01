#!/usr/bin/env python3
"""Record the integrated-fix verdict once every module group has been re-run.

The integrated fix is the point at which the final fix revision is verified
against every module group at once. This script reads the final fix record
(applied_fix.json) and the final per-group reports, then writes
/app/output_data/integrated_fix.json.

It is meant to run AFTER the last module-group pass; it fails loudly if any
group's final report is missing or not passing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

OUT_DIR = Path("/app/output_data")
GROUPS = ["A", "B", "C"]
GROUPS_OUT = OUT_DIR / "module_groups"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run() -> int:
    applied = _load(OUT_DIR / "applied_fix.json")
    revision = applied["fix_revision"]

    integrated_groups: list[str] = []
    for group in GROUPS:
        report = _load(GROUPS_OUT / f"{group}_result.json")
        if report.get("passed") is not True:
            print(f"error: group {group} final report is not passing")
            return 1
        if report.get("run_revision") != revision:
            print(
                f"error: group {group} report revision {report.get('run_revision')} "
                f"does not match final fix revision {revision}"
            )
            return 1
        integrated_groups.append(group)

    report = {
        "fix_revision": revision,
        "integrated_groups": integrated_groups,
        "report_path": str(OUT_DIR / "integrated_fix.json"),
    }
    (OUT_DIR / "integrated_fix.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
