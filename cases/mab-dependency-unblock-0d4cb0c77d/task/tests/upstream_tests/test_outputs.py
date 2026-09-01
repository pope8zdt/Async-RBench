from __future__ import annotations
import importlib.util, json, pathlib
OUT=pathlib.Path('/app/output_data')

def load_solution():
    path=OUT/'solution.py'; assert path.is_file()
    spec=importlib.util.spec_from_file_location('submitted_solution',path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def event_docs():
    return json.loads((OUT/'event_receipt.json').read_text()), json.loads((OUT/'coding_closure.json').read_text())

def assert_closure(kind):
    receipt,closure=event_docs(); assert closure['case_id']=='mab-dependency-unblock-0d4cb0c77d'; assert closure['source_task_id']=='coding:021'; assert closure['artifact_type']==kind; assert closure['source_semantics_reverified'] is True; assert closure['event_receipt_sha256']==receipt['receipt_sha256']

def test_teamsync_output_schema_and_artifacts():
    m=load_solution(); assert m.DOMAIN=='team_sync_pro'; assert hasattr(m,'TeamSyncPro'); assert_closure('teamsync_adaptive_schedule_closure')

def test_teamsync_priority_dependencies_assignments_and_notifications():
    m=load_solution(); app=m.TeamSyncPro(); app.add_member('ana',['09:00']); app.add_member('bo',['10:00']); app.add_task('low',1,1); app.add_task('urgent',1,9); schedule=app.apply_adaptive_schedule(); assert schedule['urgent']=={'member':'ana','slot':'09:00','duration':1}; assert len(app.notifications)==2

def test_teamsync_preserves_messages_and_reports_after_reschedule():
    m=load_solution(); app=m.TeamSyncPro(); app.add_member('ana',['09:00']); app.add_task('design',1,3); app.message('ana','keep requirements'); app.apply_adaptive_schedule(); report=app.productivity_report(); assert app.messages==[{'sender':'ana','text':'keep requirements'}]; assert report['contributions']=={'ana':1}

def test_teamsync_event_receipt_and_post_event_closure():
    receipt,closure=event_docs(); assert 'dependencies' in receipt['authority']['inputs']; assert 'unassigned_reasons' in receipt['authority']['outputs']; assert closure['event_receipt_sha256']==receipt['receipt_sha256']
