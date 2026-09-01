from __future__ import annotations
import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); CASE_ID='mab-dependency-unblock-a145b96b70'; SOURCE_ID='database:023'; CHECKPOINT='834bd92f8f348bbf0505f531ac223cde7a5b01d4f911603df5dd784ea44906e4'; EVIDENCE={'bytes': 1556480, 'row_count': 5000}
def test_event_receipt_is_authentic_and_case_bound():
    p=json.loads((OUT/'event_receipt.json').read_text()); claimed=p.pop('receipt_sha256'); assert claimed==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest(); assert p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID
def test_independent_worker_completed_with_task_specific_probes():
    p=json.loads((OUT/'event_receipt.json').read_text()); assert p['worker_exit_code']==0 and p['worker_finished_at']>=p['worker_started_at']; assert p['probes']=={'host_checkpoint_sha256':CHECKPOINT}; assert p['authority']['anomaly_evidence']==EVIDENCE
def test_final_closure_consumes_exact_event_receipt():
    r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); assert m['event_receipt_sha256']==r['receipt_sha256']; assert m['event_consumed'] and m['source_semantics_reverified'] and m['closure_complete']
def test_pinned_source_revision_is_preserved():
    d=json.loads((OUT/'database_diagnosis.json').read_text()); assert d['source_task_id']==SOURCE_ID
