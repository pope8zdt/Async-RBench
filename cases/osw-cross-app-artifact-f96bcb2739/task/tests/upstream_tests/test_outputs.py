import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:7f35355e-02a6-45b5-b140-f0be698bcf85" and r["native_evaluator"]=="compare_result_files"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="After CSV export, 12 missing Stock Price cells are imputed with the mean of 48 observed prices (39.20125), producing median 25.27 written as the only content of result.txt."
def test_row_accounting():
 s=_result()['state'];assert (s['table_rows'],s['observed_prices'],s['missing_prices'])==(60,48,12)
def test_mean():
 assert abs(_result()['state']['imputation_mean']-39.20125)<1e-9
def test_median():
 assert abs(_result()['state']['median_after_imputation']-25.27)<1e-9
def test_result_text():
 s=_result()['state'];assert s['result_text']=='25.27' and s['only_numeric'] is True
def test_workflow():
 s=_result()['state'];assert s['csv_exported'] is True and s['code_used'] is True
