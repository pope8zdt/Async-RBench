#!/usr/bin/env python3
"""Recover the leaked value from a participant-selected positive scan report."""

import argparse
import hashlib
import json
from pathlib import Path

SCAN_ROOT = Path("/app/output_data/scan_reports").resolve()
SECRET_PATH = Path("/app/secret.txt")
REPORT_PATH = Path("/app/output_data/recovery_report.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report_path = Path(args.report).resolve()
    if report_path.parent != SCAN_ROOT:
        raise SystemExit("--report must name a file under /app/output_data/scan_reports")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("found") is not True or not report.get("secret"):
        raise SystemExit("selected scan report does not contain a recovered value")
    secret = str(report["secret"])
    SECRET_PATH.write_text(secret + "\n", encoding="utf-8")
    recovery = {
        "secret_path": str(SECRET_PATH),
        "source_scan": report.get("scan_kind"),
        "source_object_id": report.get("object_id"),
        "secret_sha256": hashlib.sha256(secret.encode()).hexdigest(),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(recovery, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(recovery))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
