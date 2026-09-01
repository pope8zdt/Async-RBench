import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:26150609-0da3-4a7d-8868-0faf9c5f01bb" and r["native_evaluator"]=="check_python_file_by_test_suite"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="Food spawn coordinates are 10-pixel grid aligned and in bounds, so the Snake can reach food and the official OSWorld test suite passes."
def test_grid_size():
 assert _result()['state']['grid_size']==10
def test_initial_spawn():
 assert _result()['state']['initial_spawn_grid_aligned'] is True
def test_respawn():
 s=_result()['state'];assert s['respawn_grid_aligned'] is True and s['in_bounds'] is True
def test_snake_reaches_food():
 assert _result()['state']['snake_reaches_food'] is True
def test_official_test():
 assert _result()['state']['official_test_passed'] is True
def test_fixed_file():
 assert _result()['state']['fixed_file']=='food.py'
