from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
    p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def event_docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def assert_closure(kind):
    r,c=event_docs(); assert c['case_id']=='mab-dependency-unblock-1247bebf08' and c['source_task_id']=='coding:016'; assert c['artifact_type']==kind and c['upstream_depth']==4; assert c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True

def test_project_manager_output_schema_and_artifacts():
    m=load_solution(); assert m.DOMAIN=='multiagent_project_manager'; assert hasattr(m,'MultiAgentProjectManager'); assert_closure('transitive_project_dependency_closure')

def test_project_manager_cycle_transitive_readiness_and_dashboard():
    m=load_solution(); app=m.MultiAgentProjectManager(); app.add_user('pm','Project Manager'); app.add_user('dev','Team Member'); app.create_project('p','pm'); app.add_task('p','a','root','d',assignee='dev'); app.add_task('p','b','middle','d',['a'],'dev'); app.add_task('p','c','leaf','d',['b'],'dev'); app.projects['p']['tasks']['b']['status']='completed'; assert app.ready('p','c') is False; assert app.dashboard('p')['c']['blocking']==[]
    try: app.add_task('p','x','bad','d',['x'],'dev')
    except ValueError: pass
    else: raise AssertionError('self dependency accepted')

def test_project_manager_roles_notifications_and_audit_are_preserved():
    m=load_solution(); app=m.MultiAgentProjectManager(); app.add_user('pm','Project Manager'); app.add_user('dev','Team Member'); app.create_project('p','pm'); app.add_task('p','a','root','d',assignee='dev'); app.complete('p','a','dev'); assert ('completed','p','a') in app.history; assert ('dev','task_completed','a') in app.notifications; assert app.projects['p']['status']=='completed'

def test_project_manager_event_contract_and_closure():
    m=load_solution(); receipt,closure=event_docs(); assert m.EVENT_SCHEMA=='cycle_safe_dependency_v2'; assert receipt['authority']['contract']==m.EVENT_SCHEMA; assert closure['preserved_workflows']==['role_assignments','task_history','notification_preferences','completed_tasks']
