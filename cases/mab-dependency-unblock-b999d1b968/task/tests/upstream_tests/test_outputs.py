from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); CONTRACT={'duration_origin':'task_created_at','assignment_policy':'unique_member_per_task','report_formats':['csv','pdf']}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('team_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_team_output_schema_projects_tasks_and_closure():
 m=load_solution(); x=m.TeamCollaborationManager(); x.add_user('ana'); x.apply_metric_contract(CONTRACT); x.create_project('p','Launch','2026-01-01','2026-01-31','release',['ana']); x.create_task('t','p','ana','2026-01-20',10); r,c=docs(); assert m.DOMAIN=='team_collaboration_manager' and c['artifact_type']=='team_collaboration_performance_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_team_task_transitions_concurrent_assignment_and_metrics():
 m=load_solution(); x=m.TeamCollaborationManager(); [x.add_user(u) for u in ['a','b']]; x.apply_metric_contract(CONTRACT); x.create_project('p','P','2026-01-01','2026-02-01','d',['a','b']); x.create_task('t','p','a','2026-01-20',10)
 try:x.create_task('t','p','b','2026-01-21',11)
 except ValueError:pass
 else:raise AssertionError('duplicate assignment accepted')
 x.set_status('t','in progress'); x.set_status('t','completed',16); d=x.dashboard('a'); assert d['completion_rate']==1 and d['average_completion_time']==6
def test_team_messages_attachments_feedback_and_reports_are_preserved():
 m=load_solution(); x=m.TeamCollaborationManager(); [x.add_user(u) for u in ['a','b']]; x.apply_metric_contract(CONTRACT); x.create_project('p','P','2026-01-01','2026-02-01','d',['a','b']); x.create_task('t','p','a','2026-01-20',1); x.post_message('b','review','p','t','spec.pdf'); x.add_feedback('b','a',5,'solid'); assert x.messages[0]['attachment']=='spec.pdf' and x.dashboard('a')['average_rating']==5 and 'task_id,assignee,status,deadline' in x.export_project_csv('p')
def test_team_event_metric_contract_and_final_reverification():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='team_performance_metric_contract_v2' and r['authority']['duration_origin']=='task_created_at' and r['authority']['assignment_policy']=='unique_member_per_task'; assert c['upstream_depth']==4 and c['source_semantics_reverified'] is True
