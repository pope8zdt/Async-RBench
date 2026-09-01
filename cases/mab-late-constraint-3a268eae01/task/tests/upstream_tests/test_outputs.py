import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data');FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def load():
 p=OUT/'solution.py';s=importlib.util.spec_from_file_location('solution',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def test_native_binding_and_schema():
 n=json.loads(FIX.read_text());c=json.loads((OUT/'coding_closure.json').read_text());assert n['case_id']=='mab-late-constraint-3a268eae01' and n['source_task_id']=='coding:033';assert n['official_evaluator']=='marble.evaluator.evaluator.Evaluator.evaluate_code_quality' and c['artifact_type']=='photo_collaboration_revision_closure' and c['upstream_depth']==4
def test_core_behavior():
 m=load();a=m.PhotoCollabEditor();a.register('ann');a.register('bob');a.create_session('ann','s','photo');a.join('bob','s');x=a.apply('ann','s','op1',0,'filter',{'name':'warm'});assert x=={'status':'applied','revision':1};assert a.apply('bob','s','op1',1,'color',{})['status']=='duplicate';assert a.apply('bob','s','op2',0,'color',{})['status']=='conflict';assert a.apply('bob','s','op2',1,'background_remove',{})['status']=='applied';assert len(a.events)==2
def test_event_behavior():
 m=load();assert m.EVENT_SCHEMA=='socket_revision_contract_v2'
def test_edge_behavior():
 m=load();a=m.PhotoCollabEditor();a.register('o');a.create_session('o','s','p')
 try:a.history('x','s')
 except PermissionError:pass
 else:raise AssertionError('private session leaked')
def test_event_closure_and_preservation():
 r=json.loads((OUT/'event_receipt.json').read_text());c=json.loads((OUT/'coding_closure.json').read_text());assert r['event_theme']=='delayed_authoritative_result' and c['preserved_workflows']==['session_acl', 'presence', 'chat_history', 'editing_actions'] and c['authority_applied']
