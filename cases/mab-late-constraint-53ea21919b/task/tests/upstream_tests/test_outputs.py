import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def load():
    spec=importlib.util.spec_from_file_location('solution',OUT/'solution.py'); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
def test_native_binding_and_schema():
    native=json.loads(FIX.read_text()); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert native['case_id']=='mab-late-constraint-53ea21919b' and native['source_task_id']=='bargaining:028'; assert native['official_evaluator']=='marble.evaluator.evaluator.Evaluator.evaluate_code_quality'; assert closure['artifact_type']=='youth_shirt_production_closure' and closure['upstream_depth']==4
def test_core_behavior():
    module=load(); negotiation=module.YouthShirtProductionNegotiation(); rev=negotiation.offer(module.PROVISIONAL); rev=negotiation.apply_authority(rev,module.AUTHORITY); rev=negotiation.counter(rev,module.CANONICAL_CHOICE); final=negotiation.finalize(rev); audit=negotiation.audit(); assert final=={'status':'agreement','terms':module.CANONICAL_CHOICE}; assert audit['chronological'] and audit['provisional_excluded']
def test_event_behavior():
    module=load(); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert module.EVENT_SCHEMA=='size_run_capacity_constraint_added' and module.AUTHORITY=={'minimum_batch': 120, 'unit_price': 16.5, 'size_run': 'assorted_youth', 'defect_replacement_days': 30} and closure['authority_applied']
def test_edge_behavior():
    module=load(); negotiation=module.YouthShirtProductionNegotiation(); rev=negotiation.offer(module.PROVISIONAL)
    try: negotiation.apply_authority(rev-1,module.AUTHORITY)
    except RuntimeError: pass
    else: raise AssertionError('stale authority accepted')
    try: negotiation.apply_authority(rev,{'unauthorized':True})
    except ValueError: pass
    else: raise AssertionError('unauthorized authority accepted')
def test_event_closure_and_preservation():
    receipt=json.loads((OUT/'event_receipt.json').read_text()); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert receipt['event_theme']=='task_scope_or_dependency_change'; assert closure['preserved_workflows']==['shirt_product_identity', 'buyer_price_quality_priority', 'seller_production_demand_goal']
def test_final_terms_and_tool_sequence():
    closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert closure['selected_terms']=={'minimum_batch': 120, 'unit_price': 16.5, 'size_run': 'assorted_youth', 'defect_replacement_days': 30}; assert closure['tool_sequence']==['offer','authority','counter','finalize']
