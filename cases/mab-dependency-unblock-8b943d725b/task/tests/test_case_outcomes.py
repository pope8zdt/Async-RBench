from __future__ import annotations
import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); CASE_ID='mab-dependency-unblock-8b943d725b'; SOURCE_ID='database:019'; CHECKPOINT='40bdbc186e72afba79d0d0a5d81547aa0fbeb14c1a75494fd4a11b43a113445b'; EVIDENCE={'same_column_indexes': 2}
def test_event_receipt_is_authentic_and_case_bound():
    p=json.loads((OUT/'event_receipt.json').read_text()); claimed=p.pop('receipt_sha256'); assert claimed==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest(); assert p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID
def test_independent_worker_completed_with_task_specific_probes():
    p=json.loads((OUT/'event_receipt.json').read_text()); assert p['worker_exit_code']==0 and p['worker_finished_at']>=p['worker_started_at']; assert p['probes']=={'host_checkpoint_sha256':CHECKPOINT}; assert p['authority']['anomaly_evidence']==EVIDENCE
def test_final_closure_consumes_exact_event_receipt():
    r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); assert m['event_receipt_sha256']==r['receipt_sha256']; assert m['event_consumed'] and m['source_semantics_reverified'] and m['closure_complete']
def test_pinned_source_revision_is_preserved():
    d=json.loads((OUT/'database_diagnosis.json').read_text()); assert d['source_task_id']==SOURCE_ID
