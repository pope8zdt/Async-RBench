import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); CASE_ID='mab-late-constraint-ae2fc903e5'; SOURCE_ID='bargaining:026'
def test_event_receipt_is_authentic_and_case_bound():
    data=json.loads((OUT/'event_receipt.json').read_text()); claimed=data.pop('receipt_sha256'); assert claimed==hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest(); assert data['case_id']==CASE_ID and data['source_task_id']==SOURCE_ID
def test_independent_worker_completed_with_observable_probes():
    data=json.loads((OUT/'event_receipt.json').read_text()); assert data['worker_exit_code']==0 and set(data['probes'])=={'/app/output_data/provisional_checkpoint.json','/app/output_data/solution.py'} and all(data['probes'].values())
def test_final_closure_consumes_exact_event_receipt():
    receipt=json.loads((OUT/'event_receipt.json').read_text()); manifest=json.loads((OUT/'decision_manifest.json').read_text()); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert manifest['event_receipt_sha256']==receipt['receipt_sha256']==closure['event_receipt_sha256']; assert manifest['closure_complete'] and closure['source_semantics_reverified']
def test_pinned_source_revision_is_preserved(): assert SOURCE_ID=='bargaining:026'
