from __future__ import annotations
import importlib.util, json, pathlib
OUT=pathlib.Path('/app/output_data')

def load_solution():
    path=OUT/'solution.py'; assert path.is_file()
    spec=importlib.util.spec_from_file_location('submitted_solution',path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def event_docs():
    return json.loads((OUT/'event_receipt.json').read_text()), json.loads((OUT/'coding_closure.json').read_text())

def assert_closure(kind):
    receipt,closure=event_docs(); assert closure['case_id']=='mab-dependency-unblock-031ed6f5bc'; assert closure['source_task_id']=='coding:087'; assert closure['artifact_type']==kind; assert closure['source_semantics_reverified'] is True; assert closure['event_receipt_sha256']==receipt['receipt_sha256']

def test_dataflow_output_schema_and_artifacts():
    m=load_solution(); assert m.DOMAIN=='data_flow_coordinator'; assert hasattr(m,'DataFlowCoordinator'); assert_closure('validated_data_pipeline_closure')

def test_dataflow_validation_partition_and_stage_order():
    m=load_solution(); p=m.DataFlowCoordinator(); p.ingest('csv',[{'id':'a','amount':'2','name':'one'},{'id':'','amount':'x','name':'bad'}]); split=p.validate(); assert len(split['accepted'])==1 and split['rejected'][0]['errors']==['missing_id','invalid_amount']; assert p.transform({'uppercase_name':True})[0]['name']=='ONE'

def test_dataflow_invalid_rows_never_reach_export_and_replay_is_idempotent():
    m=load_solution(); p=m.DataFlowCoordinator(); p.ingest('database',[{'id':'a','amount':2},{'id':None,'amount':3}]); first=p.consume_validation_completion('validation-batch-87',{},'database'); again=p.consume_validation_completion('validation-batch-87',{},'database'); assert first['artifact']['rows']==[{'id':'a','amount':2,'_source':'database'}]; assert again=={'duplicate':True,'exports':1}

def test_dataflow_event_receipt_and_post_event_closure():
    receipt,closure=event_docs(); assert receipt['authority']['delivery_count']==2; assert receipt['authority']['idempotency_key']=='validation-batch-87'; assert closure['event_receipt_sha256']==receipt['receipt_sha256']
