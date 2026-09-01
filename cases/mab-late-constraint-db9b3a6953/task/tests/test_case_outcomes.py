from __future__ import annotations
import hashlib,json,pathlib
O=pathlib.Path('/app/output_data');CASE='mab-late-constraint-db9b3a6953';SOURCE='bargaining:004';CURRENT=2;STALE=1
def test_event_receipt_is_authentic_and_bound():
 p=json.loads((O/'event_receipt.json').read_text());c=p.pop('receipt_sha256');assert c==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();assert p['case_id']==CASE and p['source_task_id']==SOURCE
def test_late_offer_is_stale():
 p=json.loads((O/'event_receipt.json').read_text());assert p['delivered_offer']['revision']==STALE<CURRENT and p['classification']=='late_and_superseded'
def test_closure_rejects_stale():
 r=json.loads((O/'event_receipt.json').read_text());c=json.loads((O/'negotiation_closure.json').read_text());m=json.loads((O/'decision_manifest.json').read_text());assert c['event_receipt_sha256']==r['receipt_sha256']==m['event_receipt_sha256'] and c['stale_revision_rejected'] and c['closure_complete']
def test_source_pin():assert json.loads((O/'agreement.json').read_text())['source_task_id']==SOURCE
