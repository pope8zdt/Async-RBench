from __future__ import annotations
import json,pathlib,re
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
SOURCE_ID='database:008'; EXPECTED='INSERT_LARGE_DATA'; DECOY='LOCK_CONTENTION'; EVIDENCE='5628d05e3619235f1aae717a8ca1c84322dc6fbe37ee27797ed14ceeedcfc599'; CHECKPOINT='165afb19e3b554272f09b4689c302d4f09867b14a42df5c47f352cd282297b0b'
def diagnosis(): return json.loads((OUT/'database_diagnosis.json').read_text())
def native(): return json.loads(FIX.read_text())
def test_native_evaluator_binding_is_exact():
    n=native(); assert n['case_id']=='mab-conflicting-specialist-results-0298f78d18' and n['source_task_id']==SOURCE_ID; assert n['source_native_marble_verified'] is True and n['native_evaluator_verified'] is True and n['passed'] is True
def test_selected_database_cause_is_exact():
    d=diagnosis(); assert d['selected_causes']==[EXPECTED]
def test_competing_diagnosis_is_reconciled():
    d=diagnosis(); assert d['superseded_causes']==[DECOY]; assert DECOY not in d['selected_causes']
def test_native_authority_evidence_is_consumed():
    d=diagnosis(); assert d['native_evidence_sha256']==EVIDENCE; assert d['host_checkpoint_sha256']==CHECKPOINT
def test_database_diagnosis_schema_and_preservation():
    d=diagnosis(); assert set(d)=={'source_task_id','selected_causes','superseded_causes','preserved_prior_findings','native_evidence_sha256','host_checkpoint_sha256','source_semantics_reverified'}; assert d['preserved_prior_findings'] is True and d['source_semantics_reverified'] is True
