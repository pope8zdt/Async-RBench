import json,pathlib,pytest
OUT=pathlib.Path('/app/output_data'); REG=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())
@pytest.mark.parametrize('point',REG['checks'],ids=lambda p:p['id'])
def test_control_point(point):
    receipt=json.loads((OUT/'event_receipt.json').read_text()); manifest=json.loads((OUT/'decision_manifest.json').read_text()); assert manifest['control_flow'][point['stage_tag']]['completed']; assert manifest['control_flow'][point['stage_tag']]['receipt_sha256']==receipt['receipt_sha256']
