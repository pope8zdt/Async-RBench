import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data');FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def load():
 p=OUT/'solution.py';s=importlib.util.spec_from_file_location('solution',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def test_native_binding_and_schema():
 n=json.loads(FIX.read_text());c=json.loads((OUT/'coding_closure.json').read_text());assert n['case_id']=='mab-late-constraint-311fc423ac' and n['source_task_id']=='coding:049';assert n['official_evaluator']=='marble.evaluator.evaluator.Evaluator.evaluate_code_quality' and c['artifact_type']=='financial_goal_accounting_closure' and c['upstream_depth']==4
def test_core_behavior():
 m=load();a=m.FinancialCollaborator();a.register('ann','secret1');a.register('bob','secret2');ta=a.login('ann','secret1');tb=a.login('bob','secret2');a.create_group(ta,'g');a.join_group(tb,'g');a.set_goal(ta,'g',100,'2030-01-01',[50,100]);assert a.contribute(ta,'g',60,'op1');assert not a.contribute(ta,'g',60,'op1');a.contribute(tb,'g',20,'op2');a.refund(ta,'g',10,'op3');d=a.dashboard(tb,'g');assert d['total']==70 and d['remaining']==30 and d['milestones_reached']==[50.0]
def test_event_behavior():
 m=load();assert m.EVENT_SCHEMA=='ledger_invariants_v2'
def test_edge_behavior():
 m=load();a=m.FinancialCollaborator();a.register('u','secret1');t=a.login('u','secret1');a.create_group(t,'g');a.set_goal(t,'g',10,'d')
 try:a.refund(t,'g',1,'r')
 except ValueError:pass
 else:raise AssertionError('over-refund accepted')
def test_event_closure_and_preservation():
 r=json.loads((OUT/'event_receipt.json').read_text());c=json.loads((OUT/'coding_closure.json').read_text());assert r['event_theme']=='delayed_authoritative_result' and c['preserved_workflows']==['accounts', 'group_memberships', 'chat_history'] and c['authority_applied']
