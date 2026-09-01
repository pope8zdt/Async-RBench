import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:48c46dc7-fe04-4505-ade7-723cba1aa6f6" and r["native_evaluator"]=="check_list+is_expected_tabs"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="The OSWorld project is open in Nautilus and GNOME Terminal at the required directory while Chrome has https://github.com and https://docs.python.org/3/ open."
def test_project_archive():
 s=_result()["state"];assert s["archive_sha256"]=="adadd814627cf0a9c70d2edd8a034b026decd2f89902498cc173378c33b6d7c2" and "codes/main.py" in s["archive_members"] and "osworld.ics" in s["archive_members"]
def test_nautilus_window():
 w=_result()["state"]["nautilus_window"];assert w["wm_class"]=="org.gnome.Nautilus.Org.gnome.Nautilus" and w["title_contains"]=="OSWorld"
def test_terminal_window():
 w=_result()["state"]["terminal_window"];assert w["wm_class"]=="gnome-terminal-server.Gnome-terminal" and w["title_contains"]=="~/Documents/Projects/OSWorld"
def test_chrome_tabs():
 assert _result()["state"]["chrome_tabs"]==["https://github.com","https://docs.python.org/3/"]

