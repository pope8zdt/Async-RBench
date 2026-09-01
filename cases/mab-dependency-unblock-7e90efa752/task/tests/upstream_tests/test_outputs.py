from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
 p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def event_docs():return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def assert_closure(k):
 r,c=event_docs(); assert c['case_id']=='mab-dependency-unblock-7e90efa752' and c['source_task_id']=='coding:052' and c['artifact_type']==k and c['upstream_depth']==4; assert c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True
def test_teamsync_output_schema_and_artifacts():
 m=load_solution(); assert m.DOMAIN=='team_sync_sports'; assert hasattr(m,'TeamSync'); assert_closure('sports_profile_schedule_closure')
def test_teamsync_stable_ids_availability_conflicts_permissions_and_deletion():
 m=load_solution(); app=m.TeamSync(); app.create_player('c','c@x','coach',[(8,18)]); app.create_player('p','p@x','player',[(9,12)]); app.schedule('e',9,10,['c','p'])
 try: app.schedule('bad',11,13,['p'])
 except ValueError: pass
 else: raise AssertionError('availability ignored')
 try: app.announce('p','all','team')
 except PermissionError: pass
 else: raise AssertionError('player broadcast accepted')
 app.delete_profile('p'); assert app.events['e']['attendees']==['c']
def test_teamsync_performance_completed_events_and_history_are_preserved():
 m=load_solution(); app=m.TeamSync(); app.create_player('p','p@x','player',[(9,12)]); app.record_performance('p','speed',8); app.schedule('e',9,10,['p']); app.events['e']['completed']=True; app.delete_profile('p'); assert app.performance['p']==[('speed',8)]; assert app.events['e']['attendees']==['p']; assert ('profile_deleted','p') in app.history
def test_teamsync_event_contract_and_closure():
 m=load_solution(); r,c=event_docs(); assert m.EVENT_SCHEMA=='player_profile_v2'; assert r['authority']['contract']==m.EVENT_SCHEMA and r['authority']['stable_ids'] is True; assert c['preserved_workflows']==['performance_history','completed_events','communication_history','notification_preferences']
