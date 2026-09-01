import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:aceb0368-56b8-4073-b70e-3dc9aee184e0" and r["native_evaluator"]=="compare_table"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="grades.xlsx preserves the schema and records the official per-question correctness matrix and totals for all ten students."
def test_output_schema():
 s=_result()["state"];assert s["output_path"]=="/home/user/exam/grades.xlsx" and s["headers"]==["Student ID","Student Name","Q1","Q2","Q3","Q4","Q5","Q6","Q7","Q8","Q9","Q10","Total Grade"]
def test_answer_key(): assert _result()["state"]["answer_key"]==["D","A","C","D","B","C","C","D","D","D"]
def test_score_matrix():
 s=_result()["state"];assert s["student_count"]==10 and s["remaining_students_scored"]==9 and [r[3] for r in s["rows"]]==[70,70,70,80,80,60,60,90,50,100]
def test_totals():
 assert all(r[3]==10*sum(r[2]) for r in _result()["state"]["rows"])
def test_preservation():
 r=_result()["state"]["rows"][0];assert r==["20230901000","Linda Garcia",[1,0,1,1,1,0,1,0,1,1],70]

