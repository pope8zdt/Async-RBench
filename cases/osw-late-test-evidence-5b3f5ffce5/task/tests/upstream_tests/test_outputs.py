import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:9219480b-3aed-47fc-8bac-d2cffc5849f7" and r["native_evaluator"]=="check_python_file_by_test_suite"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="The fixed Tetris project passes the official test() suite and keeps left-wall and right-wall rotations collision-free without crashing."
def test_project_identity():
 s=_result()["state"];assert s["project_path"]=="/home/user/Desktop/tetris" and set(s["source_files_sha256"])=={"block.py","main.py","settings.py","tetris.py"}
def test_test_suite_identity():
 s=_result()["state"];assert s["official_test_function"]=="test" and s["official_test_sha256"]=="b266e83242c035256b9a6b0904615318e5bb90fd7ef19f8648a9503e7a96c9ff"
def test_boundary_rotation():
 s=_result()["state"];assert s["left_wall_rotation_safe"] is True and s["right_wall_rotation_safe"] is True
def test_collision_handling():
 s=_result()["state"];assert s["rotation_reverts_or_kicks_on_collision"] is True and s["official_test_passed"] is True and s["modified_file"].endswith("/tetris.py")

