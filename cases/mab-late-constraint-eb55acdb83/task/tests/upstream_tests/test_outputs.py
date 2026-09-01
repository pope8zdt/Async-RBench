import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def load():
 s=importlib.util.spec_from_file_location('solution',OUT/'solution.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def test_native_binding_and_schema():
 n=json.loads(FIX.read_text()); c=json.loads((OUT/'negotiation_closure.json').read_text()); assert n['case_id']=='mab-late-constraint-eb55acdb83' and n['source_task_id']=='bargaining:031' and n['official_evaluator']=='marble.evaluator.evaluator.Evaluator.evaluate_code_quality'; assert c['artifact_type']=='vacationer_bag_feature_closure' and c['upstream_depth']==3
def test_core_behavior():
 m=load(); x=m.VacationerBagNegotiation(); r=x.offer(m.PROVISIONAL); r=x.apply_authority(r,m.AUTHORITY); r=x.counter(r,m.CANONICAL_CHOICE); f=x.finalize(r); a=x.audit(); assert f=={'status':'agreement','terms':m.CANONICAL_CHOICE} and a['chronological'] and a['provisional_excluded']
def test_event_behavior():
 m=load(); c=json.loads((OUT/'negotiation_closure.json').read_text()); assert m.EVENT_SCHEMA=='current_capacity_feature_counter' and m.AUTHORITY=={'current_counter': {'unit_price': 82.0, 'minimum_order': 40, 'washable_lining': True, 'compartments': 12}, 'supersedes': {'unit_price': 80.0, 'features': 'unspecified'}} and c['authority_applied']
def test_edge_behavior():
 m=load(); x=m.VacationerBagNegotiation(); r=x.offer(m.PROVISIONAL)
 try: x.apply_authority(r-1,m.AUTHORITY)
 except RuntimeError: pass
 else: raise AssertionError('stale authority accepted')
 try: x.apply_authority(r,{'unauthorized':True})
 except ValueError: pass
 else: raise AssertionError('unauthorized authority accepted')
def test_event_closure_and_preservation():
 r=json.loads((OUT/'event_receipt.json').read_text()); c=json.loads((OUT/'negotiation_closure.json').read_text()); assert r['event_theme']=='late_or_out_of_order_superseded_result' and c['preserved_workflows']==['vacationer_bag_identity', 'buyer_scalability_priority', 'seller_margin_goal']
def test_final_terms_and_tool_sequence():
 c=json.loads((OUT/'negotiation_closure.json').read_text()); assert c['selected_terms']=={'unit_price': 82.0, 'minimum_order': 40, 'washable_lining': True, 'compartments': 12} and c['tool_sequence']==['offer','authority','counter','finalize']
