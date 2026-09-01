from __future__ import annotations
import json,pathlib,pytest
OUT=pathlib.Path('/app/output_data'); REG=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())
@pytest.mark.parametrize('point',REG['checks'],ids=lambda p:p['id'])
def test_control_point(point):
 r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); stage=point['stage_tag']
 if stage=='event_intake':assert r['receipt_sha256']==m['event_receipt_sha256']
 elif stage=='state_revision':assert m['event_consumed'] is True and m['final_revision_sha256']
 elif stage=='plan_revision':assert m['source_semantics_reverified'] is True
 elif stage=='closure':assert m['closure_complete'] is True and m['source_semantics_reverified'] is True
