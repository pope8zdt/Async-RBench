from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import time


CASE_ID = "mab-conflicting-specialist-results-5f19377089"
SOURCE_ID = "database:011"
CHECKPOINT_SHA = "1c3a50e63e7f8a6ba73633054c752f3f4623e4fd9c68f159a44e4c3bf7bd8385"
NATIVE_EVIDENCE_SHA = "83b87e43a8e475cf654f4aaf6be405c4d8ccfb86040be4d9c600e5275d9908c0"
FINDING = "VACUUM"


def _write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/app/output_data/event_receipt.json")
    parser.add_argument(
        "--report",
        default="/app/output_data/workstreams/requirement_worker_02.json",
    )
    parser.add_argument("--workspace", default="/app")
    args = parser.parse_args()

    started = time.time()
    receipt = {
        "schema_version": "async-rbench-event-receipt-v1",
        "case_id": CASE_ID,
        "source_task_id": SOURCE_ID,
        "event": "authoritative_postgres_checkpoint",
        "worker_started_at": started,
        "worker_finished_at": time.time(),
        "worker_exit_code": 0,
        "probes": {
            "host_checkpoint_sha256": CHECKPOINT_SHA,
            "native_evidence_sha256": NATIVE_EVIDENCE_SHA,
            "selected_cause": FINDING,
        },
    }
    raw = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    receipt["receipt_sha256"] = hashlib.sha256(raw).hexdigest()

    receipt_path = pathlib.Path(args.output)
    report_path = pathlib.Path(args.report)
    report = {
        "schema_version": "async-rbench-authority-report-v1",
        "case_id": CASE_ID,
        "source_task_id": SOURCE_ID,
        "finding": FINDING,
        "revision_sha256": CHECKPOINT_SHA,
        "receipt_path": str(receipt_path),
        "receipt_sha256": receipt["receipt_sha256"],
    }
    _write_json(receipt_path, receipt)
    _write_json(report_path, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
