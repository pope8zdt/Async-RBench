from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
OUT=Path('/app/output_data')
def load_solution():
    spec=importlib.util.spec_from_file_location('questhub_submission',OUT/'solution.py'); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod
def closure(): return json.loads((OUT/'coding_closure.json').read_text())
def prepared():
    m=load_solution(); x=m.QuestHub(); x.register('hero','password1'); x.register('ally','password2'); return x,x.login('hero','password1','pc'),x.login('ally','password2','mobile')

def test_questhub_output_schema_and_artifacts():
    assert (OUT/'solution.py').is_file(); c=closure(); assert c['schema_version']=='async-rbench-mab-source-closure-v1' and c['case_id']=='mab-cross-app-artifact-496566389d' and c['source_task_id']=='coding:070' and c['artifact_type']=='versioned_quest_skill_sync_contract'; assert set(c['synchronized_surfaces'])=={'quest_board','skill_planner','device_sync'}

def test_questhub_versioned_quest_and_stale_write_functionality():
    x,ht,at=prepared(); q=x.create_quest(ht,'Dragon'); x.share_quest(ht,q.quest_id,'ally'); events=[]; x.subscribe(at,'quest:1',events.append); x.update_quest(at,q.quest_id,'active',0)
    try: x.update_quest(ht,q.quest_id,'completed',0); raise AssertionError('stale quest write accepted')
    except RuntimeError: pass
    assert q.status=='active' and q.version==1 and events[-1]['version']==1

def test_questhub_preserves_auth_skill_collaboration_and_ordered_sync():
    x,ht,at=prepared(); p=x.create_skill_plan(ht,'Mage'); x.share_plan(ht,p.plan_id,'ally'); x.set_skill(at,p.plan_id,'Fireball',70,0); delta=x.sync_since(at,0)
    assert p.skills=={'Fireball':70} and p.version==1 and [e['sequence'] for e in delta]==sorted(e['sequence'] for e in delta)
    try: x.login('hero','badpass1','pc'); raise AssertionError('bad login accepted')
    except PermissionError: pass

def test_questhub_event_receipt_and_post_event_closure():
    r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); c=closure(); a=r['authority']
    assert r['event']=='quest_sync_contract_delivered'; assert a['dependency']=='questhub_sync_contract' and a['revision_field']=='record_revision' and a['idempotency_field']=='event_idempotency_key'; assert m['event_receipt_sha256']==r['receipt_sha256'] and m['closure_complete'] and m['source_semantics_reverified']; assert c['event']==r['event']
