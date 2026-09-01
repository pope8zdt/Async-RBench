import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:415ef462-bed3-493a-ac36-ca8c6d23bf1b" and r["native_evaluator"]=="compare_table + check_list"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="The December AWS invoice is saved as aws-invoice-2312.pdf and the tally ends with AWS, 2023.12, 10.02."
def test_invoice_output_paths():
    state=_result()["state"]; assert state["receipt_path"]=="/home/oai/share/receipts/aws-invoice-2312.pdf"; assert state["tally_path"]=="/home/oai/share/tally_book.xlsx"

def test_invoice_pdf_evidence():
    state=_result()["state"]; assert state["receipt_sha256"]=="db1e923997754a453688e60bcda8845a6bb2bb31e60d1997424633ce4e086983"; assert state["billing_period"]=="2023-12-01/2023-12-31"; assert state["prior_receipt_count"]==5

def test_tally_row():
    state=_result()["state"]; assert state["service"]=="AWS" and state["month"]==2023.12 and state["amount"]==10.02

