import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data');FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def load():
 s=importlib.util.spec_from_file_location('solution',OUT/'solution.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def test_native_binding_and_schema():
 n=json.loads(FIX.read_text());z=json.loads((OUT/'negotiation_closure.json').read_text());assert n['case_id']=='mab-late-constraint-6f495ee7e8' and n['source_task_id']=='bargaining:046' and n['official_evaluator']=='marble.evaluator.evaluator.Evaluator.evaluate_code_quality';assert z['artifact_type']=='kohler_valve_delivery_closure' and z['upstream_depth']==3
def test_core_behavior():
 m=load();x=m.KohlerValveKitNegotiation();r=x.offer(m.PROVISIONAL);r=x.apply_authority(r,m.AUTHORITY);r=x.counter(r,m.CANONICAL_CHOICE);v=x.finalize(r);a=x.audit();assert v=={'status':'agreement','terms':m.CANONICAL_CHOICE} and a['chronological'] and a['provisional_excluded']
def test_event_behavior():
 m=load();z=json.loads((OUT/'negotiation_closure.json').read_text());assert m.EVENT_SCHEMA=='current_genuine_part_delivery_counter' and m.AUTHORITY=={'current_counter': {'unit_price': 10.5, 'part_number': '1266657', 'genuine_kohler': True, 'delivery_days': 2, 'warranty_months': 12}, 'supersedes': {'unit_price': 9.0, 'part_authenticity': 'unverified'}} and z['authority_applied']
def test_edge_behavior():
 m=load();x=m.KohlerValveKitNegotiation();r=x.offer(m.PROVISIONAL)
 try:x.apply_authority(r-1,m.AUTHORITY)
 except RuntimeError:pass
 else:raise AssertionError('stale authority accepted')
 try:x.apply_authority(r,{'unauthorized':True})
 except ValueError:pass
 else:raise AssertionError('unauthorized authority accepted')
def test_event_closure_and_preservation():
 r=json.loads((OUT/'event_receipt.json').read_text());z=json.loads((OUT/'negotiation_closure.json').read_text());assert r['event_theme']=='late_or_out_of_order_superseded_result' and z['preserved_workflows']==['kohler_1266657_identity', 'buyer_timely_delivery_priority', 'seller_premium_price_goal']
def test_final_terms_and_tool_sequence():
 z=json.loads((OUT/'negotiation_closure.json').read_text());assert z['selected_terms']=={'unit_price': 10.5, 'part_number': '1266657', 'genuine_kohler': True, 'delivery_days': 2, 'warranty_months': 12} and z['tool_sequence']==['offer','authority','counter','finalize']
