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
    assert result["source_task_id"] == "osworld:chrome:a96b564e-dbe9-42c3-9ccf-b4498073438a"
    assert result["native_evaluator"] == "is_expected_active_tab"


def test_official_score_is_one():
    assert _result()["official_score"] == 1.0


def test_native_evidence_sha256_matches_fixture():
    assert _result()["native_evidence_sha256"] == _native()["evidence_sha256"]


def test_task_assertion_is_case_specific():
    assert _result()["task_assertion"] == "The final active tab is the maximum-posts topic in FlightAware > General."


def test_flightaware_topic_and_url():
    state = _result()["state"]
    assert state["category"] == "FlightAware > General"
    assert state["topic_title"] == "The Banter Thread"
    assert state["topic_url"] == "https://discussions.flightaware.com/t/the-banter-thread/4412"
    assert state["active_tab_url"] == state["topic_url"]

