#!/usr/bin/env python3
"""Public scanner for the raw object database.

Runs `git fsck --lost-found` over the raw object database and inspects every
dangling object (commit, tree, blob).

Writes /app/output_data/scan_reports/object_db.json (found=true with the
object_id, the recovered secret, and its sha256) and prints the report.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

REPO = "/app/repo"
OUT = "/app/output_data/scan_reports"
SECRET_RE = re.compile(r"secret\[[^\]]*\]")
AUTHORITY_PATH = "/app/task_file/events/object_authority.json"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, cwd=REPO)


def _dangling_object_ids() -> list[str]:
    result = _run("git", "fsck", "--lost-found")
    ids = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "dangling":
            ids.append(parts[-1])
    return ids


def _blob_contents(oid: str) -> list[tuple[str, str]]:
    """Return (blob_oid, content) pairs for every blob reachable from a dangling
    commit or tree. The secret lives in a BLOB (a reset-away file), not in the
    dangling commit's own metadata, so a scan of commit messages alone would
    miss it."""
    otype = _run("git", "cat-file", "-t", oid).stdout.strip()
    if otype == "blob":
        return [(oid, _run("git", "cat-file", "-p", oid).stdout)]
    if otype not in ("commit", "tree"):
        return []
    listing = _run("git", "ls-tree", "-r", oid)
    blobs = []
    for line in listing.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] == "blob":
            blobs.append((parts[2], _run("git", "cat-file", "-p", parts[2]).stdout))
    return blobs


def main() -> int:
    with open(AUTHORITY_PATH, encoding="utf-8") as handle:
        authority_receipt = json.load(handle)["authority_receipt"]
    revision = _run("git", "rev-parse", "HEAD").stdout.strip()
    found = False
    object_id = None
    secret = None
    for oid in _dangling_object_ids():
        for blob_oid, content in _blob_contents(oid):
            match = SECRET_RE.search(content)
            if match:
                found = True
                object_id = blob_oid
                secret = match.group(0)
                break
        if found:
            break
    report = {
        "scan_kind": "object_db",
        "found": found,
        "object_id": object_id,
        "secret": secret,
        "secret_hash": hashlib.sha256(secret.encode()).hexdigest() if secret else None,
        "authority_receipt": authority_receipt,
        "scan_revision": revision,
        "note": "raw object-database scan using git fsck --lost-found",
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "object_db.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
