import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:3680a5ee-6870-426a-a997-eba929a0d25c" and r["native_evaluator"]=="check_include_exclude+compare_csv"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="Using only command-line operations, the 5,001 XLSX and ODS rows are concatenated in order into output.csv and that file is opened in LibreOffice Calc from the terminal."
def test_row_counts():
 s=_result()['state'];assert (s['file1_rows'],s['file2_rows'],s['output_rows'])==(5001,5001,5001)
def test_boundaries():
 s=_result()['state'];assert (s['header_left'],s['header_right'])==('First Name','Last Name') and (s['first_data_left'],s['first_data_right'])==('Dulce','Abril') and (s['last_data_left'],s['last_data_right'])==('Rasheeda','Alkire')
def test_order():
 assert _result()['state']['order_preserved'] is True
def test_output_path():
 assert _result()['state']['output_path']=='/home/user/Desktop/output.csv'
def test_terminal_calc():
 s=_result()['state'];assert s['command_line_only'] is True and s['opened_in_calc'] is True and s['launched_from_terminal'] is True
def test_accepted_variant():
 assert _result()['state']['accepted_variant'] in {'tab','none','space'}
