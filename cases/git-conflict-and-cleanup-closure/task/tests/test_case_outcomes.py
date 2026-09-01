"""Frozen semantic outcome checks for the git-conflict-and-cleanup-closure case.

Each registered pytest function is one leaderboard point. The tests read the
participant's scan reports, recovery report, cleanup reports, closure report and
decision manifest under /app/output_data, plus the git repository state at
/app/repo. The manifest is a self-report; these tests cross-check every
manifest claim against the actual artifacts and repo state so a hand-written
manifest cannot pass alone.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess

from pathlib import Path

OUT = Path("/app/output_data")
REPO = Path("/app/repo")
SCANS = OUT / "scan_reports"
SECRET_RE = re.compile(r"secret\[[^\]]*\]")
SECRET_SHA256 = "ab452ce3efdaa7ef9ab80bf604ffa2f5115528cb8af9a8849e3626aa4f950bbb"
AUTHORITY_RECEIPT = "gc-object-authority-7f5b1d1a9c4e42c0"

# Scaffold content that must survive the cleanup untouched (unrelated files).
SCAFFOLD = {
    "README.md": "apartment-scraping notes.",
    "docs/roadmap.md": "Q2: lease workflow",
    "src/main.py": 'print("scratch project")',
}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest() -> dict:
    return _json(OUT / "decision_manifest.json")


def _obj_db() -> dict:
    return _json(SCANS / "object_db.json")


def _ref_hist() -> dict:
    return _json(SCANS / "ref_history.json")


def _pack() -> dict:
    return _json(SCANS / "pack.json")


def _recovery() -> dict:
    return _json(OUT / "recovery_report.json")


def _closure() -> dict:
    return _json(OUT / "closure_report.json")


def _cleanup_reports() -> list[dict]:
    reports = []
    for path in sorted((OUT / "cleanup_reports").glob("*.json")):
        reports.append(_json(path))
    return sorted(reports, key=lambda item: int(item["attempt"]))


SECRET_FILE = Path("/app/secret.txt")


def _secret_sha256() -> str | None:
    if not SECRET_FILE.is_file():
        return None
    return hashlib.sha256(SECRET_FILE.read_bytes().strip()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        args, capture_output=True, text=True, cwd=REPO, check=True
    ).stdout


# ---- base_task_completion (gc.base) -------------------------------------
def test_scan_reports_exist():
    assert (SCANS / "ref_history.json").is_file()
    assert (SCANS / "pack.json").is_file()
    assert (SCANS / "object_db.json").is_file()


def test_secret_file_recovered():
    secret_path = SECRET_FILE
    assert secret_path.is_file()
    content = secret_path.read_text(encoding="utf-8").strip()
    assert content
    assert SECRET_RE.fullmatch(content)


def test_decision_manifest_valid():
    manifest = _manifest()
    for key in (
        "case_id",
        "authoritative_result_kind",
        "recovery_source",
        "authority_object_id",
        "authority_receipt",
        "recovered_secret_sha256",
        "excluded_negative_scans",
        "preserved_scan_set",
        "cleanup_attempts",
        "cleanup_failures",
        "cleanup_redelegations",
        "closure_verified",
    ):
        assert key in manifest, key


def test_repo_reachable_state_preserved():
    assert (REPO / ".git").is_dir()
    head = _git("git", "rev-parse", "--verify", "HEAD").strip()
    assert head
    log = _git("git", "log", "--all", "--format=%s")
    assert "chore: init scaffold" in log
    assert "feat: add tools script" in log


# ---- async_result_integration (gc.rec) ----------------------------------
def test_recovery_source_object_db():
    recovery = _recovery()
    manifest = _manifest()
    assert recovery["source_scan"] == "object_db"
    assert manifest["recovery_source"] == "object_db"
    assert manifest["recovery_source"] == recovery["source_scan"]


def test_authority_hash_consistent():
    # The same sha256 must appear in the authority scan, the recovery report,
    # the manifest, and the recovered file on disk — four independent writers.
    obj_db = _obj_db()
    recovery = _recovery()
    manifest = _manifest()
    assert obj_db["secret_hash"] == SECRET_SHA256
    assert recovery["secret_sha256"] == SECRET_SHA256
    assert manifest["recovered_secret_sha256"] == SECRET_SHA256
    assert _secret_sha256() == SECRET_SHA256
    assert obj_db["authority_receipt"] == AUTHORITY_RECEIPT
    assert manifest["authority_receipt"] == AUTHORITY_RECEIPT


def test_recovery_report_consistent():
    obj_db = _obj_db()
    recovery = _recovery()
    manifest = _manifest()
    assert recovery["secret_path"] == "/app/secret.txt"
    assert recovery["source_object_id"] == obj_db["object_id"]
    assert manifest["authority_object_id"] == obj_db["object_id"]


# ---- async_dynamic_replanning (gc.excl) ---------------------------------
def test_negative_scans_excluded():
    manifest = _manifest()
    recovery = _recovery()
    assert manifest["excluded_negative_scans"] == ["ref_history", "pack"]
    assert recovery["source_scan"] not in {"ref_history", "pack"}


def test_scan_set_preserved():
    # The negative scans were still run and their reports kept; only the
    # recovery was anchored on the authority.
    manifest = _manifest()
    assert manifest["preserved_scan_set"] == ["ref_history", "pack", "object_db"]
    assert (SCANS / "ref_history.json").is_file()
    assert (SCANS / "pack.json").is_file()
    assert (SCANS / "object_db.json").is_file()


def test_negative_scan_reports_negative():
    # Both negative scans genuinely found nothing in reachable history —
    # their absence is recorded, not assumed.
    ref_hist = _ref_hist()
    pack = _pack()
    assert ref_hist["found"] is False
    assert pack["found"] is False
    assert pack["reachable_objects_clean"] is True
    assert pack["working_tree_clean"] is True


def test_authority_scan_positive():
    obj_db = _obj_db()
    assert obj_db["found"] is True
    assert bool(obj_db["object_id"])
    assert bool(obj_db["secret"])
    assert bool(obj_db["secret_hash"])


def test_wait_for_authority_recorded():
    authority_path = SCANS / "object_db.json"
    recovery_path = OUT / "recovery_report.json"
    assert authority_path.stat().st_mtime_ns <= recovery_path.stat().st_mtime_ns


# ---- async_consistency_closure (gc.closure) ------------------------------
def test_cleanup_attempts_recorded():
    manifest = _manifest()
    reports = _cleanup_reports()
    assert manifest["cleanup_attempts"] >= 1
    assert len(reports) == manifest["cleanup_attempts"]
    assert {int(item["attempt"]) for item in reports} == set(
        range(1, manifest["cleanup_attempts"] + 1)
    )
    for item in reports:
        assert item["command"]
        assert item["verified"] is not None


def test_cleanup_failure_recorded():
    # The naive first attempt (git gc without expiring the reflog) cannot close
    # the repo; the verifier's closed=false must be recorded, not hidden.
    manifest = _manifest()
    assert manifest["cleanup_attempts"] >= 2
    assert manifest["cleanup_failures"] == list(range(1, manifest["cleanup_attempts"]))


def test_cleanup_redelegated():
    manifest = _manifest()
    assert manifest["cleanup_redelegations"] >= 1
    assert manifest["cleanup_redelegations"] == len(manifest["cleanup_failures"])


def test_recovery_before_cleanup():
    recovery_path = OUT / "recovery_report.json"
    reports = sorted((OUT / "cleanup_reports").glob("*.json"))
    assert reports
    assert recovery_path.stat().st_mtime_ns <= min(path.stat().st_mtime_ns for path in reports)


def test_closure_verified():
    manifest = _manifest()
    closure = _closure()
    assert closure["closed"] is True
    assert manifest["closure_verified"] is True


def test_closure_report_closed():
    assert _closure()["closed"] is True


def test_all_closure_checks_clean():
    closure = _closure()
    for check in (
        "reachable_history_clean",
        "unreachable_objects_clean",
        "all_objects_clean",
        "working_tree_clean",
    ):
        assert closure["checks"][check] is True, check


def test_cleanup_reports_consistent():
    manifest = _manifest()
    reports = _cleanup_reports()
    assert len(reports) == manifest["cleanup_attempts"]
    # The final attempt closed the repo; every earlier attempt failed closure.
    for item in reports:
        if int(item["attempt"]) == manifest["cleanup_attempts"]:
            assert item["verified"] is True
            assert item["closed_at_verify"] is True
        else:
            assert item["verified"] is False
            assert item["closed_at_verify"] is False


def test_secret_absent_reachable():
    # Nothing reachable from any ref (commit messages or content diffs) and
    # nothing in the working tree may contain the secret.
    assert not _git("git", "log", "--all", "--grep", "secret\\[", "--regexp-ignore-case").strip()
    assert not _git("git", "log", "--all", "-p", "-S", "secret[").strip()
    working = subprocess.run(
        ["grep", "-rI", "--", "-e", "secret[", "."],
        capture_output=True, text=True, cwd=REPO,
    )
    assert working.returncode != 0 or not working.stdout.strip()


def test_secret_absent_object_store():
    # The full object database (reachable and unreachable) holds no secret.
    listing = _git("git", "cat-file", "--batch-all-objects", "--batch-check=%(objectname)")
    for oid in listing.split():
        content = subprocess.run(
            ["git", "cat-file", "-p", oid],
            capture_output=True, text=True, cwd=REPO,
        ).stdout
        assert "secret[" not in content, oid


def test_unrelated_files_preserved():
    for relative, marker in SCAFFOLD.items():
        path = REPO / relative
        assert path.is_file(), relative
        assert marker in path.read_text(encoding="utf-8"), relative


def test_reachable_history_preserved():
    log = _git("git", "log", "--all", "--format=%s")
    assert "chore: init scaffold" in log
    assert "feat: add tools script" in log
    # The rewritten-away leak commit must not be reachable.
    assert "feat: add scratch notes" not in log
