from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
CASES=[{'input':[],'expected':[]},{'input':[3,1,3],'expected':[1,3,3]},{'input':[-2,4,0],'expected':[-2,0,4]}]
def load_solution():
 p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('familyquest_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_familyquest_output_schema_and_artifacts():
 m=load_solution(); assert m.DOMAIN=='family_code_quest' and hasattr(m,'FamilyCodeQuest'); r,c=docs(); assert c['artifact_type']=='family_code_quest_test_closure' and c['upstream_depth']==4 and c['event_receipt_sha256']==r['receipt_sha256']
def test_familyquest_sort_boundaries_and_duplicate_evidence_are_idempotent():
 m=load_solution(); q=m.FamilyCodeQuest(); q.add_user('parent','adult'); q.add_user('child','child'); q.add_challenge('sort','beginner','sort_numbers'); q.start_session('s',['parent','child'],'sort'); first=q.apply_test_evidence('sorting-boundaries-2026-08','sort',CASES); replay=q.apply_test_evidence('sorting-boundaries-2026-08','sort',CASES)
 assert first=={'status':'applied','applied':3} and replay=={'status':'duplicate','applied':0} and q.evidence_application_count==1; assert q.run_registered_tests('sort')=={'passed':3,'total':3,'all_passed':True}; assert q.submit('child','sort',[-1,2,-1])['result']==[-1,-1,2]
def test_familyquest_collaboration_progress_and_feedback_are_preserved():
 m=load_solution(); q=m.FamilyCodeQuest(); q.add_user('p','adult'); q.add_user('c','child'); q.add_challenge('sort','beginner','sort_numbers'); q.start_session('home',['p','c'],'sort'); q.collaborate('home','c','def solve(xs): return sorted(xs)','ready'); q.apply_test_evidence('e','sort',CASES); q.submit('c','sort',[2,1]); hint=q.get_hint('c','sort',2); saved=q.save_progress('c')
 assert q.sessions['home']['revision']==1 and q.history and 'duplicates' in hint and q.hints; assert saved['completed']==['sort'] and q.load_progress('c')==saved
def test_familyquest_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='family_code_quest_tests_v2'; assert r['authority']['evidence_id']=='sorting-boundaries-2026-08' and len(r['authority']['cases'])==3; assert c['preserved_workflows']==['shared_sessions','saved_progress','hint_history','collaboration_history'] and c['source_semantics_reverified'] is True
