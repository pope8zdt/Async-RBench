from __future__ import annotations
import json,pathlib
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
SOURCE='database:018'; CASE='mab-dependency-unblock-b69316f186'; EXPECTED='LOCK_CONTENTION'; TENTATIVE='REDUNDANT_INDEX'; EVIDENCE_SHA='63fc51db3d504ae0d1a59fa985bd28853f837cfb6c5e9ccdd6c3b6a8f4d85f9d'; CHECKPOINT='9cc9bbc280bd730a29ba8344df3af5f54150fef17e06c6bc25ca90e46655d464'; ANOMALY_EVIDENCE={'blocker_lock_rows': 4, 'waiter_timeout_observed': True}; DOMAIN='music streaming'; PRESERVE=['music schema inventory', 'index disposition', 'insert, vacuum, and fetch-path dispositions']
def diagnosis(): return json.loads((OUT/'database_diagnosis.json').read_text())
def native(): return json.loads(FIX.read_text())
def test_native_evaluator_binding_is_exact():
    n=native(); assert n['case_id']==CASE and n['source_task_id']==SOURCE and n['anomaly']==EXPECTED; assert n['upstream_marble_evaluator']=='marble.evaluator.evaluator.Evaluator.evaluate_task_db'; assert n['native_evaluator_metrics']['predicted']==EXPECTED and n['native_evaluator_metrics']['root_cause']==[EXPECTED]; assert n['source_native_marble_verified'] and n['native_evaluator_verified'] and n['passed']
def test_selected_database_cause_is_exact(): assert diagnosis()['selected_causes']==[EXPECTED]
def test_tentative_diagnosis_is_excluded():
    d=diagnosis(); assert d['excluded_tentative_causes']==[TENTATIVE] and TENTATIVE not in d['selected_causes']
def test_native_authority_evidence_is_consumed():
    d=diagnosis(); assert d['native_evidence_sha256']==EVIDENCE_SHA and d['host_checkpoint_sha256']==CHECKPOINT and d['authority_evidence']==ANOMALY_EVIDENCE
def test_database_diagnosis_schema_and_preservation():
    d=diagnosis(); assert set(d)=={'source_task_id','database_domain','selected_causes','excluded_tentative_causes','native_evidence_sha256','host_checkpoint_sha256','authority_evidence','preserved_prior_findings','source_semantics_reverified'}; assert d['database_domain']==DOMAIN and d['preserved_prior_findings']==PRESERVE and d['source_semantics_reverified'] is True
