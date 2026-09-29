#!/usr/bin/env python3
"""Run the full regression suite and record its result.

The regression runs every test file in /app/task_file/tests — the three module
groups plus the smoke test — in a deterministic order, and writes a JSON report
to /app/output_data/regression_result.json carrying the per-file verdicts and
the fix-target revision the run was made against.

Exit code: 0 when the full regression passes, 1 otherwise (the report is still
written either way).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

TEST_DIR = "/app/task_file/tests"
OUT_PATH = "/app/output_data/regression_result.json"
FIX_TARGET = "/app/task_file/src/sklearn/utils/multiclass.py"

# Deterministic order: module groups A, B, C, then the smoke test.
TEST_FILES = [
    "test_classification.py",
    "test_label.py",
    "test_multiclass.py",
    "test_smoke.py",
]


def sha256_of(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def run() -> int:
    revision = sha256_of(FIX_TARGET)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    verdicts: dict[str, str] = {}
    all_passed = True
    for test_file in TEST_FILES:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--no-header",
                "-p",
                "no:cacheprovider",
                os.path.join(TEST_DIR, test_file),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        verdicts[test_file] = "pass" if proc.returncode == 0 else "fail"
        all_passed = all_passed and proc.returncode == 0

    report = {
        "passed": all_passed,
        "regression_revision": revision,
        "groups": verdicts,
        "report_path": OUT_PATH,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(run())
