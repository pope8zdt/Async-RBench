import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:a503b07f-9119-456b-b75d-f5146737d24f" and r["native_evaluator"]=="compare_pdf_images"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="Desktop/receipt.pdf is a one-page PDF whose rendered image matches the source receipt OIP.jpg."
def test_receipt_paths():
    state=_result()["state"]; assert state["source_path"]=="/home/user/OIP.jpg"; assert state["output_path"]=="/home/user/Desktop/receipt.pdf"

def test_receipt_pdf_page_count():
    assert _result()["state"]["pdf_pages"]==1

def test_receipt_pdf_fidelity():
    state=_result()["state"]; assert state["source_image_sha256"]=="cd99e73cde26b1578108f9505825aa18f7dd888c01bd1687dd49a540a10b46d2"; assert state["expected_pdf_sha256"]=="6d2524495695df066348adf65d5b61c72de7dde6edd07fe75c546d88022643ca"; assert state["image_content_matches"] is True

