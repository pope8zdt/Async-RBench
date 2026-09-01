from __future__ import annotations
import json,pathlib,pytest
O=pathlib.Path('/app/output_data');R=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())
@pytest.mark.parametrize('p',R['checks'],ids=lambda p:p['id'])
def test_control_point(p):
 r=json.loads((O/'event_receipt.json').read_text());m=json.loads((O/'decision_manifest.json').read_text());assert r['receipt_sha256']==m['event_receipt_sha256'] and m['event_consumed'] and m['source_semantics_reverified'];assert not (p['stage_tag']=='closure') or m['closure_complete']
