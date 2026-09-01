import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:42f4d1c7-4521-4161-b646-0a8934e36081" and r["native_evaluator"]=="is_extension_installed+check_image_size"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="A VS Code extension identifier containing lisp is installed and /home/user/Desktop/resized.png has official width and height 128×128."
def test_source_image():
 s=_result()["state"];assert s["source_sha256"]=="d02270af65b8fddd0891dadc299548ffde1a3067ea1f0f0c7b7c61f542a70de3" and s["source_dimensions"]==[1280,1280]
def test_lisp_extension():
 s=_result()["state"];assert s["extension_installed"] is True and "lisp" in s["extension_match"].lower()
def test_output_path():
 assert _result()["state"]["output_path"]=="/home/user/Desktop/resized.png"
def test_resize_dimensions():
 s=_result()["state"];assert s["output_dimensions"]==[128,128] and s["output_image_valid"] is True

