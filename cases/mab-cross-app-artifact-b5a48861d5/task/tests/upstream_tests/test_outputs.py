from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
OUT=Path('/app/output_data')
def load_solution():
    spec=importlib.util.spec_from_file_location('codesquad_submission',OUT/'solution.py'); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod
def closure(): return json.loads((OUT/'coding_closure.json').read_text())

def test_codesquad_output_schema_and_artifacts():
    assert (OUT/'solution.py').is_file(); c=closure(); assert c['schema_version']=='async-rbench-mab-source-closure-v1' and c['case_id']=='mab-cross-app-artifact-b5a48861d5' and c['source_task_id']=='coding:063' and c['artifact_type']=='git_review_history_contract'; assert set(c['synchronized_surfaces'])=={'code_review','debug_chat','git_history'}

def test_codesquad_review_git_and_conflict_functionality():
    m=load_solution(); x=m.CodeSquad(); x.register('lead','password1','senior'); x.register('dev','password2'); lt=x.login('lead','password1'); dt=x.login('dev','password2'); r=x.create_review(lt,'repo','main','print(1)'); x.add_reviewer(lt,r.id,'dev'); x.annotate(dt,r.id,1,'fix'); x.send_chat(dt,r.id,'trace','error_log'); x.push(dt,r.id,'print(2)',0)
    try: x.push(lt,r.id,'stale',0); raise AssertionError('stale push accepted')
    except RuntimeError: pass
    assert r.version==1 and r.history==[{'version':0,'code':'print(1)'}] and r.annotations[0]['version']==0

def test_codesquad_preserves_auth_chat_transitions_and_dashboard():
    m=load_solution(); x=m.CodeSquad(); x.register('lead','password1','senior'); x.register('dev','password2'); lt=x.login('lead','password1'); dt=x.login('dev','password2'); r=x.create_review(lt,'repo','main','bug'); x.add_reviewer(lt,r.id,'dev'); x.send_chat(dt,r.id,'stack','error_log'); x.transition(dt,r.id,'resolved'); x.transition(lt,r.id,'reopened'); x.transition(lt,r.id,'escalated')
    assert x.dashboard(dt,'escalated','repo')==[{'id':r.id,'status':'escalated','version':0}]
    try: x.login('dev','wrongpass'); raise AssertionError('bad password accepted')
    except PermissionError: pass

def test_codesquad_event_receipt_and_post_event_closure():
    r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); c=closure(); a=r['authority']
    assert r['event']=='git_adapter_contract_delivered'; assert a['dependency']=='git_adapter_contract' and set(a['operations'])=={'pull','diff','push','history'} and a['conflict']=='non_fast_forward_requires_refresh'; assert m['event_receipt_sha256']==r['receipt_sha256'] and m['closure_complete'] and m['source_semantics_reverified']; assert c['event']==r['event']
