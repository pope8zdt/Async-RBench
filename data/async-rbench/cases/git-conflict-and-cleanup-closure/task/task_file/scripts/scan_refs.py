#!/usr/bin/env python3
"""Public scanner: search reachable history (refs, commit messages, diffs).

Reports whether any SECRET_TOKEN ("secret[...]") appears in history that is
reachable from any ref. Objects that are not reachable from any ref are NOT
considered here; they are covered by scan_objects.py.

Writes /app/output_data/scan_reports/ref_history.json and prints the report.
"""
import json
import os
import subprocess
import sys

REPO = "/app/repo"
OUT = "/app/output_data/scan_reports"
SECRET_PATTERN = "secret["


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, cwd=REPO)


def _scanned_refs() -> list[str]:
    result = _run("git", "for-each-ref", "--format=%(refname)")
    return [line for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    messages = _run("git", "log", "--all", "--grep", "secret\\[", "--regexp-ignore-case")
    diffs = _run("git", "log", "--all", "-p", "-S", "secret[")
    found = bool(messages.stdout.strip() or diffs.stdout.strip())
    revision = _run("git", "rev-parse", "HEAD").stdout.strip()
    report = {
        "scan_kind": "ref_history",
        "found": found,
        "scanned_refs": _scanned_refs(),
        "scan_revision": revision,
        "note": "reachable history only: commit messages (--grep) and content diffs (-S) for secret tokens",
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "ref_history.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if not found else 1


if __name__ == "__main__":
    sys.exit(main())
