import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:26660ad1-6ebb-4f59-8cba-a8432dfe8d38" and r["native_evaluator"]=="file_contains"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="~/Test/Speed/results.txt contains exactly one non-empty Ping, Download, and Upload metric line, each formatted as metric name, one space, then its measured value."
def test_output_path():
 assert _result()["state"]["output_path"]=="/home/user/Test/Speed/results.txt"
def test_metric_coverage():
 s=_result()["state"];assert s["metric_order"]==["Ping","Download","Upload"] and s["line_count"]==3
def test_line_format():
 s=_result()["state"];assert s["single_space_after_metric"] is True and s["all_values_nonempty"] is True;assert all(line.startswith(name+" ") and len(line.split(" ",1)[1])>0 for name,line in zip(s["metric_order"],s["metric_lines"]))
def test_service_identity():
 assert _result()["state"]["service_url"]=="https://www.speedtest.net/"

