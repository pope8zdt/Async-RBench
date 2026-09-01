from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); CONTRACT={'constraints':['availability','task_dependencies','no_overlap','priority','feedback'],'slot_minutes':30}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('schedule_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_schedule_output_schema_tasks_and_artifacts():
 m=load_solution(); p=m.CollaborativeSchedulePlanner(); assert m.DOMAIN=='collaborative_schedule_planner'; p.add_user('a',[0,1,2]); p.add_task('t','a','Plan',30,2); p.apply_optimizer_contract(CONTRACT); assert p.optimize()['t']['start_slot']==0; r,c=docs(); assert c['artifact_type']=='team_schedule_optimizer_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_schedule_dependencies_availability_non_overlap_priority_and_feedback():
 m=load_solution(); p=m.CollaborativeSchedulePlanner(); p.add_user('a',[0,1,2,3]); p.add_task('base','a','Base',60,1); p.add_task('urgent','a','Urgent',30,3,['base']); p.add_task('other','a','Other',30,2); p.apply_optimizer_contract(CONTRACT); p.provide_feedback('a','other',2); s=p.optimize(); assert s['base']['end_slot']<=s['urgent']['start_slot'] and len({x for v in s.values() for x in range(v['start_slot'],v['end_slot'])})==4 and s['other']['priority']==4
def test_schedule_edits_feedback_notifications_and_reports_are_preserved():
 m=load_solution(); p=m.CollaborativeSchedulePlanner(); p.add_user('a',[0,1,2]); p.add_task('t','a','Draft',30,1); p.edit_task('a','t',name='Final'); p.provide_feedback('a','t',2); p.apply_optimizer_contract(CONTRACT); p.optimize(); report=p.report(); assert p.tasks['t']['name']=='Final' and p.notifications[0]['changes']==['name'] and p.feedback[0]['delta']==2 and report['minutes_by_user']=={'a':30} and p.reports==[report]
def test_schedule_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='team_schedule_optimizer_v2' and set(r['authority']['constraints'])=={'availability','task_dependencies','no_overlap','priority','feedback'} and r['authority']['slot_minutes']==30; assert c['upstream_depth']==4 and c['preserved_workflows']==['user_tasks','team_feedback','change_notifications','gantt_and_usage_reports']
