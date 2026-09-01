from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); AUTHORITY={'contract':'driving_causal_explanation_protocol_v2','benchmark_dimensions':['task_specific_method','data_protocol','metrics','ablations'],'version':2}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('research_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_research_exact_five_question_schema_and_artifacts():
 m=load_solution(); p=m.ResearchProposal(); p.apply_authority(AUTHORITY); q=p.build_5q(); assert m.DOMAIN=='driving_counterfactual_explanations' and list(q)==[f'question_{i}' for i in range(1,6)] and q['question_1'].count('?')==1 and all(q.values()); assert all(f'Question {i}' in p.render() for i in range(1,6)); r,c=docs(); assert c['artifact_type']=='driving_explanation_research_closure' and c['upstream_depth']==4 and c['event_receipt_sha256']==r['receipt_sha256']
def test_research_task_specific_method_data_metrics_and_ablations():
 m=load_solution(); p=m.ResearchProposal(); p.apply_authority(AUTHORITY); text=' '.join(p.build_5q().values()).lower(); assert all(k in text for k in ['traffic light', 'pedestrian', 'lane', 'counterfactual', 'bdd100k', 'nuscenes', 'fidelity', 'stability', 'human', 'ablat'])
def test_research_source_premises_and_structure_are_preserved():
 m=load_solution(); p=m.ResearchProposal(); p.apply_authority(AUTHORITY); q=p.build_5q(); joined=' '.join(q.values()).lower(); assert len(q)==5 and all(term in (' '.join(p.premises)+' '+joined).lower() for term in ['safety-critical', 'saliency', 'human', 'liability'])
def test_research_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='driving_causal_explanation_protocol_v2' and r['authority']['contract']==m.EVENT_SCHEMA and r['authority']['version']==2; assert c['preserved_workflows']==['five_question_structure', 'safety_critical_motivation', 'saliency_limitations', 'human_explanation_goal'] and c['source_semantics_reverified'] is True
