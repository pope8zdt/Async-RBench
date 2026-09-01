#!/usr/bin/env python3
"""Assemble a manifest from the scan, recovery, cleanup and closure reports."""
import hashlib
import json
import os

SECRET_PATH = "/app/secret.txt"
OUT = "/app/output_data"
SCAN_DIR = os.path.join(OUT, "scan_reports")
RECOVERY = os.path.join(OUT, "recovery_report.json")
CLOSURE = os.path.join(OUT, "closure_report.json")
CLEANUP_DIR = os.path.join(OUT, "cleanup_reports")
MANIFEST_PATH = os.path.join(OUT, "decision_manifest.json")


def _load(path: str) -> dict:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _secret_sha256() -> str | None:
    if not os.path.isfile(SECRET_PATH):
        return None
    return hashlib.sha256(open(SECRET_PATH, "rb").read().strip()).hexdigest()


def _cleanup_attempts() -> list[dict]:
    attempts = []
    if os.path.isdir(CLEANUP_DIR):
        for name in os.listdir(CLEANUP_DIR):
            if name.endswith(".json"):
                try:
                    with open(os.path.join(CLEANUP_DIR, name), encoding="utf-8") as handle:
                        attempts.append(json.load(handle))
                except (OSError, json.JSONDecodeError):
                    continue
    return sorted(attempts, key=lambda item: int(item.get("attempt", 0)))


def main() -> None:
    recovery = _load(RECOVERY)
    closure = _load(CLOSURE)
    attempts = _cleanup_attempts()
    scan_reports = []
    for name in sorted(os.listdir(SCAN_DIR)):
        if name.endswith(".json"):
            scan_reports.append(_load(os.path.join(SCAN_DIR, name)))
    scan_order = {"ref_history": 0, "pack": 1, "object_db": 2}
    scan_reports.sort(key=lambda item: scan_order.get(str(item.get("scan_kind")), 99))
    positive = [item for item in scan_reports if item.get("found") is True]
    authority = next(
        (
            item for item in positive
            if item.get("scan_kind") == recovery.get("source_scan")
        ),
        {},
    )
    negative_scans = [
        str(item.get("scan_kind")) for item in scan_reports
        if item.get("found") is False
    ]
    scan_set = [str(item.get("scan_kind")) for item in scan_reports]
    failed_attempts = [int(item["attempt"]) for item in attempts if item.get("verified") is False]
    source_scan = str(recovery.get("source_scan") or "")
    manifest = {
        "case_id": "git-conflict-and-cleanup-closure",
        "authoritative_result_kind": (
            "unreachable_object_authority"
            if source_scan == "object_db" else f"{source_scan}_scan_result"
        ),
        "superseded_result_kind": (
            f"{negative_scans[0]}_scan_result" if negative_scans else ""
        ),
        "recovery_source": source_scan,
        "authority_object_id": authority.get("object_id"),
        "authority_receipt": authority.get("authority_receipt"),
        "recovered_secret_sha256": recovery.get("secret_sha256"),
        "excluded_negative_scans": negative_scans,
        "preserved_scan_set": scan_set,
        "cleanup_attempts": len(attempts),
        "cleanup_failures": failed_attempts,
        "cleanup_redelegations": len(failed_attempts),
        "closure_verified": bool(closure.get("closed")),
        "closure_report_path": CLOSURE,
        "secret_artifact": SECRET_PATH,
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
