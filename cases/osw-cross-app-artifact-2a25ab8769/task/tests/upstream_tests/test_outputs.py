import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:3f05f3b9-29ba-4b6b-95aa-2204697ffc06" and r["native_evaluator"]=="check_mp3_meta×5"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="All five audited MP3 files retain their audio identity and have exact artist and title tags matching the filename pairs checked by the official evaluators."
def test_track_set():
 s=_result()["state"];assert s["track_count"]==5 and len(s["tracks"])==5 and all(t["path"].startswith("/home/user/Music/") for t in s["tracks"])
def test_initial_blank_tags():
 assert _result()["state"]["all_initial_tags_empty"] is True
def test_cheng_track():
 t=_result()["state"]["tracks"][0];assert (t["artist"],t["title"])==("Cheng Xiang","Missing You")
def test_han_track():
 t=_result()["state"]["tracks"][1];assert (t["artist"],t["title"])==("Han Baoyi","Tears of Dancing Girl")
def test_huang_track():
 t=_result()["state"]["tracks"][2];assert (t["artist"],t["title"])==("Huang An","I Know Missing is Painful")
def test_chen_track():
 t=_result()["state"]["tracks"][3];assert (t["artist"],t["title"])==("Chen Shaohua","Red Daughter")
def test_zhou_track():
 t=_result()["state"]["tracks"][4];assert (t["artist"],t["title"])==("Zhou Xuan","Nights in Shanghai")
def test_audio_preservation():
 s=_result()["state"];assert s["all_audio_preserved"] is True and all(len(t["source_sha256"])==64 for t in s["tracks"])

