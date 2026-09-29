#!/usr/bin/env python3
"""Public scanner: search the packed/reachable object set and the working tree.

Enumerates every blob reachable from any ref (git rev-list --objects --all),
reads each blob's content, and greps the working tree. Objects that are not
reachable from any ref (e.g. a reset-away dangling commit) are NOT reachable
through this scan; they are covered by scan_objects.py.

Writes /app/output_data/scan_reports/pack.json and prints the report.
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


def _reachable_blob_has_secret() -> bool:
    listing = _run("git", "rev-list", "--objects", "--all")
    blob_ids = []
    for line in listing.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].strip():
            blob_ids.append(parts[0])
    for blob_id in blob_ids:
        content = _run("git", "cat-file", "-p", blob_id).stdout
        if SECRET_PATTERN in content:
            return True
    return False


def _working_tree_has_secret() -> bool:
    result = subprocess.run(
        ["grep", "-rI", "--", "-e", "secret[", "."],
        capture_output=True, text=True, cwd=REPO,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def main() -> int:
    obj_found = _reachable_blob_has_secret()
    tree_found = _working_tree_has_secret()
    revision = _run("git", "rev-parse", "HEAD").stdout.strip()
    report = {
        "scan_kind": "pack",
        "found": bool(obj_found or tree_found),
        "objects_scanned": _run("git", "rev-list", "--objects", "--all").stdout.count("\n"),
        "reachable_objects_clean": not obj_found,
        "working_tree_clean": not tree_found,
        "scan_revision": revision,
        "note": "objects reachable from refs plus working-tree grep; unreachable objects excluded",
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "pack.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if not report["found"] else 1


if __name__ == "__main__":
    sys.exit(main())
