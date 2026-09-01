import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data');FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def load():
 p=OUT/'solution.py';s=importlib.util.spec_from_file_location('solution',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def test_native_binding_and_schema():
 n=json.loads(FIX.read_text());c=json.loads((OUT/'negotiation_closure.json').read_text());assert n['case_id']=='mab-late-constraint-fc88525ce2' and n['source_task_id']=='bargaining:022';assert n['official_evaluator']=='marble.evaluator.evaluator.Evaluator.evaluate_code_quality' and c['artifact_type']=='idol_doll_supply_scope_closure' and c['upstream_depth']==4
def test_core_behavior():
 m=load();a=m.IdolDollNegotiation();r=a.buyer_offer({'plan':m.STALE_PLAN});r=a.apply_authority(r,m.AUTHORITY);r=a.counter(r,m.CANONICAL_CHOICE);f=a.finalize(r);assert f=={'status':'agreement','terms':m.CANONICAL_CHOICE} and a.audit()['chronological'] and a.audit()['stale_plan_excluded']
def test_event_behavior():
 m=load();assert m.EVENT_SCHEMA=='production_scope_constraint_added' and m.AUTHORITY=={'immediate_batch_max': 100, 'unit_price': 14.25, 'replacement_days': 90, 'second_batch_weeks': 6}
def test_edge_behavior():
 m=load();a=m.IdolDollNegotiation();r=a.buyer_offer({'plan':m.STALE_PLAN})
 try:a.apply_authority(r-1,m.AUTHORITY)
 except RuntimeError:pass
 else:raise AssertionError('stale authority accepted')
def test_event_closure_and_preservation():
 r=json.loads((OUT/'event_receipt.json').read_text());c=json.loads((OUT/'negotiation_closure.json').read_text());assert r['event_theme']=='task_scope_or_dependency_change' and c['preserved_workflows']==['warranty_priority', 'offer_history', 'buyer_demand'] and c['authority_applied']
