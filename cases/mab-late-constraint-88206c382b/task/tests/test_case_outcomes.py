from __future__ import annotations
import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); CASE_ID='mab-late-constraint-88206c382b'; SOURCE_ID='bargaining:014'; CURRENT=2; STALE=1
def test_event_receipt_is_authentic_and_case_bound():
    p=json.loads((OUT/'event_receipt.json').read_text()); claimed=p.pop('receipt_sha256'); assert claimed==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest(); assert p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID
def test_late_offer_is_task_specific_and_stale():
    p=json.loads((OUT/'event_receipt.json').read_text()); assert p['event']=='late_superseded_offer_delivery' and p['delivered_offer']['revision']==STALE<CURRENT and p['classification']=='late_and_superseded'
def test_final_closure_consumes_receipt_and_rejects_stale():
    r=json.loads((OUT/'event_receipt.json').read_text()); c=json.loads((OUT/'negotiation_closure.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); assert c['event_receipt_sha256']==r['receipt_sha256']==m['event_receipt_sha256']; assert c['stale_revision_rejected'] and c['closure_complete']
def test_source_pin_is_preserved():
    a=json.loads((OUT/'agreement.json').read_text()); assert a['source_task_id']==SOURCE_ID
