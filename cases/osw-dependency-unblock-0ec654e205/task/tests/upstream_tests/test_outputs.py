import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:libreoffice_writer:88fe4b2d-3040-4c70-9a70-546a47764b48" and r["native_evaluator"]=="compare_docx_files"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="The first paragraph is split into seven sentences with one empty paragraph between adjacent sentences, while the rest of the guideline is preserved."
def test_output_path(): assert _result()["state"]["output_path"]=="/home/user/Desktop/CCCH9003_Tutorial_guidelines.docx"
def test_source_identity():
 s=_result()["state"];assert s["source_paragraph_count"]==28 and s["first_paragraph_sha256"]=="edb90f5f2a4e687c21d41502463597f5c89cb8ed488e147c849b25cf2eeba420"
def test_sentence_boundaries():
 s=_result()["state"];assert s["sentence_count"]==7 and s["between_sentence_blank_count"]==6
def test_tail_preservation():
 s=_result()["state"];assert s["tail_paragraph_count"]==27 and s["tail_preserved"] is True and s["tail_sha256"]=="e007fab6fb12af7236f1b86af30d9ca4a3d25b9df8a54f0dce817866d0b23393"
def test_accepted_gold_variants(): assert _result()["state"]["accepted_gold_sha256"]==["5d649645b9f3298dfdcce5b2943f4be7314bb23bcdf70e37288db86f81852674","7a335b4d24d47ebb37db765899a193987506a8de62fd86ce5c741a072e642a33","98fb56cedd2e1f1a3e795d9645dd2a5f2af40568c693855825b53d2d7f65f023","1b4b3e83d3bac2af3506b19e72f857c30dc21d0b6cac9efca2edfe2584e76cd9"]
