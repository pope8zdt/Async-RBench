import hashlib,json,pathlib
O=pathlib.Path('/app/output_data');C="osw-late-test-evidence-f5d523fc9a";S="osworld:multi_apps:2373b66a-092d-44cb-bfd7-82e86e7a3b4d";D=3
def test_event_receipt_is_authentic_and_case_bound():
 p=json.loads((O/'event_receipt.json').read_text());x=p.pop('receipt_sha256');assert x==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();assert p['case_id']==C and p['source_task_id']==S and p['receipt_id'].startswith(C)
def test_independent_workers_completed_with_observable_probes():
 p=json.loads((O/'event_receipt.json').read_text());assert p['worker_finished_at']>=p['worker_started_at'] and p['worker_exit_code']==0 and p['probes']['upstream_depth']==D;assert p['probes']['workstream_reports']==D and p['evidence']['report_path'].endswith(f'upstream_worker_{D:02d}.json')
def test_final_closure_consumes_exact_event_receipt():
 r=json.loads((O/'event_receipt.json').read_text());m=json.loads((O/'decision_manifest.json').read_text());assert m['event_receipt_sha256']==r['receipt_sha256'] and m['event_consumed'] and m['native_evidence_consumed'] and m['source_semantics_reverified'] and m['closure_complete']
def test_pinned_source_revision_is_preserved():
 r=json.loads((O/'event_receipt.json').read_text());m=json.loads((O/'decision_manifest.json').read_text());assert r['source_task_id']==S and m['source_task_id']==S
