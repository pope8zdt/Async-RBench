from __future__ import annotations
import importlib.util, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT=Path('/app/output_data')
def load_solution():
    spec=importlib.util.spec_from_file_location('office_submission',OUT/'solution.py'); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod
def closure(): return json.loads((OUT/'coding_closure.json').read_text())

def test_office_output_schema_and_artifacts():
    assert (OUT/'solution.py').is_file()
    c=closure(); assert c['schema_version']=='async-rbench-mab-source-closure-v1'; assert c['case_id']=='mab-cross-app-artifact-4e6f0120bd'; assert c['source_task_id']=='coding:059'; assert c['artifact_type']=='calendar_deadline_sync_contract'
    assert set(c['synchronized_surfaces'])=={'task_dashboard','google_calendar','outlook_calendar'}

def test_office_task_calendar_functionality():
    m=load_solution(); x=m.Office_Task_Collaborator(); x.add_user('lead'); x.add_user('dev')
    due=datetime.now(timezone.utc)+timedelta(hours=2); t=x.create_task('lead','Apollo','Ship','x'*10000,due,'high','dev')
    g=x.sync_calendar('dev',t.id,'google'); o=x.sync_calendar('lead',t.id,'outlook')
    assert g['task_id']==o['task_id']==t.id and g['deadline']==o['deadline']==due.isoformat() and g['uid']!=o['uid']

def test_office_preserves_assignment_messaging_dashboard_and_report():
    m=load_solution(); x=m.Office_Task_Collaborator(); x.add_user('lead'); x.add_user('dev')
    due=datetime.now(timezone.utc)+timedelta(days=1); assigned=x.create_task('lead','Apollo','Ship','details',due,'urgent','dev'); unassigned=x.create_task('lead','Apollo','Backlog','none',due,'low')
    x.message('dev',assigned.id,'working'); x.update_status('dev',assigned.id,'completed')
    assert x.dashboard('dev')['completed']==[assigned.id]; report=x.report('lead','Apollo'); assert report['total']==2 and report['completed']==1 and report['completion_rate']==0.5; assert unassigned.assignee is None

def test_office_event_receipt_and_post_event_closure():
    r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); c=closure(); p=json.loads((OUT/'preserved_source_facts.json').read_text())
    assert r['event']=='calendar_adapter_contract_delivered'; a=r['authority']; assert a['stable_id_field']=='provider_event_id' and set(a['operations'])=={'create','update','cancel'} and a['conflict_policy']=='newer_task_revision_wins'
    assert m['event_receipt_sha256']==r['receipt_sha256'] and m['event_consumed'] and m['source_semantics_reverified'] and m['closure_complete']; assert c['event']=='calendar_adapter_contract_delivered' and p['preserved'] is True
