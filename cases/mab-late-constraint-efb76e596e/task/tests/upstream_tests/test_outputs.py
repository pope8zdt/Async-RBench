import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data');FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def load():
 p=OUT/'solution.py';s=importlib.util.spec_from_file_location('solution',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def test_native_binding_and_schema():
 n=json.loads(FIX.read_text());c=json.loads((OUT/'negotiation_closure.json').read_text());assert n['case_id']=='mab-late-constraint-efb76e596e' and n['source_task_id']=='bargaining:013';assert n['official_evaluator']=='marble.evaluator.evaluator.Evaluator.evaluate_code_quality' and c['artifact_type']=='bookcase_delivery_bargaining_closure' and c['upstream_depth']==3
def test_core_behavior():
 m=load();a=m.BookcaseNegotiation();r=a.buyer_offer({'plan':m.STALE_PLAN});r=a.apply_authority(r,m.AUTHORITY);r=a.counter(r,m.CANONICAL_CHOICE);f=a.finalize(r);assert f=={'status':'agreement','terms':m.CANONICAL_CHOICE} and a.audit()['chronological'] and a.audit()['stale_plan_excluded']
def test_event_behavior():
 m=load();assert m.EVENT_SCHEMA=='delivery_margin_tiers_countered' and m.AUTHORITY=={'unit_price': 91.0, 'delivery_business_days': 4, 'written_confirmation': True, 'tier_rejected': {'unit_price': 84.0, 'delivery_business_days': 14}}
def test_edge_behavior():
 m=load();a=m.BookcaseNegotiation();r=a.buyer_offer({'plan':m.STALE_PLAN})
 try:a.apply_authority(r-1,m.AUTHORITY)
 except RuntimeError:pass
 else:raise AssertionError('stale authority accepted')
def test_event_closure_and_preservation():
 r=json.loads((OUT/'event_receipt.json').read_text());c=json.loads((OUT/'negotiation_closure.json').read_text());assert r['event_theme']=='late_or_out_of_order_superseded_result' and c['preserved_workflows']==['buyer_urgency', 'offer_history', 'written_confirmation_request'] and c['authority_applied']
