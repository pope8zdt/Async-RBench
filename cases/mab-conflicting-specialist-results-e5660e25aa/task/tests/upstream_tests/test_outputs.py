from __future__ import annotations
import json,pathlib,re
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
SOURCE_ID='database:006'; EXPECTED='VACUUM'; DECOY='LOCK_CONTENTION'; EVIDENCE='322f0026d4e9ccabd0fd178488018700b11831b3a9f3bffe2a94814a0217ce62'; CHECKPOINT='36da8ae7700f5c7278b02ea708113955602551377ac59394f567241743bb00cb'
def diagnosis(): return json.loads((OUT/'database_diagnosis.json').read_text())
def native(): return json.loads(FIX.read_text())
def test_native_evaluator_binding_is_exact():
    n=native(); assert n['case_id']=='mab-conflicting-specialist-results-e5660e25aa' and n['source_task_id']==SOURCE_ID; assert n['source_native_marble_verified'] is True and n['native_evaluator_verified'] is True and n['passed'] is True
def test_selected_database_cause_is_exact():
    d=diagnosis(); assert d['selected_causes']==[EXPECTED]
def test_competing_diagnosis_is_reconciled():
    d=diagnosis(); assert d['superseded_causes']==[DECOY]; assert DECOY not in d['selected_causes']
def test_native_authority_evidence_is_consumed():
    d=diagnosis(); assert d['native_evidence_sha256']==EVIDENCE; assert d['host_checkpoint_sha256']==CHECKPOINT
def test_database_diagnosis_schema_and_preservation():
    d=diagnosis(); assert set(d)=={'source_task_id','selected_causes','superseded_causes','preserved_prior_findings','native_evidence_sha256','host_checkpoint_sha256','source_semantics_reverified'}; assert d['preserved_prior_findings'] is True and d['source_semantics_reverified'] is True
