from __future__ import annotations
import importlib.util, json, pathlib
OUT=pathlib.Path('/app/output_data')

def load_solution():
    path=OUT/'solution.py'; assert path.is_file()
    spec=importlib.util.spec_from_file_location('submitted_solution',path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def event_docs():
    return json.loads((OUT/'event_receipt.json').read_text()), json.loads((OUT/'coding_closure.json').read_text())

def assert_closure(kind):
    receipt,closure=event_docs(); assert closure['case_id']=='mab-dependency-unblock-0de81e81ac'; assert closure['source_task_id']=='coding:002'; assert closure['artifact_type']==kind; assert closure['source_semantics_reverified'] is True; assert closure['event_receipt_sha256']==receipt['receipt_sha256']

def test_foodchain_output_schema_and_artifacts():
    m=load_solution(); assert m.DOMAIN=='food_chain'; assert hasattr(m,'FoodChain'); assert_closure('foodchain_dynamic_delivery_closure')

def test_foodchain_restaurant_modification_and_delivery_lifecycle():
    m=load_solution(); app=m.FoodChain(); app.add_restaurant('r',{'soup':8,'rice':3}); app.place_order('o','c','r',['soup','rice']); modified=app.restaurant_decision('o','modify',['rice']); assert modified['items']==['rice']; app.assign_courier('o','d'); app.courier_status('o','picked_up'); app.courier_status('o','delivered'); assert app.orders['o']['status']=='delivered'

def test_foodchain_traffic_replans_route_priority_eta_and_preserves_feedback():
    m=load_solution(); app=m.FoodChain(); app.add_restaurant('r',{'rice':3}); app.place_order('o','c','r',['rice']); app.restaurant_decision('o','accept'); app.assign_courier('o','d'); route=app.replan('o',['jammed','clear'],{'jammed':4,'clear':1}); app.rate('o',5,4); assert route['route']==['clear','jammed']; assert route['priority']=='high' and route['eta_minutes']==35; assert app.feedback[0]['restaurant']==5

def test_foodchain_event_receipt_and_post_event_closure():
    receipt,closure=event_docs(); assert receipt['authority']['failure']=='implicit_no_result'; assert receipt['authority']['traffic_policy']=='avoid_high_traffic'; assert closure['event_receipt_sha256']==receipt['receipt_sha256']
