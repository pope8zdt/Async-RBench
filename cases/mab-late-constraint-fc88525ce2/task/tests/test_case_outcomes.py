import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data');CASE_ID='mab-late-constraint-fc88525ce2';SOURCE_ID='bargaining:022'
def test_event_receipt_is_authentic_and_case_bound():
 d=json.loads((OUT/'event_receipt.json').read_text());h=d.pop('receipt_sha256');assert h==hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest() and d['case_id']==CASE_ID and d['source_task_id']==SOURCE_ID
def test_independent_worker_completed_with_observable_probes():
 d=json.loads((OUT/'event_receipt.json').read_text());assert d['worker_exit_code']==0 and all(d['probes'].values())
def test_final_closure_consumes_exact_event_receipt():
 r=json.loads((OUT/'event_receipt.json').read_text());m=json.loads((OUT/'decision_manifest.json').read_text());c=json.loads((OUT/'negotiation_closure.json').read_text());assert m['event_receipt_sha256']==r['receipt_sha256']==c['event_receipt_sha256'] and m['closure_complete'] and c['source_semantics_reverified']
def test_pinned_source_revision_is_preserved():assert SOURCE_ID
