import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:os:5812b315-e7bd-4265-b51f-863c02174c28" and r["native_evaluator"]=="check_include_exclude"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="The charles account authenticates with the requested password, uses /home/test1 as its home, and /home/test1 is group-writable as required by the official command-line evaluator."
def test_account_identity():
 s=_result()["state"];assert s["username"]=="charles" and s["password_verified"] is True
def test_home_binding():
 assert _result()["state"]["home_directory"]=="/home/test1"
def test_access_scope():
 assert _result()["state"]["access_scope"]==["/home/test1"]
def test_permission_probe():
 s=_result()["state"];assert s["home_group_writable"] is True and s["official_success_text"]=="Password, home directory, and write permission check passed"
def test_check_script_identity():
 assert _result()["state"]["check_script_sha256"]=="fc645b23f28b3d30fd7bd0df67a8afd7b340b3a8a2d3813955dd154e91f0a97c"

