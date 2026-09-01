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
    assert result["source_task_id"] == "osworld:chrome:9f3f70fc-5afc-4958-a7b7-3bb4fcb01805"
    assert result["native_evaluator"] == "check_url_and_content_include"


def test_official_score_is_one():
    assert _result()["official_score"] == 1.0


def test_native_evidence_sha256_matches_fixture():
    assert _result()["native_evidence_sha256"] == _native()["evidence_sha256"]


def test_task_assertion_is_case_specific():
    assert _result()["task_assertion"] == "The final catalog state is Women's Nike Jerseys with a lower price bound strictly above $60."


def test_nike_womens_jersey_filter_state():
    state = _result()["state"]
    assert state["department"] == "Women"
    assert state["brand"] == "Nike"
    assert state["product_type"] == "Jerseys"
    assert state["price_min_exclusive"] == 60
    assert state["results_page_visible"] is True

