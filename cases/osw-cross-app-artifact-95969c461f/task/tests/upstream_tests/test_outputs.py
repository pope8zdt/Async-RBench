import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:5bc63fb9-276a-4439-a7c1-9dc76401737f" and r["native_evaluator"]=="compare_docx_files_and_ignore_new_lines"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="gemini_results.docx contains six Gemini responses in source order and highlights all 33 Iliad occurrences."
def test_output_path(): assert _result()["state"]["output_path"]=="/home/user/Desktop/gemini_results.docx"
def test_response_coverage():
 s=_result()["state"];assert s["response_count"]==6 and s["response_lengths"]==[2781,112,1995,112,2278,1435]
def test_paragraph_order():
 s=_result()["state"];assert s["nonempty_paragraph_count"]==6 and s["source_order_preserved"] is True
def test_iliad_highlights():
 s=_result()["state"];assert s["iliad_occurrence_count"]==33 and s["highlighted_iliad_count"]==33
def test_gold_fidelity(): assert _result()["state"]["gold_docx_sha256"]=="01e3ad9bebaee3c028f7fd8635e9c6de69b4e57fd4fa5ae53447a73fd42dc0f8"

