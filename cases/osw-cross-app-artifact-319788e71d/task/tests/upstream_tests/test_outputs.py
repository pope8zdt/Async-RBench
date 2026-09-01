import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:da922383-bfa4-4cd3-bbad-6bebab3d7742" and r["native_evaluator"]=="exact_match"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="The Blog folder contains exactly two readable PDFs named for the two open articles: LLM Powered Autonomous Agents and Thinking about High-Quality Human Data."
def test_blog_output_dir():
    assert _result()["state"]["output_dir"]=="/home/user/Documents/Blog"

def test_blog_pdf_coverage():
    state=_result()["state"]; assert state["files"]==["LLM Powered Autonomous Agents.pdf","Thinking about High-Quality Human Data.pdf"]; assert state["one_pdf_per_tab"] is True

def test_blog_pdf_readability():
    state=_result()["state"]; assert state["readable"]==[True,True]; assert state["titles"]==["LLM Powered Autonomous Agents","Thinking about High-Quality Human Data"]

