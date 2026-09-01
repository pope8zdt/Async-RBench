import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:vlc:5ac2891a-eacd-4954-b339-98abba077adb" and r["native_evaluator"]=="check_play_and_exit"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="The active VLC configuration contains one effective play-and-exit=0 setting and VLC no longer exits automatically at end of playback."
def test_config_path(): assert _result()["state"]["config_path"]=="/home/user/.config/vlc/vlcrc"
def test_preference_value():
 s=_result()["state"];assert s["preference_key"]=="play-and-exit" and s["initial_value"]==1 and s["final_value"]==0
def test_single_effective_assignment():
 s=_result()["state"];assert s["effective_assignment_count"]==1 and s["conflicting_enabled_assignment"] is False
def test_restart_persistence():
 s=_result()["state"];assert s["vlc_restarted"] is True and s["config_persisted"] is True
def test_playback_behavior(): assert _result()["state"]["playback_exit_disabled"] is True
