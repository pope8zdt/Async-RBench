from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
OUT=Path('/app/output_data')
def load_solution():
    spec=importlib.util.spec_from_file_location('booksynergy_submission',OUT/'solution.py'); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod
def closure(): return json.loads((OUT/'coding_closure.json').read_text())
def prepared():
    m=load_solution(); x=m.BookSynergy(); x.register('owner','password1','publisher'); x.register('writer','password2'); ot=x.authenticate('owner','password1'); wt=x.authenticate('writer','password2'); p=x.create_project(ot,'Reference'); x.add_member(ot,p.project_id,'writer','edit'); return x,ot,wt,p

def test_booksynergy_output_schema_and_artifacts():
    assert (OUT/'solution.py').is_file(); c=closure(); assert c['schema_version']=='async-rbench-mab-source-closure-v1' and c['case_id']=='mab-cross-app-artifact-2763fffe05' and c['source_task_id']=='coding:064' and c['artifact_type']=='immutable_revision_parent_schema'; assert set(c['synchronized_surfaces'])=={'editor','realtime_subscriber','external_integration'}

def test_booksynergy_immutable_revision_functionality():
    x,ot,wt,p=prepared(); events=[]; x.subscribe(wt,p.project_id,events.append); r1=x.commit(ot,p.project_id,'# One',None); r2=x.commit(wt,p.project_id,'# Two',r1.number)
    try: x.commit(wt,p.project_id,'stale',r1.number); raise AssertionError('stale parent accepted')
    except RuntimeError: pass
    assert r1.parent is None and r2.parent==r1.number and events[-1]['revision']==r2.number

def test_booksynergy_preserves_membership_render_and_external_export():
    x,ot,wt,p=prepared(); r=x.commit(ot,p.project_id,'**Reference**',None); rendered=x.render(wt,p.project_id,True); export=x.export_integration(ot,p.project_id,'github',b'x'*10000)
    assert rendered['markdown']=='**Reference**' and '<strong>' in rendered['wysiwyg_html']; assert export['revision']==r.number and len(export['large_file_sha256'])==64
    try: x.export_integration(wt,p.project_id,'github'); raise AssertionError('writer published')
    except PermissionError: pass

def test_booksynergy_event_receipt_and_post_event_closure():
    r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); c=closure(); a=r['authority']
    assert r['event']=='authoritative_revision_schema_delivered'; assert a['result']=='booksynergy_revision_schema' and a['revision_rule']=='immutable_parent_chain' and a['stale_parent']=='reject'; assert m['event_receipt_sha256']==r['receipt_sha256'] and m['event_consumed'] and m['closure_complete']; assert c['event']==r['event']
