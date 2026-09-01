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
    assert result["source_task_id"] == "osworld:chrome:121ba48f-9e17-48ce-9bc6-a4fb17a7ebba"
    assert result["native_evaluator"] == "is_added_to_steam_cart"


def test_official_score_is_one():
    assert _result()["official_score"] == 1.0


def test_native_evidence_sha256_matches_fixture():
    assert _result()["native_evidence_sha256"] == _native()["evidence_sha256"]


def test_task_assertion_is_case_specific():
    assert _result()["task_assertion"] == "The final Steam cart contains the evaluator-required Dota 2 DLC item."


def test_steam_required_item_in_cart():
    state = _result()["state"]
    assert state["game"] == "Dota 2"
    assert state["required_item"] == "The Dota 2 Official Soundtrack"
    assert state["cart_items"].count(state["required_item"]) == 1
    assert state["cart_url"] == "https://store.steampowered.com/cart/"

