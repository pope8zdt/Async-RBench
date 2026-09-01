import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:c2751594-0cd5-4088-be1b-b5f2f9ec97c4" and r["native_evaluator"]=="compare_images"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="The active desktop wallpaper matches the first embedded image in lecture-notes.docx from the newest Notes email."
def test_mail_identity():
 s=_result()["state"];assert s["notes_subject"]=="Lecture Document" and s["notes_date"]=="Tue, 30 Jan 2024 02:38:44 -0800"
def test_attachment_identity():
 s=_result()["state"];assert s["attachment_name"]=="lecture-notes.docx" and s["attachment_sha256"]=="4c9a185bc89de330d1a736efe83315e2d2ab3305277c6126ee57056decdd41b4"
def test_first_embedded_image():
 s=_result()["state"];assert s["embedded_image_index"]==1 and s["embedded_image_path"]=="word/media/image1.png" and s["embedded_image_size"]==[860,732] and s["embedded_image_sha256"]=="4f584d4b99a2ae0498dd4fb8827bf3acbb53847918912881ce12b04dca91aaa9"
def test_wallpaper_state():
 s=_result()["state"];assert s["wallpaper_active"] is True and s["wallpaper_gold_size"]==[1496,626] and s["wallpaper_gold_sha256"]=="1b19ee9db539d8eeabe3deab4e7579aeba472afad1dbd9538fd110830ab9ca0c"

