import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:vs_code:930fdb3b-11a8-46fe-9bac-577332e2640e" and r["native_evaluator"]=="check_json_keybindings"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="The active VS Code keybindings contain one terminal-scoped Ctrl+J entry that moves focus to the active editor group without replacing unrelated shortcuts."
def test_output_path(): assert _result()["state"]["output_path"]=="/home/user/.config/Code/User/keybindings.json"
def test_entry_identity():
 s=_result()["state"];assert s["key"]=="ctrl+j" and s["command"]=="workbench.action.focusActiveEditorGroup"
def test_terminal_scope(): assert _result()["state"]["when"]=="terminalFocus"
def test_unique_valid_entry():
 s=_result()["state"];assert s["matching_entry_count"]==1 and s["valid_json"] is True
def test_scoped_behavior():
 s=_result()["state"];assert s["terminal_to_editor_enabled"] is True and s["unrelated_keybindings_preserved"] is True
