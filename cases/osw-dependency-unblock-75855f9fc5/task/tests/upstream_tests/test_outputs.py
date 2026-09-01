import datetime
import json
from pathlib import Path

OUT = Path("/app/output_data")
NATIVE = Path("/async_rbench_tests/fixtures/native_canonical_report.json")


def _result():
    return json.loads((OUT / "osworld_native_result.json").read_text())


def _native():
    return json.loads(NATIVE.read_text())


def test_osworld_result_identity():
    result = _result()
    assert result["source_task_id"] == "osworld:chrome:2ad9387a-65d8-4e33-ad5b-7580065a27ca"
    assert result["native_evaluator"] == "is_expected_bookmarks"


def test_official_score_is_one():
    assert _result()["official_score"] == 1.0


def test_native_evidence_sha256_matches_fixture():
    assert _result()["native_evidence_sha256"] == _native()["evidence_sha256"]


def test_task_assertion_is_case_specific():
    assert _result()["task_assertion"] == "Exactly one persisted Favorites folder exists directly under Chrome bookmarks bar."


def test_favorites_unique_and_persisted():
    state = _result()["state"]
    favorites = [item for item in state["folders"] if item["name"] == "Favorites"]
    assert len(favorites) == 1
    assert favorites[0]["parent"] == "bookmark_bar"
    assert favorites[0]["persisted"] is True
    assert state["profile_reloaded"] is True

