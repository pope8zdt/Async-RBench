"""Frozen semantic outcome checks for the gaia2-stockholm-moveout case.

Each registered pytest function is one leaderboard point. The tests derive the
expected state from the public app files and the deterministic event feed
(which the participant and the verifier both see), then compare the submitted
deliverables under the output root against that derivation. The two-message
notification expectation and the identity of the matching listings are never
baked into the participant image; they are re-derived here from the public
apps, exactly as the reference solution derives them.
"""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path

TASK = Path(os.environ.get("ASYNC_RBENCH_TASK_ROOT", "/app/task_file"))
OUTPUT = Path(os.environ.get("ASYNC_RBENCH_OUTPUT_ROOT", "/app/output_data"))
APP = TASK / "app"
FEED = TASK / "event_feed"

BASE_OUTPUT_FILES = (
    "saved_list_final.json",
    "notifications.jsonl",
    "event_monitor_report.json",
    "decision_manifest.json",
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _saved_app() -> dict:
    return _json(APP / "raf_saved_list.json")


def _catalog_app() -> dict:
    return _json(APP / "raf_catalog.json")


def _contacts_app() -> dict:
    return _json(APP / "contacts.json")


def _feed_events() -> list[dict]:
    events = _jsonl(FEED / "feed.jsonl")
    events.sort(key=lambda event: int(event["seq"]))
    return events


def _prefs() -> dict:
    return _saved_app()["search_preferences"]


def _linnea() -> dict:
    return _contacts_app()["contacts"][0]


def _corrected_initial_ids() -> set[str]:
    """Re-derive the corrected initial saved list from the public apps."""
    prefs = _prefs()
    saved_ids = {entry["id"] for entry in _saved_app()["saved"]}
    result: set[str] = set()
    for entry in _saved_app()["saved"]:
        if entry["city"] == prefs["city"] and not (
            prefs["min_rent_sek"] <= entry["price_sek"] <= prefs["max_rent_sek"]
        ):
            continue  # out-of-range Stockholm saved listing is removed
        result.add(entry["id"])
    for entry in _catalog_app()["catalog"]:
        if (
            entry["city"] == prefs["city"]
            and prefs["min_rent_sek"] <= entry["price_sek"] <= prefs["max_rent_sek"]
            and entry["id"] not in saved_ids
        ):
            result.add(entry["id"])  # unsaved in-range Stockholm listing is added
    return result


def _expected_removed_ids() -> set[str]:
    prefs = _prefs()
    return {
        entry["id"] for entry in _saved_app()["saved"]
        if entry["city"] == prefs["city"] and not (
            prefs["min_rent_sek"] <= entry["price_sek"] <= prefs["max_rent_sek"]
        )
    }


def _expected_added_ids() -> set[str]:
    prefs = _prefs()
    saved_ids = {entry["id"] for entry in _saved_app()["saved"]}
    return {
        entry["id"] for entry in _catalog_app()["catalog"]
        if entry["city"] == prefs["city"]
        and prefs["min_rent_sek"] <= entry["price_sek"] <= prefs["max_rent_sek"]
        and entry["id"] not in saved_ids
    }


def _matching_feed_events() -> list[dict]:
    prefs = _prefs()
    return [
        event for event in _feed_events()
        if event["listing"]["city"] == prefs["city"]
        and prefs["min_rent_sek"] <= event["listing"]["price_sek"] <= prefs["max_rent_sek"]
    ]


def _matching_feed_ids() -> list[str]:
    return [event["listing"]["id"] for event in _matching_feed_events()]


def _final_saved_ids() -> set[str]:
    saved = _json(OUTPUT / "saved_list_final.json")
    return {entry["id"] for entry in saved["saved"]}


def _notifications() -> list[dict]:
    return _jsonl(OUTPUT / "notifications.jsonl")


def _report() -> dict:
    return _json(OUTPUT / "event_monitor_report.json")


def _manifest() -> dict:
    return _json(OUTPUT / "decision_manifest.json")


# ---- base_task_completion (case1_s1) --------------------------------------
def test_output_files_exist():
    for name in BASE_OUTPUT_FILES:
        assert (OUTPUT / name).is_file(), f"missing deliverable {name}"


def test_saved_list_well_formed():
    saved = _json(OUTPUT / "saved_list_final.json")
    assert isinstance(saved.get("saved"), list) and saved["saved"]
    for entry in saved["saved"]:
        assert entry["id"] and entry["name"] and entry["city"]
        assert isinstance(entry["price_sek"], int)


def test_out_of_range_stockholm_removed():
    final = _final_saved_ids()
    removed = _expected_removed_ids()
    assert removed, "fixture must contain an out-of-range Stockholm saved listing"
    assert removed.isdisjoint(final)


def test_in_range_unsaved_stockholm_added():
    final = _final_saved_ids()
    added = _expected_added_ids()
    assert added, "fixture must contain an unsaved in-range Stockholm catalog listing"
    assert added <= final


# ---- late listing integration (case1_s2) -----------------------------------
def test_vasastan_serenity_added():
    matching = _matching_feed_ids()
    assert matching and matching[0] == "apt-sthlm-vasastan"
    assert "apt-sthlm-vasastan" in _final_saved_ids()


def test_sodermalm_heaven_added():
    matching = _matching_feed_ids()
    assert len(matching) >= 2 and matching[1] == "apt-sthlm-sodermalm"
    assert "apt-sthlm-sodermalm" in _final_saved_ids()


def test_matching_additions_preserve_metadata():
    saved = {entry["id"]: entry for entry in _json(OUTPUT / "saved_list_final.json")["saved"]}
    for event in _matching_feed_events():
        listing = event["listing"]
        entry = saved[listing["id"]]
        assert entry["price_sek"] == listing["price_sek"]
        assert entry["city"] == listing["city"] == _prefs()["city"]


def test_no_duplicate_saved_ids():
    final = _final_saved_ids()
    assert len(final) == len(
        [entry["id"] for entry in _json(OUTPUT / "saved_list_final.json")["saved"]]
    )


# ---- selective notification (case1_s3 / case1_s4) --------------------------
def test_exactly_two_notifications():
    notifications = _notifications()
    expected = _matching_feed_ids()
    assert len(expected) == 2, "fixture must produce exactly two matching late listings"
    assert len(notifications) == 2


def test_first_notification_names_vasastan():
    notifications = _notifications()
    assert notifications[0]["listing_id"] == "apt-sthlm-vasastan"
    assert notifications[0]["apartment"] == "Vasastan Serenity"
    assert notifications[0]["price_sek"] == 1800


def test_second_notification_names_sodermalm():
    notifications = _notifications()
    assert notifications[1]["listing_id"] == "apt-sthlm-sodermalm"
    assert notifications[1]["apartment"] == "Södermalm Heaven"
    assert notifications[1]["price_sek"] == 1600


def test_no_message_for_stockholm_lofts():
    notified = {notification["listing_id"] for notification in _notifications()}
    assert "apt-sthlm-lofts" not in notified


def test_no_message_for_other_decoys():
    notified = {notification["listing_id"] for notification in _notifications()}
    for listing_id in ("apt-sthlm-luxe", "apt-sthlm-nordic", "apt-gbg-condo"):
        assert listing_id not in notified


def test_notifications_addressed_to_linnea():
    for notification in _notifications():
        assert notification["recipient"] == _linnea()["name"]


# ---- event evaluation / monitoring (case1_s4) ------------------------------
def test_event_monitor_report_exists():
    report = _report()
    assert isinstance(report.get("observed_events"), list)
    assert report.get("window_closed") is True
    assert report.get("stream_revision") == hashlib.sha256(
        (FEED / "feed.jsonl").read_bytes()
    ).hexdigest()


def test_all_six_events_evaluated():
    report = _report()
    observed = report["observed_events"]
    feed = _feed_events()
    assert len(observed) == len(feed) == 6
    assert [int(event["seq"]) for event in observed] == [int(event["seq"]) for event in feed]


def test_matching_events_acted():
    report = _report()
    matched = {event["listing_id"] for event in report["observed_events"] if event["matched"]}
    assert matched == set(_matching_feed_ids())
    for event in report["observed_events"]:
        if event["matched"]:
            assert event["disposition"] == "added_and_notified"


def test_decoys_ignored():
    report = _report()
    for event in report["observed_events"]:
        if event["listing_id"] not in set(_matching_feed_ids()):
            assert event["matched"] is False
            assert event["disposition"] == "ignored"
            assert event.get("reason")


# ---- consistency closure (case1_s5) ----------------------------------------
def test_final_saved_list_closure():
    expected = _corrected_initial_ids() | set(_matching_feed_ids())
    assert _final_saved_ids() == expected


def test_notifications_match_additions():
    notified = [notification["listing_id"] for notification in _notifications()]
    assert notified == _matching_feed_ids()


def test_manifest_window_closed():
    manifest = _manifest()
    assert manifest["wait_for_window_closed"] is True
    assert len(manifest["late_event_evaluations"]) == 6
    assert manifest["authority_stream_revision"] == hashlib.sha256(
        (FEED / "feed.jsonl").read_bytes()
    ).hexdigest()


def test_manifest_closure_verified():
    manifest = _manifest()
    assert manifest["closure_verified"] is True
    assert set(manifest["final_saved_ids"]) == _final_saved_ids()


def test_report_matches_deliverables():
    report = _report()
    assert set(report["final_saved_ids"]) == _final_saved_ids()
    assert report["notifications_sent"] == _matching_feed_ids()


def test_manifest_initial_plan_consistent():
    manifest = _manifest()
    plan = manifest["initial_plan"]
    assert set(plan["corrected_saved_ids"]) == _corrected_initial_ids()
    assert set(plan["removed_ids"]) == _expected_removed_ids()
    assert set(plan["added_ids"]) == _expected_added_ids()
