from __future__ import annotations
import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); CASE_ID='mab-dependency-unblock-b69316f186'; SOURCE_ID='database:018'; CHECKPOINT='9cc9bbc280bd730a29ba8344df3af5f54150fef17e06c6bc25ca90e46655d464'; EVIDENCE={'blocker_lock_rows': 4, 'waiter_timeout_observed': True}
def test_event_receipt_is_authentic_and_case_bound():
    p=json.loads((OUT/'event_receipt.json').read_text()); claimed=p.pop('receipt_sha256'); assert claimed==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest(); assert p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID
def test_independent_worker_completed_with_task_specific_probes():
    p=json.loads((OUT/'event_receipt.json').read_text()); assert p['worker_exit_code']==0 and p['worker_finished_at']>=p['worker_started_at']; assert p['probes']=={'host_checkpoint_sha256':CHECKPOINT}; assert p['authority']['anomaly_evidence']==EVIDENCE
def test_final_closure_consumes_exact_event_receipt():
    r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); assert m['event_receipt_sha256']==r['receipt_sha256']; assert m['event_consumed'] and m['source_semantics_reverified'] and m['closure_complete']
def test_pinned_source_revision_is_preserved():
    d=json.loads((OUT/'database_diagnosis.json').read_text()); assert d['source_task_id']==SOURCE_ID
