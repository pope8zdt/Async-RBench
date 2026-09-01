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
    assert result["source_task_id"] == "osworld:chrome:1704f00f-79e6-43a7-961b-cedd3724d5fd"
    assert result["native_evaluator"] == "check_direct_json_object"


def test_official_score_is_one():
    assert _result()["official_score"] == 1.0


def test_native_evidence_sha256_matches_fixture():
    assert _result()["native_evidence_sha256"] == _native()["evidence_sha256"]


def test_task_assertion_is_case_specific():
    assert _result()["task_assertion"] == "The final rental state uses Zürich, a Monday-to-Friday interval, large category, and PRICE sorting."


def test_zurich_relative_date_interval():
    state = _result()["state"]
    pickup = datetime.date.fromisoformat(state["pickup_date"])
    returned = datetime.date.fromisoformat(state["return_date"])
    assert state["timezone"] == "Europe/Zurich"
    assert state["location"] == "Zürich" and state["drop_location"] == "Zürich"
    assert state["car_category"] == "large" and state["sort_by"] == "PRICE"
    assert pickup.weekday() == 0 and returned.weekday() == 4
    assert (returned - pickup).days == 4

