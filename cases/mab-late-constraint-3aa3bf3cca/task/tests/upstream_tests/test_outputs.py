import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def load():
    spec=importlib.util.spec_from_file_location('solution',OUT/'solution.py'); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
def test_native_binding_and_schema():
    native=json.loads(FIX.read_text()); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert native['case_id']=='mab-late-constraint-3aa3bf3cca' and native['source_task_id']=='bargaining:030'; assert native['official_evaluator']=='marble.evaluator.evaluator.Evaluator.evaluate_code_quality'; assert closure['artifact_type']=='jewelry_organizer_scope_closure' and closure['upstream_depth']==4
def test_core_behavior():
    module=load(); negotiation=module.JewelryOrganizerNegotiation(); rev=negotiation.offer(module.PROVISIONAL); rev=negotiation.apply_authority(rev,module.AUTHORITY); rev=negotiation.counter(rev,module.CANONICAL_CHOICE); final=negotiation.finalize(rev); audit=negotiation.audit(); assert final=={'status':'agreement','terms':module.CANONICAL_CHOICE}; assert audit['chronological'] and audit['provisional_excluded']
def test_event_behavior():
    module=load(); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert module.EVENT_SCHEMA=='product_quality_scope_clarified' and module.AUTHORITY=={'power_requirement': 'none', 'material': 'velvet_ring_holder', 'unit_price': 17.49, 'minimum_batch': 60} and closure['authority_applied']
def test_edge_behavior():
    module=load(); negotiation=module.JewelryOrganizerNegotiation(); rev=negotiation.offer(module.PROVISIONAL)
    try: negotiation.apply_authority(rev-1,module.AUTHORITY)
    except RuntimeError: pass
    else: raise AssertionError('stale authority accepted')
    try: negotiation.apply_authority(rev,{'unauthorized':True})
    except ValueError: pass
    else: raise AssertionError('unauthorized authority accepted')
def test_event_closure_and_preservation():
    receipt=json.loads((OUT/'event_receipt.json').read_text()); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert receipt['event_theme']=='task_scope_or_dependency_change'; assert closure['preserved_workflows']==['organizer_product_identity', 'buyer_price_quality_priority', 'seller_production_demand_goal']
def test_final_terms_and_tool_sequence():
    closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert closure['selected_terms']=={'power_requirement': 'none', 'material': 'velvet_ring_holder', 'unit_price': 17.49, 'minimum_batch': 60}; assert closure['tool_sequence']==['offer','authority','counter','finalize']
