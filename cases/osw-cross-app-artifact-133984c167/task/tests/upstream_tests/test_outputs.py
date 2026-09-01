import json
from pathlib import Path
O=Path("/app/output_data");N=Path("/async_rbench_tests/fixtures/native_canonical_report.json")
def _result():return json.loads((O/"osworld_native_result.json").read_text())
def _native():return json.loads(N.read_text())
def test_osworld_result_identity():
 r=_result();assert r["source_task_id"]=="osworld:multi_apps:df67aebb-fb3a-44fd-b75b-51b6012df509" and r["native_evaluator"]=="compare_text_file"
def test_official_score_is_one():assert _result()["official_score"]==1.0
def test_native_evidence_sha256_matches_fixture():assert _result()["native_evidence_sha256"]==_native()["evidence_sha256"]
def test_task_assertion_is_case_specific():assert _result()["task_assertion"]=="references.bib contains the six published DBLP records from the thesis DOCX, with no arXiv entries and a blank line between entries."
def test_bibtex_output_path():
    assert _result()["state"]["output_path"]=="/home/oai/share/references.bib"

def test_six_dblp_records():
    state=_result()["state"]; assert state["entry_count"]==6
    assert state["cite_keys"]==["DBLP:conf/emnlp/YuZYYWLMLYRZR18","DBLP:conf/acl/YuZYTLLELPCJDPS19","DBLP:conf/emnlp/YuZELXPLTSLJYSC19","DBLP:conf/nips/VaswaniSPUJGKP17","DBLP:conf/naacl/DevlinCLT19","DBLP:conf/nips/BrownMRSKDNSSAA20"]

def test_published_records_not_arxiv():
    state=_result()["state"]; assert state["arxiv_entries"]==0 and state["published_records_preferred"] is True

def test_bibtex_format():
    state=_result()["state"]; assert state["blank_line_separated"] is True and state["encoding"]=="utf-8"

