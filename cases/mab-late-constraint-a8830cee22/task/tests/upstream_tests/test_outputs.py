import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def load():
    spec=importlib.util.spec_from_file_location('solution',OUT/'solution.py'); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
def test_native_binding_and_schema():
    native=json.loads(FIX.read_text()); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert native['case_id']=='mab-late-constraint-a8830cee22' and native['source_task_id']=='bargaining:025'; assert native['official_evaluator']=='marble.evaluator.evaluator.Evaluator.evaluate_code_quality'; assert closure['artifact_type']=='rubbermaid_service_contract_closure' and closure['upstream_depth']==4
def test_core_behavior():
    module=load(); negotiation=module.RubbermaidServiceNegotiation(); rev=negotiation.offer(module.PROVISIONAL); rev=negotiation.apply_authority(rev,module.AUTHORITY); rev=negotiation.counter(rev,module.CANONICAL_CHOICE); final=negotiation.finalize(rev); audit=negotiation.audit(); assert final=={'status':'agreement','terms':module.CANONICAL_CHOICE}; assert audit['chronological'] and audit['provisional_excluded']
def test_event_behavior():
    module=load(); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert module.EVENT_SCHEMA=='after_sales_contract_confirmed' and module.AUTHORITY=={'unit_price': 11.5, 'warranty_months': 18, 'support_response_days': 2, 'contract_months': 24} and closure['authority_applied']
def test_edge_behavior():
    module=load(); negotiation=module.RubbermaidServiceNegotiation(); rev=negotiation.offer(module.PROVISIONAL)
    try: negotiation.apply_authority(rev-1,module.AUTHORITY)
    except RuntimeError: pass
    else: raise AssertionError('stale authority accepted')
    try: negotiation.apply_authority(rev,{'unauthorized':True})
    except ValueError: pass
    else: raise AssertionError('unauthorized authority accepted')
def test_event_closure_and_preservation():
    receipt=json.loads((OUT/'event_receipt.json').read_text()); closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert receipt['event_theme']=='delayed_authoritative_result'; assert closure['preserved_workflows']==['wastebasket_product_scope', 'buyer_after_sales_priority', 'seller_long_term_contract_goal']
def test_final_terms_and_tool_sequence():
    closure=json.loads((OUT/'negotiation_closure.json').read_text()); assert closure['selected_terms']=={'unit_price': 11.5, 'warranty_months': 18, 'support_response_days': 2, 'contract_months': 24}; assert closure['tool_sequence']==['offer','authority','counter','finalize']
