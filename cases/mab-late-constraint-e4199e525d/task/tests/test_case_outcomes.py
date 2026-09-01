from __future__ import annotations
import hashlib,json,pathlib
O=pathlib.Path('/app/output_data');CASE='mab-late-constraint-e4199e525d';SOURCE='research:064';METHOD='risk-calibrated hierarchical skill selection with online opponent adaptation and confidence-aware fallback'
def test_event_receipt_is_authentic_and_bound():
 p=json.loads((O/'event_receipt.json').read_text());c=p.pop('receipt_sha256');assert c==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest() and p['case_id']==CASE and p['source_task_id']==SOURCE
def test_authority_is_table_tennis_specific():
 p=json.loads((O/'event_receipt.json').read_text());assert p['authority']['method']==METHOD and p['worker_exit_code']==0
def test_closure_consumes_receipt():
 r=json.loads((O/'event_receipt.json').read_text());c=json.loads((O/'research_closure.json').read_text());m=json.loads((O/'decision_manifest.json').read_text());assert c['event_receipt_sha256']==r['receipt_sha256']==m['event_receipt_sha256'] and c['closure_complete']
def test_source_pin():assert json.loads((O/'research_closure.json').read_text())['source_task_id']==SOURCE
