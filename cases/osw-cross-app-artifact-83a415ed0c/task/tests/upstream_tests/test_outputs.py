import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:98e8e339-5f91-4ed2-b2b2-12647cb134f4" and r["native_evaluator"]=="compare_docx_files"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="concat.docx contains the five project TXT files in order with no inserted separator and all text at 10 points."
def test_output_path(): assert _result()["state"]["output_path"]=="/home/user/Desktop/concat.docx"
def test_file_manifest():
 s=_result()["state"];assert s["source_files"]==["1.txt","2.txt","3.txt","4.txt","5.txt"] and s["source_file_count"]==5
def test_concat_content():
 s=_result()["state"];assert s["concatenated_char_count"]==2249 and s["concatenated_text_sha256"]=="ee5fbcad825882637452da098bc494594838b008a5a4b5363d8e91ecebb8e8e9" and s["separator"]==""
def test_font_size(): assert _result()["state"]["font_size_pt"]==10
def test_gold_fidelity(): assert _result()["state"]["gold_docx_sha256"]=="65185ab2f4c60c69e76820e0bebbf87915a11988f47b7d9d47c6d512a4d68af5"

