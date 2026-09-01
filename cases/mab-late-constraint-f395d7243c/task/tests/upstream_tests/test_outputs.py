import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data');FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def load():
 p=OUT/'solution.py';s=importlib.util.spec_from_file_location('solution',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def test_native_binding_and_schema():
 n=json.loads(FIX.read_text());c=json.loads((OUT/'negotiation_closure.json').read_text());assert n['case_id']=='mab-late-constraint-f395d7243c' and n['source_task_id']=='bargaining:012';assert n['official_evaluator']=='marble.evaluator.evaluator.Evaluator.evaluate_code_quality' and c['artifact_type']=='seal_protectant_logistics_closure' and c['upstream_depth']==3
def test_core_behavior():
 m=load();a=m.SealProtectantNegotiation();r=a.buyer_offer({'plan':m.STALE_PLAN});r=a.apply_authority(r,m.AUTHORITY);r=a.counter(r,m.CANONICAL_CHOICE);f=a.finalize(r);assert f=={'status':'agreement','terms':m.CANONICAL_CHOICE} and a.audit()['chronological'] and a.audit()['stale_plan_excluded']
def test_event_behavior():
 m=load();assert m.EVENT_SCHEMA=='logistics_tiers_countered' and m.AUTHORITY=={'one_time': {'quantity': 240, 'unit_price': 8.4}, 'annual': {'quantity': 960, 'unit_price': 8.1, 'cadence': 'quarterly'}}
def test_edge_behavior():
 m=load();a=m.SealProtectantNegotiation();r=a.buyer_offer({'plan':m.STALE_PLAN})
 try:a.apply_authority(r-1,m.AUTHORITY)
 except RuntimeError:pass
 else:raise AssertionError('stale authority accepted')
def test_event_closure_and_preservation():
 r=json.loads((OUT/'event_receipt.json').read_text());c=json.loads((OUT/'negotiation_closure.json').read_text());assert r['event_theme']=='late_or_out_of_order_superseded_result' and c['preserved_workflows']==['quality_requirement', 'offer_history', 'buyer_cost_goal'] and c['authority_applied']
