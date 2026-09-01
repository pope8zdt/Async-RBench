import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:788b3701-3ec9-4b67-b679-418bfa726c22" and r["native_evaluator"]=="diff_text_file"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="Early Buildings.tex is the next chapter absent from the seven-file archive and its saved content exactly matches the official 5045-byte gold text."
def test_archive_inventory():
 s=_result()["state"];assert s["archive_sha256"]=="ee25951bc798d678253ec3cb7afd87114a6a7e6535499156a23a58ca9a838382" and len(s["existing_chapters"])==7 and "Early Buildings.tex" not in s["existing_chapters"]
def test_next_chapter():
 s=_result()["state"];assert s["repository_url"]=="https://github.com/liangjs333/4th-year-in-tsinghua-eng" and s["next_chapter"]=="Early Buildings.tex"
def test_output_path():
 assert _result()["state"]["output_path"]=="/home/user/Documents/Novels/4th Year in Tsinghua/Early Buildings.tex"
def test_gold_content():
 s=_result()["state"];assert s["content_sha256"]=="648849de03984bfaeaac2be87fdbbba9ff66cfdd430165edf5655ebef1d8ac5d" and s["content_bytes"]==5045 and s["content_lines"]==76 and s["first_line"]=="\\chapter{Early Buildings}"

