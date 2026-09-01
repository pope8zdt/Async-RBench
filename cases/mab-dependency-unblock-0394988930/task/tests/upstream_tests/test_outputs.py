from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); AUTH={'divergences':['reverse_kl','forward_kl','jensen_shannon','alpha_divergence'],'assumptions':['absolute_continuity','convex_generator','finite_preference_log_ratio'],'consistency_case':'reverse_kl_recovers_diffusion_dpo'}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('proposal_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_fdivergence_exact_five_question_schema_and_artifacts():
 m=load_solution(); p=m.DivergenceAlignmentProposal(); p.apply_derivation(AUTH); q=p.build_5q(); assert list(q)==[f'question_{i}' for i in range(1,6)] and q['question_1'].count('?')==1 and all(q.values()); assert all(f'Question {i}' in p.render() for i in range(1,6)); r,c=docs(); assert c['artifact_type']=='five_question_f_divergence_proposal_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_fdivergence_authority_method_datasets_metrics_and_consistency_case():
 m=load_solution(); p=m.DivergenceAlignmentProposal(); p.apply_derivation(AUTH); q=p.build_5q(); method=q['question_5'].lower(); assert all(x in method for x in ['reverse kl','forward kl','jensen-shannon','alpha-divergence','absolute continuity','convex generator','diffusion-dpo','pick-a-pic','hps','pickscore','imagereward','clip','lpips','ablate']); assert 'naive' in q['question_3'].lower() and 'underexplores' in q['question_4'].lower()
def test_fdivergence_source_motivation_and_structure_are_preserved():
 m=load_solution(); p=m.DivergenceAlignmentProposal(); p.apply_derivation(AUTH); q=p.build_5q(); joined=' '.join(q.values()).lower(); assert len(p.premises)==4 and 'human preferences' in joined and 'reward model' in joined and 'diversity' in joined and len(q)==5
def test_fdivergence_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='f_divergence_alignment_derivation_v3' and set(r['authority']['divergences'])=={'reverse_kl','forward_kl','jensen_shannon','alpha_divergence'} and r['authority']['consistency_case']=='reverse_kl_recovers_diffusion_dpo'; assert c['upstream_depth']==4 and c['preserved_workflows']==['five_question_structure','human_preference_motivation','diversity_collapse_gap','dataset_and_metric_plan']
