from __future__ import annotations
import json,pathlib
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
SOURCE='database:021'; CASE='mab-dependency-unblock-18d7c09304'; EXPECTED='VACUUM'; TENTATIVE='LOCK_CONTENTION'; EVIDENCE_SHA='4e8f55ffc936d4d6a9eadc1dadc703412df4156f08b5c2a2e5f6f999aa53a5aa'; CHECKPOINT='893f6fa5b23d721446e95ce968a9b16cefb92639f000d3d4acb919e3362763cb'; ANOMALY_EVIDENCE={'remaining_rows': 500, 'vacuum_full_executed': True}; DOMAIN='healthcare management'; PRESERVE=['appointment and treatment schema inventory', 'lock-contention probe disposition', 'index and fetch-path dispositions']
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
