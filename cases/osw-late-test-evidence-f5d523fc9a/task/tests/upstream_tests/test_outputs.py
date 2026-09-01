import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:2373b66a-092d-44cb-bfd7-82e86e7a3b4d" and r["native_evaluator"]=="file_contains+check_line_number"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="Desktop/System_Resources_Report.txt records 30 one-second sar CPU samples with CPU, %user, %nice, %system, %iowait, %steal, and %idle labels and satisfies the official line-count check."
def test_report_path():
 assert _result()['state']['output_path']=='/home/user/Desktop/System_Resources_Report.txt'
def test_sampling_contract():
 s=_result()['state'];assert s['interval_seconds']==1 and s['sample_count']==30 and s['command']=='sar -u 1 30'
def test_required_labels():
 s=_result()['state'];assert s['labels_present'] is True and s['required_labels']==['CPU','%user','%nice','%system','%iowait','%steal','%idle']
def test_line_count():
 s=_result()['state'];assert s['official_line_count']==31 and s['line_count_check_passed'] is True
