import hashlib,json,pathlib
O=pathlib.Path('/app/output_data');C="osw-cross-app-artifact-133984c167";S="osworld:multi_apps:df67aebb-fb3a-44fd-b75b-51b6012df509"
def test_event_receipt_is_authentic_and_case_bound():
 p=json.loads((O/'event_receipt.json').read_text());x=p.pop('receipt_sha256');assert x==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();assert p['case_id']==C and p['source_task_id']==S
def test_independent_worker_completed_with_observable_probes():
 p=json.loads((O/'event_receipt.json').read_text());assert p['worker_finished_at']>=p['worker_started_at'] and p['worker_exit_code']==0 and p['probes']['upstream_depth']==2
def test_final_closure_consumes_exact_event_receipt():
 r=json.loads((O/'event_receipt.json').read_text());m=json.loads((O/'decision_manifest.json').read_text());assert m['event_receipt_sha256']==r['receipt_sha256'] and m['event_consumed'] and m['source_semantics_reverified'] and m['closure_complete']
def test_pinned_source_revision_is_preserved(): assert S

