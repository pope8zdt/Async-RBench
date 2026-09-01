from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
 p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def event_docs():return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def assert_closure(k):
 r,c=event_docs(); assert c['case_id']=='mab-dependency-unblock-8d29bb0513' and c['source_task_id']=='coding:041' and c['artifact_type']==k and c['upstream_depth']==4; assert c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True
def test_travel_output_schema_and_artifacts():
 m=load_solution(); assert m.DOMAIN=='travel_collaborator'; assert hasattr(m,'TravelCollaborator'); assert_closure('authorized_travel_collaboration_closure')
def test_travel_sessions_roles_privacy_and_forged_actors():
 m=load_solution(); app=m.TravelCollaborator(); app.register('a','pw',True); app.register('b','pw'); ta=app.login('a','pw',0); tb=app.login('b','pw',0); app.create_itinerary(ta,1,'i'); app.invite(ta,1,'i','b','viewer')
 try: app.add_item(tb,1,'i',{'day':1})
 except PermissionError: pass
 else: raise AssertionError('viewer wrote itinerary')
 try: app.actor('forged:0',1)
 except PermissionError: pass
 else: raise AssertionError('forged actor accepted')
 try: app.actor(ta,61)
 except PermissionError: pass
 else: raise AssertionError('expired session accepted')
 assert app.profile('b','a')=={'name':'private'}
def test_travel_comments_chat_reviews_and_changes_are_preserved():
 m=load_solution(); app=m.TravelCollaborator(); app.register('a','pw'); app.register('b','pw'); ta=app.login('a','pw',0); tb=app.login('b','pw',0); app.create_itinerary(ta,1,'i'); app.invite(ta,1,'i','b','contributor'); app.add_item(tb,1,'i',{'day':1}); app.comment(tb,1,'i','museum'); assert app.itineraries['i']['items']==[{'day':1}]; assert app.itineraries['i']['comments']==[('b','museum')]; assert app.chat==[('i','b','museum')]
def test_travel_event_contract_and_closure():
 m=load_solution(); r,c=event_docs(); assert m.EVENT_SCHEMA=='travel_auth_v2'; assert r['authority']['contract']==m.EVENT_SCHEMA and r['authority']['forged_actor_rejected'] is True; assert c['preserved_workflows']==['itinerary_comments','chat_history','reviews','accepted_changes']
