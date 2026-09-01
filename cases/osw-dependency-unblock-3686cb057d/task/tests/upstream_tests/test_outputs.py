import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:libreoffice_calc:21ab7b40-77c2-4ae6-8321-e00d3a086c73" and r["native_evaluator"]=="compare_table"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="PeriodRate.xlsx contains 24 numeric A/B period rates in column C and highlights the unique maximum C20 value 14.724 in green."
def test_output_schema():
 s=_result()["state"];assert s["output_path"]=="/home/user/PeriodRate.xlsx" and s["header"]=="Period Rate (%)" and s["formula_range"]=="C2:C25"
def test_formula_coverage():
 s=_result()["state"];assert s["row_count"]==24 and s["formula_pattern"]=="=A{row}/B{row}" and len(s["rates"])==24
def test_numeric_results():
 s=_result()["state"];assert s["rates"]==[5.625,1.296,2.582666666667,4.66,3.097333333333,2.27475,3.5624,7.362,2.324,1.69575,2.8676,1.9412,6.783,1.9412,1.938,1.110857142857,3.022,5.165333333333,14.724,1.827714285714,1.864,2.324,5.239,2.654857142857]
def test_number_type():
 s=_result()["state"];assert s["result_type"]=="number" and s["number_format"]=="0.00"
def test_maximum_highlight():
 s=_result()["state"];assert s["maximum"]==14.724 and s["maximum_rows"]==[20] and s["highlight_cell"]=="C20" and s["font_color"]=="#00ff00" and s["conditional_formula"]=="$C2=MAX($C$2:$C$25)"
def test_gold_fidelity(): assert _result()["state"]["gold_workbook_sha256"]=="599cbdc6fe16b64b9628022bf55f26a488d1912c4b036359f3564c6146e1407a"
