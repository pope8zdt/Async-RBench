from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
 p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def assert_closure(kind):
 r,c=docs(); assert c['artifact_type']==kind and c['upstream_depth']==4 and c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True
def test_teamsyncpro_output_schema_and_artifacts():
 m=load_solution(); assert m.DOMAIN=='team_sync_pro' and hasattr(m,'TeamSyncPro'); assert_closure('department_rbac_api_closure')
def test_teamsyncpro_department_role_endpoint_fields_and_frontend_visibility():
 m=load_solution(); app=m.TeamSyncPro(); app.add_user('mgr','sales','manager'); app.add_user('mem','sales','member'); app.add_user('admin','hq','admin'); app.create_task('mgr','t','Pitch','sales'); app.create_task('admin','e','Engine','engineering')
 for call in [lambda:app.create_task('mgr','x','Cross','engineering'),lambda:app.create_task('mem','x','No','sales'),lambda:app.authorize('mgr','POST','/tasks',{'task_id','title','department','extra'},'sales')]:
  try: call()
  except PermissionError: pass
  else: raise AssertionError('RBAC/API violation accepted')
 assert '/messages' in app.visible_actions('mem') and '/tasks' not in app.visible_actions('mem')
def test_teamsyncpro_tasks_allocations_messages_reports_and_audit_are_preserved():
 m=load_solution(); app=m.TeamSyncPro(); app.add_user('mgr','sales','manager'); app.add_user('mem','sales','member'); app.create_task('mgr','t','Pitch','sales'); app.allocate('mgr','t','r','sales'); app.communicate('mem','team','ready','sales'); report=app.performance_report('mgr','sales')
 assert app.tasks['t']['title']=='Pitch' and app.allocations==[('t','r','sales')] and app.messages[0]['message']=='ready'; assert report['open_tasks']==1 and len(app.audit)==2
def test_teamsyncpro_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='department_rbac_api_v3'; assert r['authority']['contract']==m.EVENT_SCHEMA and set(r['authority']['operations'])=={'task','resource','communication','performance'}; assert c['preserved_workflows']==['task_history','resource_allocations','communication_logs','report_snapshots']
