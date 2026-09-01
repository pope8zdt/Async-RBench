import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data');FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def load():
 s=importlib.util.spec_from_file_location('solution',OUT/'solution.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def test_native_binding_and_schema():
 n=json.loads(FIX.read_text());z=json.loads((OUT/'negotiation_closure.json').read_text());assert n['case_id']=='mab-late-constraint-637224fe05' and n['source_task_id']=='bargaining:043' and n['official_evaluator']=='marble.evaluator.evaluator.Evaluator.evaluate_code_quality';assert z['artifact_type']=='wooden_bead_capacity_closure' and z['upstream_depth']==4
def test_core_behavior():
 m=load();x=m.WoodenBeadNegotiation();r=x.offer(m.PROVISIONAL);r=x.apply_authority(r,m.AUTHORITY);r=x.counter(r,m.CANONICAL_CHOICE);v=x.finalize(r);a=x.audit();assert v=={'status':'agreement','terms':m.CANONICAL_CHOICE} and a['chronological'] and a['provisional_excluded']
def test_event_behavior():
 m=load();z=json.loads((OUT/'negotiation_closure.json').read_text());assert m.EVENT_SCHEMA=='bead_capacity_scope_added' and m.AUTHORITY=={'pack_count': 100, 'diameter_inches': 0.75, 'finish': 'unfinished_natural_wood', 'minimum_packs': 80, 'unit_price': 7.35, 'lead_time_days': 7} and z['authority_applied']
def test_edge_behavior():
 m=load();x=m.WoodenBeadNegotiation();r=x.offer(m.PROVISIONAL)
 try:x.apply_authority(r-1,m.AUTHORITY)
 except RuntimeError:pass
 else:raise AssertionError('stale authority accepted')
 try:x.apply_authority(r,{'unauthorized':True})
 except ValueError:pass
 else:raise AssertionError('unauthorized authority accepted')
def test_event_closure_and_preservation():
 r=json.loads((OUT/'event_receipt.json').read_text());z=json.loads((OUT/'negotiation_closure.json').read_text());assert r['event_theme']=='task_scope_or_dependency_change' and z['preserved_workflows']==['wooden_bead_product_identity', 'buyer_scalability_priority', 'seller_production_demand_goal']
def test_final_terms_and_tool_sequence():
 z=json.loads((OUT/'negotiation_closure.json').read_text());assert z['selected_terms']=={'pack_count': 100, 'diameter_inches': 0.75, 'finish': 'unfinished_natural_wood', 'minimum_packs': 80, 'unit_price': 7.35, 'lead_time_days': 7} and z['tool_sequence']==['offer','authority','counter','finalize']
