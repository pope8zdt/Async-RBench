from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
    p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def event_docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def assert_closure(kind):
    r,c=event_docs(); assert c['case_id']=='mab-dependency-unblock-2cf6576816' and c['source_task_id']=='coding:068'; assert c['artifact_type']==kind and c['upstream_depth']==4; assert c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True

def test_multiserve_output_schema_and_artifacts():
    m=load_solution(); assert m.DOMAIN=='multiserve'; assert hasattr(m,'MultiServe'); assert_closure('multi_restaurant_logistics_closure')

def test_multiserve_partitions_suborders_aggregates_status_and_assigns_agents():
    m=load_solution(); app=m.MultiServe(); app.add_restaurant('r1',['soup']); app.add_restaurant('r2',['rice']); app.add_agent('a1'); app.add_agent('a2'); sub=app.place_order('o','u',[{'restaurant':'r1','item':'soup'},{'restaurant':'r2','item':'rice'}]); assert set(sub)=={'r1','r2'}; assert app.set_suborder_status('o','r1','ready')=='partially_ready'; assert app.set_suborder_status('o','r2','ready')=='ready'; tasks=app.assign_deliveries('o'); assert {v['agent'] for v in tasks.values()}=={'a1','a2'}

def test_multiserve_cancellation_restaurant_state_and_notifications_are_preserved():
    m=load_solution(); app=m.MultiServe(); app.add_restaurant('r1',['soup']); app.add_agent('a1'); app.place_order('o','u',[{'restaurant':'r1','item':'soup'}]); app.set_suborder_status('o','r1','ready'); app.cancel('o'); assert app.assign_deliveries('o')=={}; assert app.orders['o']['status']=='canceled'; assert ('u','canceled') in app.notifications

def test_multiserve_event_contract_and_closure():
    m=load_solution(); receipt,closure=event_docs(); assert m.EVENT_SCHEMA=='suborder_logistics_v3'; assert receipt['authority']['recovery']=='redelegated'; assert receipt['authority']['contract']==m.EVENT_SCHEMA; assert closure['preserved_workflows']==['cart_items','restaurant_decisions','cancellation_state','user_notifications']
