#!/usr/bin/env python3
"""Repo-wide closure verifier.

Checks that the secret is absent from (1) reachable history, (2) unreachable
objects reported by fsck, (3) the entire object database, and (4) the working
tree. Writes /app/output_data/closure_report.json and stamps the most recent
cleanup report with the result.

The report contains one boolean per inspected repository surface.
"""
import json
import os
import subprocess
import sys

REPO = "/app/repo"
SECRET_PATTERN = "secret["
CLOSURE_PATH = "/app/output_data/closure_report.json"
CLEANUP_DIR = "/app/output_data/cleanup_reports"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, cwd=REPO)


def _reachable_history_clean() -> bool:
    messages = _run("git", "log", "--all", "--grep", "secret\\[", "--regexp-ignore-case")
    diffs = _run("git", "log", "--all", "-p", "-S", "secret[")
    return not (messages.stdout.strip() or diffs.stdout.strip())


def _dangling_blob_contents(oid: str) -> list[str]:
    """Blob contents reachable from a dangling commit/tree (the secret lives in
    a blob, not in commit metadata), plus the object itself if it is a blob."""
    otype = _run("git", "cat-file", "-t", oid).stdout.strip()
    if otype == "blob":
        return [_run("git", "cat-file", "-p", oid).stdout]
    if otype not in ("commit", "tree"):
        return []
    listing = _run("git", "ls-tree", "-r", oid)
    return [_run("git", "cat-file", "-p", line.split()[2]).stdout
            for line in listing.stdout.splitlines()
            if len(line.split()) >= 4 and line.split()[1] == "blob"]


def _unreachable_objects_clean() -> bool:
    result = _run("git", "fsck", "--lost-found")
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "dangling":
            if any(SECRET_PATTERN in content for content in _dangling_blob_contents(parts[-1])):
                return False
    return True


def _all_objects_clean() -> bool:
    listing = _run("git", "cat-file", "--batch-all-objects", "--batch-check=%(objectname)")
    for oid in listing.stdout.split():
        content = _run("git", "cat-file", "-p", oid).stdout
        if SECRET_PATTERN in content:
            return False
    return True


def _working_tree_clean() -> bool:
    result = subprocess.run(
        ["grep", "-rI", "--", "-e", "secret[", "."],
        capture_output=True, text=True, cwd=REPO,
    )
    return not (result.returncode == 0 and bool(result.stdout.strip()))


def _stamp_cleanup_reports(closed: bool) -> None:
    if not os.path.isdir(CLEANUP_DIR):
        return
    attempts = []
    for name in os.listdir(CLEANUP_DIR):
        if name.endswith(".json"):
            try:
                with open(os.path.join(CLEANUP_DIR, name), encoding="utf-8") as handle:
                    attempts.append((int(name[:-5]), json.load(handle)))
            except (ValueError, OSError, json.JSONDecodeError):
                continue
    if not attempts:
        return
    _, latest = max(attempts, key=lambda pair: pair[0])
    latest["verified"] = bool(closed)
    latest["closed_at_verify"] = bool(closed)
    with open(os.path.join(CLEANUP_DIR, f"{latest['attempt']}.json"), "w", encoding="utf-8") as handle:
        json.dump(latest, handle, indent=2)


def main() -> int:
    checks = {
        "reachable_history_clean": _reachable_history_clean(),
        "unreachable_objects_clean": _unreachable_objects_clean(),
        "all_objects_clean": _all_objects_clean(),
        "working_tree_clean": _working_tree_clean(),
    }
    closed = all(checks.values())
    _stamp_cleanup_reports(closed)
    report = {"closed": closed, "checks": checks}
    os.makedirs(os.path.dirname(CLOSURE_PATH), exist_ok=True)
    with open(CLOSURE_PATH, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if closed else 1


if __name__ == "__main__":
    sys.exit(main())
