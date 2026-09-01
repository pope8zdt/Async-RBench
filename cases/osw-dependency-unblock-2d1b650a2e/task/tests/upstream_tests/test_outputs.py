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
    assert result["source_task_id"] == "osworld:chrome:030eeff7-b492-4218-b312-701ec99ee0cc"
    assert result["native_evaluator"] == "exact_match"


def test_official_score_is_one():
    assert _result()["official_score"] == 1.0


def test_native_evidence_sha256_matches_fixture():
    assert _result()["native_evidence_sha256"] == _native()["evidence_sha256"]


def test_task_assertion_is_case_specific():
    assert _result()["task_assertion"] == "The persisted Chrome profile has enable_do_not_track set to true."


def test_do_not_track_is_true():
    state = _result()["state"]
    assert state["preference"] == "enable_do_not_track"
    assert state["enabled"] is True
    assert state["persisted"] is True

