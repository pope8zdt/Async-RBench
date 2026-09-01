import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:69acbb55-d945-4927-a87b-8480e1a5bb7e" and r["native_evaluator"]=="check_include_exclude"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="The /home/user instructor-embedding environment imports INSTRUCTOR successfully and remains bound to the official repository and dependency lock."
def test_project_identity():
 s=_result()["state"];assert s["project_path"]=="/home/user/instructor-embedding" and s["repository_url"]=="https://github.com/xlang-ai/instructor-embedding" and s["repository_revision"]=="9a9742c130cef6e028af9f3bd582204c5bcfe96e"
def test_distribution_identity():
 s=_result()["state"];assert s["distribution_name"]=="InstructorEmbedding" and s["distribution_version"]=="1.0.2"
def test_dependency_lock(): assert len(_result()["state"]["dependency_ranges"])==12 and "sentence-transformers>=3.0.1,<4.0" in _result()["state"]["dependency_ranges"]
def test_import_command(): assert _result()["state"]["import_statement"]=="from InstructorEmbedding import INSTRUCTOR;"
def test_import_smoke():
 s=_result()["state"];assert s["import_exit_code"]==0 and s["import_stderr"]=="" and s["official_exclude_token"]=="Error:"
