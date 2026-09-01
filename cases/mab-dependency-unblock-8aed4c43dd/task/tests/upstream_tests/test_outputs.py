from __future__ import annotations
import json,pathlib
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
SOURCE='database:013'; CASE='mab-dependency-unblock-8aed4c43dd'; EXPECTED='LOCK_CONTENTION'; TENTATIVE='VACUUM'; EVIDENCE_SHA='fb85548fa724be44b7022696b350fe541d48ef08adeae3879270825c0b62f08c'; CHECKPOINT='b97d78c5fb7f69fbdd5296f208a9bfd520041e6c7055c9b37a630a03c5d6e67c'; ANOMALY_EVIDENCE={'blocker_lock_rows': 4, 'waiter_timeout_observed': True}; DOMAIN='file sharing'; PRESERVE=['file-sharing relation inventory', 'vacuum history disposition', 'insert, index, and fetch-path dispositions']
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
