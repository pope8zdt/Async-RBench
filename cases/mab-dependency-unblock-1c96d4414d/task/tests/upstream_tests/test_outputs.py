from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
OUT=Path('/app/output_data')
def load_solution():
    spec=importlib.util.spec_from_file_location('sports_submission',OUT/'solution.py'); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod
def closure(): return json.loads((OUT/'coding_closure.json').read_text())
def prepared():
    m=load_solution(); s=m.SportsTeamCollaborator(); s.create_team('red'); s.create_team('blue'); s.add_user('red','coach','coach'); s.add_user('red','ana','analyst'); s.add_user('red','p1','player'); return s

def test_sports_output_schema_and_artifacts():
    assert (OUT/'solution.py').is_file(); c=closure(); assert c['schema_version']=='async-rbench-mab-source-closure-v1' and c['case_id']=='mab-dependency-unblock-1c96d4414d' and c['source_task_id']=='coding:019' and c['artifact_type']=='authoritative_collaboration_sequence'; assert set(c['synchronized_surfaces'])=={'shared_notes','comments','chat'}

def test_sports_upload_metric_and_stale_sequence_functionality():
    s=prepared(); digest=s.upload('red','ana','m.csv',b'speed,31','csv'); metric=s.metric('red','coach','p1',[28,30,32]); accepted=s.collaborate('red','coach','note','press',0)
    try: s.collaborate('red','ana','comment','stale',0); raise AssertionError('stale edit accepted')
    except RuntimeError: pass
    assert len(digest)==64 and metric=={'player':'p1','average':30.0,'maximum':32,'count':3} and accepted['sequence']==1

def test_sports_preserves_team_isolation_and_role_permissions():
    s=prepared(); s.upload('red','ana','m.csv',b'speed,31','csv'); assert not s.teams['blue'].datasets
    try: s.upload('red','p1','x.csv',b'x','csv'); raise AssertionError('player upload accepted')
    except PermissionError: pass
    try: s.report('red','p1'); raise AssertionError('player report accepted')
    except PermissionError: pass
    assert s.report('red','coach')['dataset_count']==1

def test_sports_event_receipt_and_post_event_closure():
    r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); c=closure(); a=r['authority']
    assert r['event']=='stale_analyst_edit_arrived'; assert a['authoritative_sequence']==42 and a['late_expected_sequence']==41 and a['disposition']=='reject_superseded'; assert m['event_receipt_sha256']==r['receipt_sha256'] and m['event_consumed'] and m['closure_complete']; assert c['stale_result_disposition']=='rejected'
