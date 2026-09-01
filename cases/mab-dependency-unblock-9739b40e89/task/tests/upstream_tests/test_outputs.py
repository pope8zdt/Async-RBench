from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
 p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def event_docs():return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def assert_closure(k):
 r,c=event_docs(); assert c['case_id']=='mab-dependency-unblock-9739b40e89' and c['source_task_id']=='coding:072' and c['artifact_type']==k and c['upstream_depth']==4; assert c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True
def test_mashup_output_schema_and_artifacts():
 m=load_solution(); assert m.DOMAIN=='music_mashup_battle'; assert hasattr(m,'MusicMashupBattle'); assert_closure('ordered_mashup_room_closure')
def test_mashup_ordered_events_resync_playback_votes_and_leaderboard():
 m=load_solution(); app=m.MusicMashupBattle(); app.create_room('r','a',True); assert app.apply_event('r',{'sequence':2,'type':'join','actor':'b'})=={'status':'resync_required','expected':1}; app.apply_event('r',{'sequence':1,'type':'join','actor':'b'}); app.apply_event('r',{'sequence':2,'type':'playback','actor':'a','position':30}); assert app.rooms['r']['playback']==30; assert app.vote('a','m',5)['status']=='accepted'; assert app.vote('a','m',5)['status']=='duplicate'; assert app.leaderboard()==[('m',5)]
def test_mashup_room_history_chat_membership_and_versions_are_preserved():
 m=load_solution(); app=m.MusicMashupBattle(); app.create_room('r','a',True); app.apply_event('r',{'sequence':1,'type':'join','actor':'b'}); app.apply_event('r',{'sequence':2,'type':'chat','actor':'b','message':'drop beat'}); app.apply_event('r',{'sequence':3,'type':'edit','actor':'a','operation':{'effect':'echo'}}); room=app.rooms['r']; assert room['participants']=={'a','b'} and room['chat']==[('b','drop beat')] and len(room['history'])==3 and room['edits'][0]['sequence']==3
def test_mashup_event_contract_and_closure():
 m=load_solution(); r,c=event_docs(); assert m.EVENT_SCHEMA=='mashup_room_events_v3'; assert r['authority']['contract']==m.EVENT_SCHEMA and r['authority']['ordered_sequence'] is True; assert c['event_receipt_sha256']==r['receipt_sha256']
