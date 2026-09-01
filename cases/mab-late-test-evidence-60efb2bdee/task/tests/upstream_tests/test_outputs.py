from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); CASES=['nonexistent_assignee','past_deadline','unauthorized_task_access','overdue_report']
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('office_sched_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_office_scheduler_output_schema_dashboard_and_artifacts():
 m=load_solution(); s=m.OfficeTaskScheduler(); assert m.DOMAIN=='office_task_scheduler'; s.add_user('a'); s.add_user('b'); s.create_task('a','t','Review','b',120,'high'); assert s.dashboard('b')[0]['task_id']=='t'; r,c=docs(); assert c['artifact_type']=='office_scheduler_test_evidence_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_office_scheduler_edge_cases_and_replay_are_idempotent():
 m=load_solution(); s=m.OfficeTaskScheduler(); s.add_user('a'); s.add_user('b'); s.add_user('x'); first=s.apply_test_evidence('office-edge-suite-2026-08',CASES); replay=s.apply_test_evidence('office-edge-suite-2026-08',CASES); assert first['applied']==4 and replay=={'status':'duplicate','applied':0} and s.evidence_application_count==1
 for call,exc in [(lambda:s.create_task('a','x','Bad','missing',120,'low'),KeyError),(lambda:s.create_task('a','x','Bad','b',99,'low'),ValueError)]:
  try:call()
  except exc:pass
  else:raise AssertionError('edge case accepted')
 s.create_task('a','t','Valid','b',110,'high')
 try:s.update_status('x','t','completed')
 except PermissionError:pass
 else:raise AssertionError('unauthorized access accepted')
def test_office_scheduler_status_comments_notifications_and_reports_are_preserved():
 m=load_solution(); s=m.OfficeTaskScheduler(); s.add_user('a'); s.add_user('b'); s.create_task('a','t','Valid','b',110,'medium'); s.update_status('b','t','in_progress'); s.add_comment('b','t','working'); assert s.deadline_notifications(105)==[{'user':'b','kind':'deadline','task':'t'}]; report=s.report(111); assert report['overdue']==['t'] and report['distribution']['b']==1 and s.comments[0]['text']=='working' and len(s.history)==3 and s.reports==[report]
def test_office_scheduler_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='office_scheduler_edge_tests_v2' and r['authority']['evidence_id']=='office-edge-suite-2026-08' and set(r['authority']['cases'])==set(CASES); assert c['upstream_depth']==4 and c['preserved_workflows']==['task_assignments','status_history','task_comments','notification_and_report_history']
