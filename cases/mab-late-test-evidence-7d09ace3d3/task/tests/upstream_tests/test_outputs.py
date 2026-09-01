from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); EVIDENCE={'evidence_id':'lang-edge-2026-10','suite':'language_collaboration_edges','cases':['multi_user','unauthorized_private','simultaneous_submit','no_peer_review']}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('language_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_language_output_schema_exercise_types_and_closure():
 m=load_solution(); x=m.LanguageCollaborator(); [x.add_user(u) for u in ['a','b','c']]; x.apply_edge_evidence(EVIDENCE); x.create_exercise('g','a','grammar','Choose','went'); x.create_exercise('v','a','vocabulary','Define','rapid'); x.create_exercise('w','a','writing','Write'); r,c=docs(); assert set(x.exercises)=={'g','v','w'} and c['artifact_type']=='language_collaboration_evidence_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_language_feedback_sharing_authorization_and_peer_review_behavior():
 m=load_solution(); x=m.LanguageCollaborator(); [x.add_user(u) for u in ['a','b','c']]; x.apply_edge_evidence(EVIDENCE); x.create_exercise('g','a','grammar','Choose','went'); assert x.submit('s','b','g','went')['feedback']=={'correct':True}; assert x.peer_review('c','s',4,'clear')['rating']==4; x.create_exercise('p','a','writing','Private',shared=False)
 try:x.submit('bad','b','p','text')
 except PermissionError:pass
 else:raise AssertionError('private exercise leaked')
def test_language_writing_feedback_and_learning_history_are_preserved():
 m=load_solution(); x=m.LanguageCollaborator(); [x.add_user(u) for u in ['a','b','c']]; x.apply_edge_evidence(EVIDENCE); x.create_exercise('w','a','writing','Write'); row=x.submit('s','b','w','lower case'); x.peer_review('c','s',5,'helpful'); assert row['feedback']['suggestions']==['capitalization','terminal punctuation'] and len(x.submissions)==1 and x.reviews[0]['comment']=='helpful'
def test_language_duplicate_edge_evidence_is_idempotent_and_closes_once():
 m=load_solution(); x=m.LanguageCollaborator(); assert x.apply_edge_evidence(EVIDENCE) is True and x.apply_edge_evidence(dict(EVIDENCE)) is False and len(x.seen_evidence)==1; r,c=docs(); assert r['authority']['evidence_id']=='lang-edge-2026-10' and c['source_semantics_reverified'] is True
