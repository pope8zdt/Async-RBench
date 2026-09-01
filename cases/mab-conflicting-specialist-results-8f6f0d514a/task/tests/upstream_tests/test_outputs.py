from __future__ import annotations
import json,pathlib,re
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
SOURCE_ID='database:007'; EXPECTED='FETCH_LARGE_DATA'; DECOY='LOCK_CONTENTION'; EVIDENCE='dc3b195c8d2cca892c19b84b09124ad163465d4eaf668946bead5a8358e570ea'; CHECKPOINT='d09040e0d071cb17c8e52312369004c0c17e52ecd55842eff3890404d6a643cc'
def diagnosis(): return json.loads((OUT/'database_diagnosis.json').read_text())
def native(): return json.loads(FIX.read_text())
def test_native_evaluator_binding_is_exact():
    n=native(); assert n['case_id']=='mab-conflicting-specialist-results-8f6f0d514a' and n['source_task_id']==SOURCE_ID; assert n['source_native_marble_verified'] is True and n['native_evaluator_verified'] is True and n['passed'] is True
def test_selected_database_cause_is_exact():
    d=diagnosis(); assert d['selected_causes']==[EXPECTED]
def test_competing_diagnosis_is_reconciled():
    d=diagnosis(); assert d['superseded_causes']==[DECOY]; assert DECOY not in d['selected_causes']
def test_native_authority_evidence_is_consumed():
    d=diagnosis(); assert d['native_evidence_sha256']==EVIDENCE; assert d['host_checkpoint_sha256']==CHECKPOINT
def test_database_diagnosis_schema_and_preservation():
    d=diagnosis(); assert set(d)=={'source_task_id','selected_causes','superseded_causes','preserved_prior_findings','native_evidence_sha256','host_checkpoint_sha256','source_semantics_reverified'}; assert d['preserved_prior_findings'] is True and d['source_semantics_reverified'] is True
