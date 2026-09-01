import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:d9b7c649-c975-4f53-88f5-940b29c47247" and r["native_evaluator"]=="compare_table"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="Desktop/report.xlsx contains the latest five Daily-folder messages in chronological order with exact sender, subject, CC and attachment fields."
def test_report_path_and_headers():
    state=_result()["state"]; assert state["output_path"]=="/home/oai/share/report.xlsx"; assert state["headers"]==["sender_name","sender_address","subject","CC","number_of_attachments"]

def test_latest_five_chronological_order():
    state=_result()["state"]; assert state["row_count"]==5; assert state["chronological_subject_dates"]==["25 JAN 2024","27 JAN 2024","28 JAN 2024","29 JAN 2024","30 JAN 2024"]

def test_mail_rows():
    rows=_result()["state"]["rows"]; assert len(rows)==5
    assert [r["subject"] for r in rows]==["HKU Daily Email Digest (25 JAN 2024)","HKU Daily Notices (27 JAN 2024)","HKU Daily Notices (28 JAN 2024)","HKU Daily Email Digest (29 JAN 2024)","HKU Daily Email Digest (30 JAN 2024)"]
    assert [r["number_of_attachments"] for r in rows]==[0,0,0,0,0]
    assert rows[0]["CC"] is None and rows[1]["CC"]=="mail.service@intranet.hku.hk"

