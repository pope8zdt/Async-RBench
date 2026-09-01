import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); CASE_ID='mab-late-constraint-49a364ba43'; SOURCE_ID='bargaining:021'
def test_event_receipt_is_authentic_and_case_bound():
 p=json.loads((OUT/'event_receipt.json').read_text()); claimed=p.pop('receipt_sha256'); assert claimed==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest() and p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID and p['classification']=='late_and_superseded'
def test_independent_worker_completed_with_observable_probes():
 p=json.loads((OUT/'event_receipt.json').read_text()); assert p['worker_exit_code']==0 and p['probes'] and p['worker_finished_at']>=p['worker_started_at']
def test_final_closure_consumes_exact_event_receipt():
 r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); assert m['event_receipt_sha256']==r['receipt_sha256'] and m['event_consumed'] and m['closure_complete']
def test_pinned_source_revision_is_preserved(): assert SOURCE_ID=='bargaining:021'
