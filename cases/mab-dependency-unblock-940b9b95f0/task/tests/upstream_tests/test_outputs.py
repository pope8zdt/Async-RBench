from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
 p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def event_docs():return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def assert_closure(k):
 r,c=event_docs(); assert c['case_id']=='mab-dependency-unblock-940b9b95f0' and c['source_task_id']=='coding:015' and c['artifact_type']==k and c['upstream_depth']==4; assert c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True
def test_matp_output_schema_and_artifacts():
 m=load_solution(); assert m.DOMAIN=='matp'; assert hasattr(m,'MATP'); assert_closure('realtime_multimodal_plan_closure')
def test_matp_fresh_snapshot_recomputes_rankings_and_ignores_stale_data():
 m=load_solution(); app=m.MATP(); routes=[{'id':'bike','mode':'cycling','minutes':20,'cost':0,'carbon':0},{'id':'bus','mode':'transit','minutes':15,'cost':3,'carbon':2}]; snap={'observed_at':100,'traffic_speeds':{},'transit_delays':{'transit':20},'weather_restrictions':['cycling']}; out=app.rank(routes,{'time':1,'cost':0,'carbon':0},snap,110); assert [r['id'] for r in out['fastest']]==['bus']; stale=app.rank(routes,{'time':1,'cost':0,'carbon':0},snap,1000); assert [r['id'] for r in stale['fastest']]==['bus','bike']
def test_matp_feedback_preferences_and_accepted_routes_are_preserved():
 m=load_solution(); app=m.MATP(); app.report('u','r','delay',2); app.accept('u',{'id':'r'}); assert app.feedback==[{'user':'u','route_id':'r','issue':'delay','rating':2}]; assert app.accepted==[('u','r')]
def test_matp_event_contract_and_closure():
 m=load_solution(); r,c=event_docs(); assert m.EVENT_SCHEMA=='conditions_snapshot_v3'; assert r['authority']['contract']==m.EVENT_SCHEMA and r['authority']['deterministic_adjustments'] is True; assert c['event_receipt_sha256']==r['receipt_sha256']
