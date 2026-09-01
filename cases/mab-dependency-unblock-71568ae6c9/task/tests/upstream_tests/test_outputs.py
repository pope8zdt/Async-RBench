from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
OUT=Path('/app/output_data')
def load_solution():
    spec=importlib.util.spec_from_file_location('galactic_submission',OUT/'solution.py'); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod
def closure(): return json.loads((OUT/'coding_closure.json').read_text())

def test_galactic_output_schema_and_artifacts():
    assert (OUT/'solution.py').is_file(); c=closure(); assert c['schema_version']=='async-rbench-mab-source-closure-v1' and c['case_id']=='mab-dependency-unblock-71568ae6c9' and c['source_task_id']=='coding:054' and c['artifact_type']=='validated_map_multiplayer_gate'; assert set(c['synchronized_surfaces'])=={'matchmaking','chat','player_actions'}

def test_galactic_dependency_map_and_multiplayer_functionality():
    g=load_solution().GalacticConquest(); g.create_character('a','Nova',['dash']); g.create_character('b','Ion',['shield']); g.configure_ai('adaptive'); g.generate_map(3,True,True); g.enable_multiplayer(); mid=g.start({'red':['a'],'blue':['b']}); event=g.action(mid,'red','capture',1,0)
    assert g.map=={'key_points':3,'destructible':True,'powerups':True} and event['sequence']==1 and g.matches[mid].score['red']==10

def test_galactic_preserves_character_ai_score_progression_and_rejects_stale():
    g=load_solution().GalacticConquest(); g.create_character('a','Nova',['dash']); g.create_character('b','Ion',['shield']); g.configure_ai('adaptive'); g.generate_map(2); g.enable_multiplayer(); mid=g.start({'red':['a'],'blue':['b']}); g.action(mid,'red','capture',0,0)
    try: g.action(mid,'blue','capture',1,0); raise AssertionError('stale action accepted')
    except RuntimeError: pass
    result=g.finish(mid,'red'); assert result['score']['red']==10 and g.characters['a']['xp']==100 and g.ai_policy=='adaptive'

def test_galactic_event_receipt_and_post_event_closure():
    r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); c=closure(); a=r['authority']
    assert r['event']=='validated_map_checkpoint_recovered'; assert a['dependency']=='validated_map_checkpoint' and a['map_revision']=='map-r17' and set(a['validated_invariants'])=={'objective_placement','destructible_terrain','power_ups','balance'}; assert m['event_receipt_sha256']==r['receipt_sha256'] and m['closure_complete'] and m['source_semantics_reverified']; assert c['stale_result_disposition']=='rejected'
