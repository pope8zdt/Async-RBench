import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:7ff48d5b-2df2-49da-b500-a5150ffc7f18" and r["native_evaluator"]=="fuzzy_place_math"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="AllLocations.docx contains exactly five distinct Chinese Futian addresses accepted by the official fuzzy_place_math rule."
def test_output_path(): assert _result()["state"]["output_path"]=="/home/user/Desktop/AllLocations.docx"
def test_location_count():
 s=_result()["state"];assert s["location_count"]==5 and s["distinct"] is True
def test_location_eligibility():
 s=_result()["state"];assert s["district"]=="福田区" and s["service_hours"]=="24-hour"
def test_chinese_addresses():
 assert _result()["state"]["addresses"]==["深圳市福田区益田路5055号信息枢纽大厦西门一楼","深圳市福田区福华三路111号北三门会展中心警务室","深圳市福田区正义街1号","福田区莲科路18号莲花一村警务室","深圳市福田区彩云路2-8长城盛世家园一期C座一楼一期管理处旁边"]

