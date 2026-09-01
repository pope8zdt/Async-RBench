from __future__ import annotations
import importlib.util, json, pathlib
OUT=pathlib.Path('/app/output_data')

def load_solution():
    path=OUT/'solution.py'; assert path.is_file()
    spec=importlib.util.spec_from_file_location('submitted_solution',path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def event_docs():
    return json.loads((OUT/'event_receipt.json').read_text()), json.loads((OUT/'coding_closure.json').read_text())

def assert_closure(kind):
    receipt,closure=event_docs(); assert closure['case_id']=='mab-dependency-unblock-0daa930906'; assert closure['source_task_id']=='coding:075'; assert closure['artifact_type']==kind; assert closure['source_semantics_reverified'] is True; assert closure['event_receipt_sha256']==receipt['receipt_sha256']

def test_artcollab_output_schema_and_artifacts():
    m=load_solution(); assert m.DOMAIN=='art_collab'; assert hasattr(m,'ArtCollab'); assert_closure('artcollab_synchronized_canvas_closure')

def test_artcollab_revision_ack_duplicate_and_conflict_resolution():
    m=load_solution(); app=m.ArtCollab(); app.register('ana','pw'); assert app.login('ana','pw'); app.create_project('p','ana'); op={'op_id':'1','base_revision':0,'lamport':1,'actor':'ana','payload':{'point':[1,2],'color':'red'}}; first=app.apply_operation('p',op); replay=app.apply_operation('p',op); assert first['revision']==1 and replay['status']=='duplicate' and replay['revision']==1

def test_artcollab_layers_history_and_two_client_order_are_preserved():
    m=load_solution(); app=m.ArtCollab(); app.register('ana','pw'); app.login('ana','pw'); app.create_project('p','ana'); app.apply_operation('p',{'op_id':'a','base_revision':0,'lamport':2,'actor':'ana','payload':{'layer':'ink','point':[0,0],'color':'blue'}}); ack=app.apply_operation('p',{'op_id':'b','base_revision':0,'lamport':3,'actor':'bo','payload':{'layer':'ink','point':[0,0],'color':'green'}}); snap=app.snapshot('p'); assert ack['status']=='conflict_resolved'; assert snap['layers']['ink'][(0,0)]=='green'; assert snap['history_count']==2

def test_artcollab_event_receipt_and_post_event_closure():
    receipt,closure=event_docs(); assert receipt['authority']['duplicate_policy']=='idempotent'; assert receipt['authority']['conflict_policy']=='lamport_then_actor'; assert closure['preserved_workflows']==['layers','local_tools','project_history','authenticated_users']
