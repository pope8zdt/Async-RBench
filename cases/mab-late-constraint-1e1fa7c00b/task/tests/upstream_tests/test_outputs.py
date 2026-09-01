import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def load():
    spec=importlib.util.spec_from_file_location('solution',OUT/'solution.py'); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
def test_native_binding_and_schema():
    native=json.loads(FIX.read_text()); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert native['case_id']=='mab-late-constraint-1e1fa7c00b' and native['source_task_id']=='bargaining:029'; assert native['official_evaluator']=='marble.evaluator.evaluator.Evaluator.evaluate_code_quality'; assert closure['artifact_type']=='turtle_doorstop_freight_closure' and closure['upstream_depth']==3
def test_core_behavior():
    module=load(); negotiation=module.TurtleDoorStopNegotiation(); rev=negotiation.offer(module.PROVISIONAL); rev=negotiation.apply_authority(rev,module.AUTHORITY); rev=negotiation.counter(rev,module.CANONICAL_CHOICE); final=negotiation.finalize(rev); audit=negotiation.audit(); assert final=={'status':'agreement','terms':module.CANONICAL_CHOICE}; assert audit['chronological'] and audit['provisional_excluded']
def test_event_behavior():
    module=load(); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert module.EVENT_SCHEMA=='freight_finish_counter_supersedes_quote' and module.AUTHORITY=={'current_counter': {'unit_price': 25.49, 'finish': 'heavy_duty_rustic', 'delivery_days': 7}, 'supersedes': {'unit_price': 22.0, 'freight': 'unverified'}} and closure['authority_applied']
def test_edge_behavior():
    module=load(); negotiation=module.TurtleDoorStopNegotiation(); rev=negotiation.offer(module.PROVISIONAL)
    try: negotiation.apply_authority(rev-1,module.AUTHORITY)
    except RuntimeError: pass
    else: raise AssertionError('stale authority accepted')
    try: negotiation.apply_authority(rev,{'unauthorized':True})
    except ValueError: pass
    else: raise AssertionError('unauthorized authority accepted')
def test_event_closure_and_preservation():
    receipt=json.loads((OUT/'event_receipt.json').read_text()); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert receipt['event_theme']=='late_or_out_of_order_superseded_result'; assert closure['preserved_workflows']==['cast_iron_product_identity', 'buyer_premium_feature_priority', 'seller_margin_goal']
def test_final_terms_and_tool_sequence():
    closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert closure['selected_terms']=={'unit_price': 25.49, 'finish': 'heavy_duty_rustic', 'delivery_days': 7}; assert closure['tool_sequence']==['offer','authority','counter','finalize']
