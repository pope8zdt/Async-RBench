from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
 p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def assert_closure(kind):
 r,c=docs(); assert c['artifact_type']==kind and c['upstream_depth']==4 and c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True
def test_drift_output_schema_and_artifacts():
 m=load_solution(); assert m.DOMAIN=='multi_agent_drift_championship' and hasattr(m,'DriftChampionship'); assert_closure('fixed_timestep_drift_closure')
def test_drift_fixed_timestep_grip_collision_scoring_and_strategy():
 m=load_solution(); app=m.DriftChampionship(); app.add_agent('a',1.2,1.1,1.0); app.add_track('t',1.0,'hard',['wall']); state={'angle':12,'speed':20,'combo_duration':1}
 normal=app.step('a','t',state,.5,.2,.1,1.0,False); longer=app.step('a','t',state,.5,.2,.2,1.0,False); low=app.step('a','t',state,.5,.2,.1,.4,False); hit=app.step('a','t',state,.5,.2,.1,1.0,True)
 assert normal['angle']!=longer['angle'] and low['drift_score']<normal['drift_score']; assert hit['combo_duration']==0 and hit['drift_score']==0
 assert app.strategy('a',10,[20],1.0)['action']=='defensive_line' and app.strategy('a',10,[5],.4)['action']=='grip_conserve'
def test_drift_agent_track_replay_and_feedback_are_preserved():
 m=load_solution(); app=m.DriftChampionship(); app.add_agent('a',1,1); app.add_track('t',.8,'medium'); event=app.step('a','t',{'angle':15,'speed':10},.2,.2); app.save_replay('r',[event]); app.strategy('a',10,[5],.8)
 assert app.agents['a']['handling']==1 and app.tracks['t']['grip']==.8; assert app.replays[0]['race_id']=='r' and app.feedback and app.history
def test_drift_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='drift_physics_v2'; assert r['authority']['contract']==m.EVENT_SCHEMA and r['authority']['fixed_timestep']==.1; assert c['preserved_workflows']==['agent_customizations','track_layouts','race_replays','performance_feedback']
