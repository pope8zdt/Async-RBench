from __future__ import annotations
import json,pathlib
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
SOURCE='database:016'; CASE='mab-dependency-unblock-309c3b9f50'; EXPECTED='LOCK_CONTENTION'; TENTATIVE='FETCH_LARGE_DATA'; EVIDENCE_SHA='5f84285a34d7104f034cbd5553411d83cb701ff9d5e514f210cede3d72121163'; CHECKPOINT='0257f2e42fbaaac5384b46538c65074d4e65ae9e5d5a01818dcf9ed4b4b256de'; ANOMALY_EVIDENCE={'blocker_lock_rows': 4, 'waiter_timeout_observed': True}; DOMAIN='transportation operations'; PRESERVE=['transport schema inventory', 'vacuum and index probe dispositions', 'read-path disposition']
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
