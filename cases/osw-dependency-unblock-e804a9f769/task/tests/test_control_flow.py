import json,pathlib,pytest
O=pathlib.Path('/app/output_data');R=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())
@pytest.mark.parametrize('p',R['checks'],ids=lambda p:p['id'])
def test_control_point(p):
 r=json.loads((O/'event_receipt.json').read_text());m=json.loads((O/'decision_manifest.json').read_text());s=p['stage_tag']
 if s=='event_intake':assert r['receipt_sha256']==m['event_receipt_sha256']
 elif s=='state_revision':assert m['event_consumed'] and m['native_evidence_consumed'] and m['final_revision_sha256']
 elif s=='plan_revision':assert m['event_consumed'] and m['source_task_id']==r['source_task_id']
 elif s=='closure':assert m['closure_complete'] and m['source_semantics_reverified']
