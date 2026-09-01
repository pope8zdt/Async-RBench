from __future__ import annotations
import json,pathlib,pytest
OUT=pathlib.Path('/app/output_data'); REG=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())
@pytest.mark.parametrize('point',REG['checks'],ids=lambda p:p['id'])
def test_control_point(point):
 receipt=json.loads((OUT/'event_receipt.json').read_text()); closure=json.loads((OUT/'negotiation_closure.json').read_text()); manifest=json.loads((OUT/'decision_manifest.json').read_text()); agreement=json.loads((OUT/'agreement.json').read_text())
 if point['stage_tag']=='event_intake': assert receipt['delivered_offer']['status']=='superseded' and receipt['receipt_sha256']==manifest['event_receipt_sha256']
 elif point['stage_tag']=='state_revision': assert closure['stale_revision_rejected'] and agreement['terms']['production_demand_balance']=='seller-confirmed'
 else: assert manifest['closure_complete'] and closure['source_semantics_reverified']
