import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:gimp:d16c99dc-2a1e-46f2-b350-d97c86c85c15" and r["native_evaluator"]=="check_image_size+check_structure_sim_resized"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="The exported resized.png has a 512-pixel dog-layer height with preserved aspect ratio and background structure, and passes both bound OSWorld evaluators."
def test_target_height():
 assert _result()['state']['target_layer_height']==512 and _result()['state']['ignore_transparent'] is True
def test_aspect_ratio():
 assert _result()['state']['aspect_ratio_preserved'] is True
def test_structure_similarity():
 assert _result()['state']['structure_similarity_passed'] is True
def test_background_preservation():
 assert _result()['state']['background_layer_preserved'] is True
def test_output_path():
 assert _result()['state']['output_path']=='/home/user/Desktop/resized.png'
