from __future__ import annotations
import json,pathlib,re
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
SOURCE_ID='database:005'; EXPECTED='LOCK_CONTENTION'; DECOY='FETCH_LARGE_DATA'; EVIDENCE='bd2449c5466652ee1f79f6a7433093683df327ecce051192fc28598df645712f'; CHECKPOINT='5932d06eb74bb685d2600424226fcc2a4d802528b7dd3df0516e0990f02a20c7'
def diagnosis(): return json.loads((OUT/'database_diagnosis.json').read_text())
def native(): return json.loads(FIX.read_text())
def test_native_evaluator_binding_is_exact():
    n=native(); assert n['case_id']=='mab-conflicting-specialist-results-9ec14bb2f1' and n['source_task_id']==SOURCE_ID; assert n['source_native_marble_verified'] is True and n['native_evaluator_verified'] is True and n['passed'] is True
def test_selected_database_cause_is_exact():
    d=diagnosis(); assert d['selected_causes']==[EXPECTED]
def test_competing_diagnosis_is_reconciled():
    d=diagnosis(); assert d['superseded_causes']==[DECOY]; assert DECOY not in d['selected_causes']
def test_native_authority_evidence_is_consumed():
    d=diagnosis(); assert d['native_evidence_sha256']==EVIDENCE; assert d['host_checkpoint_sha256']==CHECKPOINT
def test_database_diagnosis_schema_and_preservation():
    d=diagnosis(); assert set(d)=={'source_task_id','selected_causes','superseded_causes','preserved_prior_findings','native_evidence_sha256','host_checkpoint_sha256','source_semantics_reverified'}; assert d['preserved_prior_findings'] is True and d['source_semantics_reverified'] is True
