import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:51f5801c-18b3-4f25-b0c3-02f85507a078" and r["native_evaluator"]=="compare_docx_files"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="notes.docx contains only the eight non-empty presenter notes in source slide order, with no page numbers or added formatting."
def test_output_path(): assert _result()["state"]["output_path"]=="/home/user/Desktop/notes.docx"
def test_slide_coverage():
 s=_result()["state"];assert s["slide_count"]==9 and s["note_slide_indices"]==[1,2,3,4,5,6,8,9] and s["note_count"]==8
def test_note_order():
 s=_result()["state"];assert s["notes"]==["This is opening slide.","Cover slide option #1","Cover slide option #3","This is a graph.","This is a table.","This is item lists.","This is an inserted image.","Blank ending slide"] and s["notes_joined_sha256"]=="c9af232221b684a6e20d82fcf864f7817e828103d29cf0c98d8b2994386fda1d"
def test_plain_text_only():
 s=_result()["state"];assert s["plain_text_only"] is True and s["page_numbers_added"] is False and s["formatting_added"] is False
def test_gold_fidelity(): assert _result()["state"]["gold_docx_sha256"]=="184938c001aa31191fef4859698273f73a4c3ab3c3f105d44c02962a453a1eab"
