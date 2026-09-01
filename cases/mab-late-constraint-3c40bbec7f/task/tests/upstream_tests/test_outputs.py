from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); AUTHORITY={'contract':'come_robot_recovery_safety_scope_v2','benchmark_dimensions':['task_specific_method','data_protocol','metrics','ablations'],'version':2}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('research_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_research_exact_five_question_schema_and_artifacts():
 m=load_solution(); p=m.ResearchProposal(); p.apply_authority(AUTHORITY); q=p.build_5q(); assert m.DOMAIN=='closed_loop_open_world_robot' and list(q)==[f'question_{i}' for i in range(1,6)] and q['question_1'].count('?')==1 and all(q.values()); assert all(f'Question {i}' in p.render() for i in range(1,6)); r,c=docs(); assert c['artifact_type']=='come_robot_safety_research_closure' and c['upstream_depth']==4 and c['event_receipt_sha256']==r['receipt_sha256']
def test_research_task_specific_method_data_metrics_and_ablations():
 m=load_solution(); p=m.ResearchProposal(); p.apply_authority(AUTHORITY); text=' '.join(p.build_5q().values()).lower(); assert all(k in text for k in ['scene-graph', 'grasp', 'unsafe-action', 'intervention', 'recovery rate', 'ablat']); assert 'ablat' in text and any(x in text for x in ['dataset','benchmark','video','sequence','image'])
def test_research_source_premises_and_structure_are_preserved():
 m=load_solution(); p=m.ResearchProposal(); p.apply_authority(AUTHORITY); q=p.build_5q(); joined=' '.join(q.values()).lower(); assert len(q)==5 and all(term in (' '.join(p.premises)+' '+joined).lower() for term in ['active perception', 'action primitives', 'closed-loop replanning'])
def test_research_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='come_robot_recovery_safety_scope_v2' and r['authority']['contract']==m.EVENT_SCHEMA and r['authority']['version']==2; assert c['preserved_workflows']==['five_question_structure', 'active_perception', 'action_primitive_library', 'closed_loop_replanning'] and c['source_semantics_reverified'] is True
