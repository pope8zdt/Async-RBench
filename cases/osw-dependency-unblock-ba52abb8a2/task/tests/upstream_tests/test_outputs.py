import json
from pathlib import Path
OUT=Path('/app/output_data')
SOURCE='osworld:chrome:6766f2b8-8a72-417f-a9e5-56fcaa735837'
def _result(): return json.loads((OUT/'extension_result.json').read_text())
def test_extension_result_exists(): assert (OUT/'extension_result.json').is_file()
def test_extension_result_matches_official_source():
    r=_result(); assert r['source_task_id']==SOURCE and r['evaluator']=='is_in_list'
def test_official_extension_score_is_one(): assert _result()['official_score']==1.0
def test_extension_path_is_manifest_root(): assert _result()['extracted_path']=='/home/user/Desktop/helloExtension' and _result()['manifest_present'] is True
