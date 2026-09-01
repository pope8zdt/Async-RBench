import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:f8369178-fafe-40c2-adc4-b9b08a125456" and r["native_evaluator"]=="check_list"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="The Orchis theme is installed from gnome-look.org and the GNOME gtk-theme preference resolves to Orchis under the official check_list evaluator."
def test_theme_identity():
 s=_result()["state"];assert s["theme_name"]=="Orchis" and s["theme_installed"] is True and s["theme_applied"] is True
def test_theme_source():
 assert _result()["state"]["theme_source"]=="gnome-look.org"
def test_gsettings_binding():
 s=_result()["state"];assert s["gsettings_schema"]=="org.gnome.desktop.interface" and s["gsettings_key"]=="gtk-theme"
def test_gsettings_output():
 assert "Orchis" in _result()["state"]["gsettings_output"]

