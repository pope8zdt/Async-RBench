#!/usr/bin/env python3
"""Reference solution for the gaia2-stockholm-moveout case (oracle material).

Runs the deterministic app-simulation flow and produces the correct submitted
deliverables under the output root:

  * saved_list_final.json      corrected saved list + every matching late addition
  * notifications.jsonl        exactly one Messages notification per matching late listing
  * event_monitor_report.json  per-event evaluation + window closure + final state
  * decision_manifest.json     initial plan, late event evaluations, closure, final state
  * planned_ops.json           the initial saved-list operation plan (intermediate)

This is benchmark-maintenance material. It never ships to the participant image
and it deliberately encodes the expected answers (which listings match, how many
notifications are owed) that must stay hidden from the participant.

The flow is fully deterministic: it reads the public app files and the public
event feed directly, and produces the same output for both execution modes
because scheduling changes control flow, never the task's correct final state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "task_file"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def matches(city: str, price: int, prefs: dict) -> bool:
    return (
        city == prefs["city"]
        and prefs["min_rent_sek"] <= price <= prefs["max_rent_sek"]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", default=str(ROOT))
    parser.add_argument("--output-root", default="/app/output_data")
    args = parser.parse_args()
    task_root = Path(args.task_root)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(task_root / "scripts"))
    from send_message import send_notification  # noqa: E402

    app = task_root / "app"
    feed_dir = task_root / "event_feed"

    saved = load_json(app / "raf_saved_list.json")
    catalog = load_json(app / "raf_catalog.json")
    contact = load_json(app / "contacts.json")
    prefs = saved["search_preferences"]
    linnea = contact["contacts"][0]
    assert linnea["budget_sek"] == prefs["max_rent_sek"], "budget must equal the saved-search upper bound"

    saved_entries = {entry["id"]: entry for entry in saved["saved"]}
    catalog_entries = {entry["id"]: entry for entry in catalog["catalog"]}

    # --- step 1: corrected initial saved list (before any late listing) -------
    removed_ids: list[str] = []
    kept: dict[str, dict] = {}
    for entry in saved["saved"]:
        if entry["city"] == prefs["city"] and not (
            prefs["min_rent_sek"] <= entry["price_sek"] <= prefs["max_rent_sek"]
        ):
            removed_ids.append(entry["id"])
        else:
            kept[entry["id"]] = dict(entry)
    added_ids: list[str] = []
    for entry in catalog["catalog"]:
        if entry["city"] != prefs["city"]:
            continue
        if not (prefs["min_rent_sek"] <= entry["price_sek"] <= prefs["max_rent_sek"]):
            continue
        if entry["id"] in kept or entry["id"] in saved_entries:
            continue
        kept[entry["id"]] = dict(entry)
        added_ids.append(entry["id"])
    corrected_ids = sorted(kept)

    initial_plan = {
        "corrected_saved_ids": corrected_ids,
        "removed_ids": sorted(removed_ids),
        "added_ids": sorted(added_ids),
    }
    (output_root / "planned_ops.json").write_text(
        json.dumps({"initial_plan": initial_plan, "planned_saved_ids": corrected_ids}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # --- step 2: monitor the feed; evaluate every late listing ----------------
    feed = load_jsonl(feed_dir / "feed.jsonl")
    stream_revision = hashlib.sha256((feed_dir / "feed.jsonl").read_bytes()).hexdigest()
    feed.sort(key=lambda event: int(event["seq"]))
    observations: list[dict] = []
    late_evaluations: list[dict] = []
    final_saved: dict[str, dict] = dict(kept)
    notified: list[str] = []

    for event in feed:
        listing = event["listing"]
        is_match = matches(listing["city"], listing["price_sek"], prefs)
        if is_match:
            final_saved[listing["id"]] = dict(listing)
            disposition = "added_and_notified"
            reason = "Stockholm listing within the friend's saved-search rent range"
            send_notification(
                linnea["name"], listing["id"], listing["name"], listing["price_sek"],
                event["at"], output_root,
            )
            notified.append(listing["id"])
        else:
            disposition = "ignored"
            if listing["city"] != prefs["city"]:
                reason = "listing city is not the friend's saved-search city"
            elif listing["price_sek"] > prefs["max_rent_sek"]:
                reason = "listing rent exceeds the friend's saved-search upper bound"
            else:
                reason = "listing rent is below the friend's saved-search lower bound"
        observations.append({
            "seq": int(event["seq"]),
            "listing_id": listing["id"],
            "at": int(event["at"]),
            "matched": is_match,
            "disposition": disposition,
            "reason": reason,
        })
        late_evaluations.append({
            "seq": int(event["seq"]),
            "listing_id": listing["id"],
            "matched": is_match,
            "action": disposition,
        })

    final_saved_ids = sorted(final_saved)
    (output_root / "saved_list_final.json").write_text(
        json.dumps({
            "owner": saved["owner"],
            "search_preferences": prefs,
            "saved": [final_saved[eid] for eid in sorted(final_saved)],
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # --- step 3: reports and manifest ------------------------------------------
    (output_root / "event_monitor_report.json").write_text(
        json.dumps({
            "feed": str(feed_dir / "feed.jsonl"),
            "stream_revision": stream_revision,
            "window_minutes": load_json(feed_dir / "feed_meta.json").get("window_minutes"),
            "observed_events": observations,
            "window_closed": True,
            "final_saved_ids": final_saved_ids,
            "notifications_sent": notified,
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "initial_plan": initial_plan,
        "late_event_evaluations": late_evaluations,
        "authority_stream_revision": stream_revision,
        "wait_for_window_closed": True,
        "final_saved_ids": final_saved_ids,
        "notifications_sent": notified,
        "closure_verified": True,
    }
    (output_root / "decision_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"corrected initial saved ids: {corrected_ids}")
    print(f"matching late listings notified: {notified}")
    print(f"final saved ids: {final_saved_ids}")
    print(f"notifications written to {output_root / 'notifications.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
