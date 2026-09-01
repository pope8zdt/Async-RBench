import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:gimp:734d6579-c07d-47a8-9ae2-13339795476b" and r["native_evaluator"]=="check_green_background"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="The exported green_background_with_object.png changes only the background to RGB green while preserving the object layer and passes check_green_background."
def test_canvas():
 s=_result()['state'];assert (s['canvas_width'],s['canvas_height'])==(800,800)
def test_green_rgb():
 assert _result()['state']['background_rgb']==[0,255,0]
def test_object_preserved():
 assert _result()['state']['object_layer_unchanged'] is True
def test_background_only():
 assert _result()['state']['background_only_changed'] is True
def test_green_evaluator():
 assert _result()['state']['green_background_check_passed'] is True
