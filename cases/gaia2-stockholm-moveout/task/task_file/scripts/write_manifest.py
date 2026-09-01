#!/usr/bin/env python3
"""Build the case manifest from the participant's concrete output files."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path("/app/output_data")


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def main() -> int:
    planned = _load("planned_ops.json")
    saved = _load("saved_list_final.json")
    monitor = _load("event_monitor_report.json")
    notifications = [
        json.loads(line)
        for line in (OUT / "notifications.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    final_saved_ids = [item["id"] for item in saved.get("saved", [])]
    notification_ids = [item["listing_id"] for item in notifications]
    monitor_saved = list(monitor.get("final_saved_ids", []))
    monitor_notifications = list(monitor.get("notifications_sent", []))
    window_closed = monitor.get("window_closed") is True
    manifest = {
        "initial_plan": planned.get("initial_plan", {}),
        "late_event_evaluations": [
            {
                "seq": item.get("seq"),
                "listing_id": item.get("listing_id"),
                "matched": item.get("matched"),
                "action": item.get("disposition"),
            }
            for item in monitor.get("observed_events", [])
        ],
        "authority_stream_revision": monitor.get("stream_revision"),
        "wait_for_window_closed": window_closed,
        "final_saved_ids": final_saved_ids,
        "notifications_sent": notification_ids,
        "closure_verified": (
            window_closed
            and set(monitor_saved) == set(final_saved_ids)
            and monitor_notifications == notification_ids
        ),
    }
    (OUT / "decision_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
