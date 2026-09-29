#!/usr/bin/env python3
"""Run module group A (sklearn.metrics / test_classification) and record it.

Writes a JSON report to /app/output_data/module_groups/A_result.json with the
group name, pass/fail, the fix-target revision the run was made against
(sha256 of sklearn/utils/multiclass.py), and a report path.

Exit code: 0 when the group passes, 1 when it fails (the report is still
written either way, so a failing run is preserved and inspectable).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

GROUP = "A"
TEST_FILE = "/app/task_file/tests/test_classification.py"
OUT_PATH = "/app/output_data/module_groups/A_result.json"
FIX_TARGET = "/app/task_file/src/sklearn/utils/multiclass.py"


def sha256_of(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def run() -> int:
    revision = sha256_of(FIX_TARGET)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            TEST_FILE,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    passed = proc.returncode == 0
    tail = (proc.stdout or "") + (proc.stderr or "")
    detail = "all module-group tests passed" if passed else tail.strip()[-2000:]
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    report = {
        "group": GROUP,
        "passed": passed,
        "run_revision": revision,
        "report_path": OUT_PATH,
        "detail": detail,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(run())
