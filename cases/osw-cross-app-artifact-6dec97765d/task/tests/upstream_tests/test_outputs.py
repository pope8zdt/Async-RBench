import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:510f64c8-9bcc-4be1-8d30-638705850618" and r["native_evaluator"]=="check_include_exclude+compare_config"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="VS Code is launched from the terminal with /home/user/Desktop/project, shell history contains the code command, and the OpenProject evaluator reports project."
def test_project_path():
 s=_result()['state'];assert s['project_path']=='/home/user/Desktop/project' and s['project_basename']=='project'
def test_project_assets():
 assert _result()['state']['project_files']==['main.py','README.md','.vscode/settings.json']
def test_terminal_history():
 s=_result()['state'];assert s['shell_history_contains_code'] is True and s['terminal_origin'] is True
def test_open_project_probe():
 assert _result()['state']['open_project_probe']=='project'
def test_vscode_state():
 assert _result()['state']['vscode_active'] is True
def test_official_checks():
 s=_result()['state'];assert s['official_terminal_check_passed'] is True and s['official_config_check_passed'] is True
