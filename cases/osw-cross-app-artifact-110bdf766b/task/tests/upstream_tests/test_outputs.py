import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:8e116af7-7db7-4e35-a68b-b0939c066c78" and r["native_evaluator"]=="compare_table"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="The saved bookkeeping workbook preserves rows 1-8 and appends the five official expense transactions with correct running balances."
def test_bookkeeping_output_path():
    assert _result()["state"]["output_path"] == "/home/oai/share/my_bookkeeping.xlsx"

def test_existing_bookkeeping_rows_preserved():
    state=_result()["state"]; assert state["preserved_range"]=="A1:E8" and state["preserved_rows"] is True

def test_five_expense_rows():
    state=_result()["state"]; assert state["new_row_count"]==5; assert state["types"]==["Expense"]*5; assert state["amounts"]==[-186.93,-3670.0,-5.7,-154.06,-8.1]

def test_running_balances():
    assert _result()["state"]["running_balances"]==[603.07,-3066.93,-3072.63,-3226.69,-3234.79]

