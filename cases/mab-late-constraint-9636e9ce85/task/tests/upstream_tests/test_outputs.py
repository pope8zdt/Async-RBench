from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); POLICY={'completion_requires':['all_dependencies_done','high_priority_manager_approval'],'overdue_alert_roles':['assignee','manager'],'allowed_statuses':['todo','in_progress','blocked','done']}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('office_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_office_output_schema_task_assignment_and_artifacts():
 m=load_solution(); app=m.OfficeTaskCollaborationManager(); assert m.DOMAIN=='office_task_collaboration_manager'; app.add_user('mgr','manager','ops'); app.add_user('ana','employee','ops'); app.apply_policy(POLICY); app.create_task('mgr','t','Prepare report','ana','ops'); assert app.tasks['t']['assignee']=='ana'; r,c=docs(); assert c['artifact_type']=='office_dependency_policy_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_office_dependency_approval_status_and_overdue_alert_behavior():
 m=load_solution(); app=m.OfficeTaskCollaborationManager(); app.add_user('mgr','manager','ops'); app.add_user('ana','employee','ops'); app.apply_policy(POLICY); app.create_task('mgr','base','Collect data','ana','ops',due_at=2); app.create_task('mgr','final','Publish','ana','ops',priority='high',due_at=3,dependencies=['base'])
 for call,exc in [(lambda:app.update_status('ana','final','done'),RuntimeError),(lambda:app.update_status('ana','final','unknown'),ValueError)]:
  try:call()
  except exc:pass
  else:raise AssertionError('invalid status accepted')
 app.update_status('ana','base','done')
 try:app.update_status('ana','final','done')
 except PermissionError:pass
 else:raise AssertionError('approval bypassed')
 app.approve('mgr','final'); assert app.update_status('ana','final','done')=='done'; app.create_task('mgr','late','Late item','ana','ops',due_at=1); assert app.generate_overdue_alerts(5)==[{'task_id':'late','recipients':['ana','mgr']}]
def test_office_delegation_comments_audit_and_reports_are_preserved():
 m=load_solution(); app=m.OfficeTaskCollaborationManager(); app.add_user('mgr','manager','ops'); app.add_user('a','employee','ops'); app.add_user('b','employee','ops'); app.apply_policy(POLICY); app.create_task('mgr','t','Coordinate','a','ops'); app.delegate('mgr','t','b'); app.comment('b','t','handoff complete'); app.update_status('b','t','in_progress'); report=app.report('ops'); assert app.tasks['t']['assignee']=='b' and app.comments[0]['text']=='handoff complete' and len(app.audit)==4 and report=={'department':'ops','total':1,'done':0,'blocked':0} and app.reports==[report]
def test_office_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='office_dependency_sla_policy_v2' and set(r['authority']['completion_requires'])=={'all_dependencies_done','high_priority_manager_approval'} and r['authority']['overdue_alert_roles']==['assignee','manager']; assert c['upstream_depth']==4 and c['preserved_workflows']==['task_assignments','collaboration_comments','task_audit_history','report_snapshots']
