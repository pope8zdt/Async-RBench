from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
    p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def event_docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def assert_closure(kind):
    r,c=event_docs(); assert c['case_id']=='mab-dependency-unblock-19d693bd13' and c['source_task_id']=='coding:018'; assert c['artifact_type']==kind and c['upstream_depth']==4; assert c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True

def test_ecosphere_output_schema_and_artifacts():
    m=load_solution(); assert m.DOMAIN=='ecosphere_manager'; assert hasattr(m,'EcoSphereManager'); assert_closure('deterministic_ecosystem_tick_closure')

def test_ecosphere_tick_is_deterministic_atomic_and_health_is_derived():
    m=load_solution(); a=m.EcoSphereManager(); b=m.EcoSphereManager(); [x.add_species('deer',20,40,1,'forest') for x in (a,b)]; one=a.tick(7,pollution_delta=20); two=b.tick(7,pollution_delta=20); assert one==two; assert one['health']!=50.0; assert one['pollution']==20.0; assert one['species']['deer']['population']<=40

def test_ecosphere_collaboration_habitats_and_history_are_preserved():
    m=load_solution(); app=m.EcoSphereManager(); app.add_species('fox',4,10,2,'woodland'); app.collaborate('ana','reduce pollution'); app.tick(3,disaster=1); assert app.messages==[('ana','reduce pollution')]; assert app.habitats['fox']=='woodland'; assert app.history[0]['seed']==3

def test_ecosphere_event_contract_and_closure():
    m=load_solution(); receipt,closure=event_docs(); assert m.EVENT_SCHEMA=='ecosystem_tick_v2'; assert receipt['authority']['atomic'] is True; assert receipt['authority']['contract']==m.EVENT_SCHEMA; assert closure['event_receipt_sha256']==receipt['receipt_sha256']
