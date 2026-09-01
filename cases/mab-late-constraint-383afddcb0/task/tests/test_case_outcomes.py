from __future__ import annotations
import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); CASE_ID='mab-late-constraint-383afddcb0'; SOURCE_ID='research:051'; METHOD='resolution-flexible continuous 2D scanning with pruning-aware hidden-state alignment and token-importance calibration'
def test_event_receipt_is_authentic_and_case_bound():
    p=json.loads((OUT/'event_receipt.json').read_text()); claimed=p.pop('receipt_sha256'); assert claimed==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest(); assert p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID
def test_delayed_research_authority_is_task_specific():
    p=json.loads((OUT/'event_receipt.json').read_text()); assert p['event']=='delayed_authoritative_research_result' and p['authority']['method']==METHOD and p['worker_exit_code']==0
def test_final_closure_consumes_exact_receipt():
    r=json.loads((OUT/'event_receipt.json').read_text()); c=json.loads((OUT/'research_closure.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); assert c['event_receipt_sha256']==r['receipt_sha256']==m['event_receipt_sha256']; assert c['closure_complete'] and m['closure_complete']
def test_source_pin_is_preserved():
    c=json.loads((OUT/'research_closure.json').read_text()); assert c['source_task_id']==SOURCE_ID
