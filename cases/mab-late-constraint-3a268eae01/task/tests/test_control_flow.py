import json,pathlib,pytest
OUT=pathlib.Path('/app/output_data');REG=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())
@pytest.mark.parametrize('point',REG['checks'],ids=lambda p:p['id'])
def test_control_point(point):
 r=json.loads((OUT/'event_receipt.json').read_text());m=json.loads((OUT/'decision_manifest.json').read_text());assert m['control_flow'][point['stage_tag']]['completed'] and m['control_flow'][point['stage_tag']]['receipt_sha256']==r['receipt_sha256']
