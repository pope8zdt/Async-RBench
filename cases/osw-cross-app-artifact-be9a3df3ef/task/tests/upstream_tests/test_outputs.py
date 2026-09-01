import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:47f7c0ce-a5fb-4100-a5e6-65cd0e7429e5" and r["native_evaluator"]=="compare_images"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="Slide 2 of Robotic_Workshop_Infographics.pptx uses the official landscape frame from 00:08.000 as its persistent background."
def test_timestamp(): assert _result()["state"]["timestamp_seconds"]==8.0
def test_frame_identity():
 s=_result()["state"];assert s["frame_size"]==[1920,1080] and s["frame_sha256"]=="9eeaa986f3d51e85bc5c21c95f4674b7e0400616d5599d63de1320b0d11fdebe"
def test_presentation_target():
 s=_result()["state"];assert s["presentation_path"]=="/home/user/Desktop/Robotic_Workshop_Infographics.pptx" and s["slide_index"]==1
def test_selective_change(): assert _result()["state"]["only_target_slide_changed"] is True
def test_persistence(): assert _result()["state"]["background_persisted"] is True

