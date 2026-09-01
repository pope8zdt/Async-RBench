from __future__ import annotations
import json,pathlib,pytest
OUT=pathlib.Path('/app/output_data'); REG=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())
@pytest.mark.parametrize('point',REG['checks'],ids=lambda p:p['id'])
def test_control_point(point):
    receipt=json.loads((OUT/'event_receipt.json').read_text()); manifest=json.loads((OUT/'decision_manifest.json').read_text()); stage=point['stage_tag']
    if stage=='event_intake': assert receipt['receipt_sha256']==manifest['event_receipt_sha256']
    elif stage=='state_revision': assert manifest['event_consumed'] is True and manifest['final_revision_sha256']
    elif stage=='plan_revision': assert manifest['source_semantics_reverified'] is True
    elif stage=='closure': assert manifest['closure_complete'] is True and manifest['source_semantics_reverified'] is True
