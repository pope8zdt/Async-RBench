import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def load():
    spec=importlib.util.spec_from_file_location('solution',OUT/'solution.py'); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
def test_native_binding_and_schema():
    native=json.loads(FIX.read_text()); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert native['case_id']=='mab-late-constraint-99180ff520' and native['source_task_id']=='bargaining:023'; assert native['official_evaluator']=='marble.evaluator.evaluator.Evaluator.evaluate_code_quality'; assert closure['artifact_type']=='hasbro_ps4_fulfillment_closure' and closure['upstream_depth']==3
def test_core_behavior():
    module=load(); negotiation=module.HasbroFamilyPackNegotiation(); rev=negotiation.offer(module.PROVISIONAL); rev=negotiation.apply_authority(rev,module.AUTHORITY); rev=negotiation.counter(rev,module.CANONICAL_CHOICE); final=negotiation.finalize(rev); audit=negotiation.audit(); assert final=={'status':'agreement','terms':module.CANONICAL_CHOICE}; assert audit['chronological'] and audit['provisional_excluded']
def test_event_behavior():
    module=load(); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert module.EVENT_SCHEMA=='verified_delivery_quality_counter' and module.AUTHORITY=={'seller_counter': {'unit_price': 14.25, 'condition': 'new', 'delivery_days': 3}, 'supersedes': {'unit_price': 12.0, 'delivery': 'unverified'}} and closure['authority_applied']
def test_edge_behavior():
    module=load(); negotiation=module.HasbroFamilyPackNegotiation(); rev=negotiation.offer(module.PROVISIONAL)
    try: negotiation.apply_authority(rev-1,module.AUTHORITY)
    except RuntimeError: pass
    else: raise AssertionError('stale authority accepted')
    try: negotiation.apply_authority(rev,{'unauthorized':True})
    except ValueError: pass
    else: raise AssertionError('unauthorized authority accepted')
def test_event_closure_and_preservation():
    receipt=json.loads((OUT/'event_receipt.json').read_text()); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert receipt['event_theme']=='late_or_out_of_order_superseded_result'; assert closure['preserved_workflows']==['ps4_compatibility', 'original_price_reference', 'buyer_quality_priority']
def test_final_terms_and_tool_sequence():
    closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert closure['selected_terms']=={'unit_price': 14.25, 'condition': 'new', 'delivery_days': 3, 'quality_rating': 4.5}; assert closure['tool_sequence']==['offer','authority','counter','finalize']
