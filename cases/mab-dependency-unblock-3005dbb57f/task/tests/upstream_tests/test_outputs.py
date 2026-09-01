from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
    p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def event_docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def assert_closure(kind):
    r,c=event_docs(); assert c['case_id']=='mab-dependency-unblock-3005dbb57f' and c['source_task_id']=='coding:009'; assert c['artifact_type']==kind and c['upstream_depth']==4; assert c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True

def test_music_hub_output_schema_and_artifacts():
    m=load_solution(); assert m.DOMAIN=='music_collaboration_hub'; assert hasattr(m,'MusicCollaborationHub'); assert_closure('versioned_loop_analysis_closure')

def test_music_hub_version_isolation_transposition_and_fixed_bins():
    m=load_solution(); app=m.MusicCollaborationHub(); app.create_project('p','ana'); app.join('p','bo'); app.add_loop('p','l','ana',[1,-1,2,-2,3,-3,4,-4],'C'); app.edit_loop('p','l','bo',[2]*8); assert [v['version'] for v in app.projects['p']['loops']['l']]==[1,2]; a=app.analyze('p','l',1,transpose=2,bins=8); assert a['detected_key']=='D'; assert len(a['waveform_bins'])==8; assert a['version']==1

def test_music_hub_chat_concurrent_edits_and_history_are_preserved():
    m=load_solution(); app=m.MusicCollaborationHub(); app.create_project('p','ana'); app.join('p','bo'); app.add_loop('p','l','ana',[1]*8); app.chat('p','ana','keep intro'); app.edit_loop('p','l','bo',[2]*8); assert app.projects['p']['chat']==[('ana','keep intro')]; assert len(app.projects['p']['loops']['l'])==2; assert app.projects['p']['events'][0]['type']=='loop_version'

def test_music_hub_event_contract_and_closure():
    m=load_solution(); receipt,closure=event_docs(); assert m.EVENT_SCHEMA=='loop_analysis_v3'; assert receipt['authority']['version_bound'] is True; assert receipt['authority']['fixed_bins']==8; assert receipt['authority']['contract']==m.EVENT_SCHEMA; assert closure['event_receipt_sha256']==receipt['receipt_sha256']
