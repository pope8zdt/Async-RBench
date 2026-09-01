from __future__ import annotations
import importlib.util, json, pathlib
OUT=pathlib.Path('/app/output_data')

def load_solution():
    path=OUT/'solution.py'; assert path.is_file()
    spec=importlib.util.spec_from_file_location('submitted_solution',path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def event_docs():
    return json.loads((OUT/'event_receipt.json').read_text()), json.loads((OUT/'coding_closure.json').read_text())

def assert_closure(kind):
    receipt,closure=event_docs(); assert closure['case_id']=='mab-dependency-unblock-09f3ab60d7'; assert closure['source_task_id']=='coding:014'; assert closure['artifact_type']==kind; assert closure['source_semantics_reverified'] is True; assert closure['event_receipt_sha256']==receipt['receipt_sha256']

def test_macao_output_schema_and_artifacts():
    m=load_solution(); assert m.DOMAIN=='macao'; assert hasattr(m,'MACAO'); assert_closure('macao_integrated_analysis_closure')

def test_macao_coverage_excludes_nonexecutable_and_builds_heatmap():
    m=load_solution(); app=m.MACAO(); source='# heading\nx=1\n\nif x:\n    x+=1'; c=app.coverage(source,{2,4}); assert c['percentage']==66.67; assert set(c['statuses'])=={2,4,5}; assert c['heatmap'][5]==0.0

def test_macao_recovery_integrates_coverage_complexity_and_size():
    m=load_solution(); app=m.MACAO(); source='x=1\nif x:\n    x+=1'; recovered=app.recover_coverage('implicit_no_result',source,{1,2,3}); report=app.integrate(recovered['result'],app.complexity(source),app.size({'a.py':source})); assert recovered['recovery']=='redelegated'; assert report['coverage']['percentage']==100.0; assert report['complexity']['cyclomatic']==2

def test_macao_event_receipt_and_post_event_closure():
    receipt,closure=event_docs(); assert receipt['authority']['failure']=='implicit_no_result'; assert receipt['authority']['recovery']=='redelegated'; assert closure['preserved_workflows']==['complexity_metrics','size_estimate','collaboration_permissions']
