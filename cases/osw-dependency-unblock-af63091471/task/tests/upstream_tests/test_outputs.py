import json
from pathlib import Path

OUT = Path('/app/output_data')
SOURCE = 'osworld:chrome:af630914-714e-4a24-a7bb-f9af687d3b91'

def _result():
    return json.loads((OUT / 'font_size_result.json').read_text())

def test_font_size_result_exists():
    assert (OUT / 'font_size_result.json').is_file()

def test_font_size_result_matches_official_source():
    result = _result()
    assert result['source_task_id'] == SOURCE
    assert result['evaluator'] == 'check_font_size'

def test_official_font_score_is_one():
    assert _result()['official_score'] == 1.0

def test_font_size_is_largest():
    assert _result()['default_font_size'] == 24
