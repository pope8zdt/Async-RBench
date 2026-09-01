import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:716a6079-22da-47f1-ba73-c9d58f986a38" and r["native_evaluator"]=="is_in_vm_clickboard"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="The unique secret.docx is found at /home/user/Data3/List3/secret.docx and the clipboard contains exactly that canonical path."
def test_filename():
 assert _result()['state']['filename']=='secret.docx'
def test_unique_match():
 s=_result()['state'];assert s['match_count']==1 and s['unique_match'] is True
def test_canonical_path():
 s=_result()['state'];assert s['canonical_path'] is True and s['exact_path']=='/home/user/Data3/List3/secret.docx'
def test_clipboard():
 assert _result()['state']['clipboard_text']=='/home/user/Data3/List3/secret.docx'
def test_asset_identity():
 assert _result()['state']['source_asset_sha256']=='4c7d705e6e7f335fd569efd248106efdf051e21d09f415c9246208d922e09e51'
