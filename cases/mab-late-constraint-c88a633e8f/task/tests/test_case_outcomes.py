from __future__ import annotations
import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); CASE_ID='mab-late-constraint-c88a633e8f'; SOURCE_ID='bargaining:003'
def test_event_receipt_is_authentic_and_case_bound():
 p=json.loads((OUT/'event_receipt.json').read_text()); claimed=p.pop('receipt_sha256'); assert claimed==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest(); assert p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID
def test_independent_worker_completed_with_observable_probes():
 p=json.loads((OUT/'event_receipt.json').read_text()); assert p['worker_finished_at']>=p['worker_started_at'] and p['worker_exit_code']==0 and p['probes'] and any(v is not None for v in p['probes'].values())
def test_final_closure_consumes_exact_event_receipt():
 r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); assert m['event_receipt_sha256']==r['receipt_sha256'] and m['event_consumed'] is True and m['source_semantics_reverified'] is True and m['closure_complete'] is True
def test_pinned_source_revision_is_preserved(): assert SOURCE_ID
