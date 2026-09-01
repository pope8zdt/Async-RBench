from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ALL_IDS = [
    "mab-late-test-evidence-4c6c77884e",
    "mab-late-constraint-aa71803693",
    "mab-late-constraint-c88a633e8f",
    "mab-dependency-unblock-0394988930",
    "mab-dependency-unblock-107bc4fe3f",
    "mab-late-constraint-9636e9ce85",
]


RUNTIME = {
    "mab-late-test-evidence-4c6c77884e": {
        "source_id": "coding:091",
        "benchmark": "coding",
        "prefix": "mab_code91_familyquest",
        "domain": "family_code_quest",
        "class_name": "FamilyCodeQuest",
        "scenario_class": "result_eventful",
        "theme": "duplicate_or_replayed_completion",
        "event": "challenge_test_evidence_replayed",
        "event_id": "evt.mab_late_test_evidence_4.challenge_test_evidence_replayed",
        "artifact": "family_code_quest_test_closure",
        "meaning": "Task-specific challenge tests are incorporated exactly once even when completion is replayed, while shared sessions, saved progress, hints, and collaboration history remain intact.",
        "authority": {
            "contract": "family_code_quest_tests_v2",
            "evidence_id": "sorting-boundaries-2026-08",
            "challenge": "sort_numbers",
            "cases": [
                {"input": [], "expected": []},
                {"input": [3, 1, 3], "expected": [1, 3, 3]},
                {"input": [-2, 4, 0], "expected": [-2, 0, 4]},
            ],
        },
        "preserved": ["shared_sessions", "saved_progress", "hint_history", "collaboration_history"],
        "extension": "Build FamilyCodeQuest with shared challenge sessions, deterministic challenge execution, progress persistence, and instructional feedback. Three upstream workstreams establish users, collaboration, and challenge state; a fourth evaluator-owned test specialist completion may be replayed. Deduplicate it by evidence identity, apply its empty, duplicate, and negative-number sorting cases exactly once, fix only affected challenge behavior, and preserve collaboration state.",
        "provenance": "FamilyCodeQuest",
        "behavior_flag": "APPLY_UNIQUE_TEST_EVIDENCE = True",
        "preserve_flag": "PRESERVE_COLLABORATION_STATE = True",
        "requirements": [
            "Implement users, family sessions, and real-time collaborative edits.",
            "Implement deterministic beginner-to-advanced challenge execution and feedback.",
            "Persist progress, hints, and resumable challenge state.",
            "Deduplicate and integrate returned task-specific test evidence, then reverify affected challenges.",
        ],
        "before": "Collaboration and challenge execution exist, but boundary-test evidence has not yet been incorporated and may be delivered more than once.",
        "after": "The authoritative sorting boundary suite is registered exactly once and affected challenge behavior is reverified without duplicating side effects.",
        "semantic_labels": {
            "output_schema": "solution.py exposes FamilyCodeQuest and the four-upstream family_code_quest_test_closure.",
            "task_behavior": "Sorting challenges handle empty, duplicate, and negative inputs, and replayed evidence is idempotently consumed once.",
            "preservation": "Preserves shared sessions, collaborative edits, saved progress, and hint history across test-evidence integration.",
            "event_closure": "The test-specialist receipt, evidence identity, registered cases, and final closure are bound without duplicate application.",
        },
        "canonical": r'''DOMAIN='family_code_quest'
EVENT_SCHEMA='family_code_quest_tests_v2'
APPLY_UNIQUE_TEST_EVIDENCE = True
PRESERVE_COLLABORATION_STATE = True

class FamilyCodeQuest:
 def __init__(self):
  self.users={}; self.challenges={}; self.sessions={}; self.saved={}; self.hints=[]; self.history=[]; self.evidence_ids=set(); self.evidence_application_count=0
 def add_user(self,user_id,age_group):
  if user_id in self.users: raise ValueError('duplicate user')
  self.users[user_id]={'age_group':age_group,'completed':[]}; return self.users[user_id]
 def add_challenge(self,challenge_id,difficulty,kind):
  if difficulty not in {'beginner','intermediate','advanced'} or kind not in {'sort_numbers','sum_numbers'}: raise ValueError('invalid challenge')
  self.challenges[challenge_id]={'difficulty':difficulty,'kind':kind,'tests':[]}; return self.challenges[challenge_id]
 def start_session(self,session_id,user_ids,challenge_id):
  if challenge_id not in self.challenges or any(u not in self.users for u in user_ids): raise KeyError('unknown participant or challenge')
  self.sessions[session_id]={'users':list(user_ids),'challenge_id':challenge_id,'shared_code':'','revision':0,'messages':[]}; return self.sessions[session_id]
 def collaborate(self,session_id,user_id,code,message=''):
  s=self.sessions[session_id]
  if user_id not in s['users']: raise PermissionError('not in family session')
  if PRESERVE_COLLABORATION_STATE:
   s['shared_code']=code; s['revision']+=1; s['messages'].append({'user':user_id,'message':message}); self.history.append((session_id,user_id,s['revision']))
  return s['revision']
 def apply_test_evidence(self,evidence_id,challenge_id,cases):
  if APPLY_UNIQUE_TEST_EVIDENCE and evidence_id in self.evidence_ids: return {'status':'duplicate','applied':0}
  if challenge_id not in self.challenges: raise KeyError(challenge_id)
  normalized=[{'input':list(c['input']),'expected':list(c['expected'])} for c in cases]
  self.challenges[challenge_id]['tests']=normalized; self.evidence_ids.add(evidence_id); self.evidence_application_count+=1
  return {'status':'applied','applied':len(normalized)}
 def solve(self,challenge_id,values):
  kind=self.challenges[challenge_id]['kind']
  return sorted(list(values)) if kind=='sort_numbers' else sum(values)
 def run_registered_tests(self,challenge_id):
  rows=self.challenges[challenge_id]['tests']; passed=sum(self.solve(challenge_id,r['input'])==r['expected'] for r in rows)
  return {'passed':passed,'total':len(rows),'all_passed':passed==len(rows)}
 def submit(self,user_id,challenge_id,values):
  result=self.solve(challenge_id,values); report=self.run_registered_tests(challenge_id)
  if report['all_passed'] and challenge_id not in self.users[user_id]['completed']: self.users[user_id]['completed'].append(challenge_id)
  return {'result':result,'test_report':report}
 def get_hint(self,user_id,challenge_id,attempt):
  text='Compare adjacent values and preserve duplicates.' if self.challenges[challenge_id]['kind']=='sort_numbers' else 'Accumulate each value once.'
  if PRESERVE_COLLABORATION_STATE:self.hints.append({'user':user_id,'challenge':challenge_id,'attempt':attempt,'hint':text})
  return text
 def save_progress(self,user_id):
  snapshot={'completed':list(self.users[user_id]['completed']),'sessions':{k:v['revision'] for k,v in self.sessions.items() if user_id in v['users']}}
  if PRESERVE_COLLABORATION_STATE:self.saved[user_id]=snapshot
  return snapshot
 def load_progress(self,user_id): return dict(self.saved.get(user_id,{'completed':[],'sessions':{}}))
''',
        "tests": r'''from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
CASES=[{'input':[],'expected':[]},{'input':[3,1,3],'expected':[1,3,3]},{'input':[-2,4,0],'expected':[-2,0,4]}]
def load_solution():
 p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('familyquest_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_familyquest_output_schema_and_artifacts():
 m=load_solution(); assert m.DOMAIN=='family_code_quest' and hasattr(m,'FamilyCodeQuest'); r,c=docs(); assert c['artifact_type']=='family_code_quest_test_closure' and c['upstream_depth']==4 and c['event_receipt_sha256']==r['receipt_sha256']
def test_familyquest_sort_boundaries_and_duplicate_evidence_are_idempotent():
 m=load_solution(); q=m.FamilyCodeQuest(); q.add_user('parent','adult'); q.add_user('child','child'); q.add_challenge('sort','beginner','sort_numbers'); q.start_session('s',['parent','child'],'sort'); first=q.apply_test_evidence('sorting-boundaries-2026-08','sort',CASES); replay=q.apply_test_evidence('sorting-boundaries-2026-08','sort',CASES)
 assert first=={'status':'applied','applied':3} and replay=={'status':'duplicate','applied':0} and q.evidence_application_count==1; assert q.run_registered_tests('sort')=={'passed':3,'total':3,'all_passed':True}; assert q.submit('child','sort',[-1,2,-1])['result']==[-1,-1,2]
def test_familyquest_collaboration_progress_and_feedback_are_preserved():
 m=load_solution(); q=m.FamilyCodeQuest(); q.add_user('p','adult'); q.add_user('c','child'); q.add_challenge('sort','beginner','sort_numbers'); q.start_session('home',['p','c'],'sort'); q.collaborate('home','c','def solve(xs): return sorted(xs)','ready'); q.apply_test_evidence('e','sort',CASES); q.submit('c','sort',[2,1]); hint=q.get_hint('c','sort',2); saved=q.save_progress('c')
 assert q.sessions['home']['revision']==1 and q.history and 'duplicates' in hint and q.hints; assert saved['completed']==['sort'] and q.load_progress('c')==saved
def test_familyquest_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='family_code_quest_tests_v2'; assert r['authority']['evidence_id']=='sorting-boundaries-2026-08' and len(r['authority']['cases'])==3; assert c['preserved_workflows']==['shared_sessions','saved_progress','hint_history','collaboration_history'] and c['source_semantics_reverified'] is True
''',
    },
    "mab-late-constraint-aa71803693": {
        "source_id": "bargaining:005", "benchmark": "bargaining", "prefix": "mab_bargain05_elephant", "domain": "elephant_baby_shower_bargaining", "class_name": "BabyShowerNegotiation",
        "scenario_class": "result_eventful", "theme": "late_or_out_of_order_superseded_result", "event": "seller_supply_terms_arrived", "event_id": "evt.mab_late_constraint_aa71.seller_supply_terms_arrived", "artifact": "elephant_centerpiece_supply_agreement_closure",
        "meaning": "Late seller supply and long-term-contract terms supersede provisional price-only drafts while the Elephant centerpiece product identity, buyer quality goal, transcript, and rejected offers remain auditable.",
        "authority": {"contract":"elephant_centerpiece_supply_v2","product":"Jungle Baby Shower Theme Centerpiece","rating":4.7,"tiers":[{"name":"single_event","unit_price":27.5,"minimum_quantity":1,"contract_months":0,"shipping_days":6},{"name":"planner_partner","unit_price":25.5,"minimum_quantity":12,"contract_months":12,"shipping_days":4}]},
        "preserved": ["negotiation_transcript","rejected_offers","buyer_quality_priority","seller_long_term_goal"],
        "extension": "Produce an auditable negotiation for the specified 4.7-rated Elephant baby-shower centerpiece. Three upstream workstreams preserve buyer quality and price priorities, seller long-term-contract goals, and tool actions. A later evaluator-owned seller supply matrix supersedes price-only drafts. Apply only the newest matrix, reject stale or structurally invalid offers, keep explicit unit price, quantity, contract duration, shipping, and product terms, and close with the required negotiation-summary sections.",
        "provenance": "Jungle Baby Shower Theme Centerpiece bargaining task", "behavior_flag": "ENFORCE_LATEST_SUPPLY_TERMS = True", "preserve_flag": "PRESERVE_NEGOTIATION_LEDGER = True",
        "requirements": ["Preserve the buyer's price and 4.7-quality objective for the Elephant centerpiece.","Preserve the seller's long-term-contract objective and explicit supply constraints.","Record offers, counters, information, rejection reasons, and agreement progress.","Apply the newest seller supply matrix and close only on complete mutually valid terms."],
        "before": "A price-only centerpiece draft exists before authoritative quantity, contract-duration, and shipping terms arrive.", "after": "The newest seller matrix supersedes the draft and yields an explicit auditable agreement without erasing negotiation history.",
        "semantic_labels": {"output_schema":"The bargaining implementation and elephant_centerpiece_supply_agreement_closure expose the required product and negotiation-summary contract.","task_behavior":"Newest seller tiers govern unit price, minimum quantity, contract duration, and shipping; stale or incomplete offers cannot become agreements.","preservation":"Preserves the transcript, rejection reasons, buyer quality priority, and seller long-term-contract goal.","event_closure":"The late seller matrix supersedes the provisional draft and the final agreement consumes the exact event receipt."},
        "canonical": r'''DOMAIN='elephant_baby_shower_bargaining'
EVENT_SCHEMA='elephant_centerpiece_supply_v2'
ENFORCE_LATEST_SUPPLY_TERMS = True
PRESERVE_NEGOTIATION_LEDGER = True
class BabyShowerNegotiation:
 def __init__(self):
  self.product='Jungle Baby Shower Theme Centerpiece'; self.original_price=29.99; self.rating=4.7; self.buyer_priorities=['price','quality']; self.seller_goal='long_term_contract'; self.transcript=[]; self.rejected=[]; self.authority_sequence=0; self.tiers={}; self.current_offer=None; self.agreement=None
 def _record(self,row):
  if PRESERVE_NEGOTIATION_LEDGER:self.transcript.append(dict(row))
 def buyer_draft(self,unit_price,quantity,sequence):
  offer={'actor':'buyer','product':self.product,'unit_price':float(unit_price),'quantity':int(quantity),'sequence':int(sequence)}; self.current_offer=offer; self._record({'action':'offer_price',**offer}); return offer
 def apply_supply_terms(self,tiers,sequence):
  if ENFORCE_LATEST_SUPPLY_TERMS and sequence<=self.authority_sequence:self.rejected.append({'reason':'stale_authority','sequence':sequence}); return {'status':'stale'}
  self.authority_sequence=int(sequence); self.tiers={t['name']:dict(t) for t in tiers}; self.current_offer=None; self._record({'action':'provide_information','actor':'seller','sequence':sequence,'tiers':sorted(self.tiers)}); return {'status':'authority_applied'}
 def select_tier(self,actor,name,quantity,sequence):
  if ENFORCE_LATEST_SUPPLY_TERMS and sequence<=self.authority_sequence:self.rejected.append({'reason':'stale_offer','sequence':sequence}); return {'status':'stale'}
  tier=dict(self.tiers[name]); qty=int(quantity)
  if qty<tier['minimum_quantity']:self.rejected.append({'reason':'below_minimum_quantity','quantity':qty}); return {'status':'rejected'}
  self.current_offer={'actor':actor,'product':self.product,'quantity':qty,'rating':self.rating,'sequence':int(sequence),**tier}; self._record({'action':'counter_offer',**self.current_offer}); return dict(self.current_offer)
 def finalize(self):
  o=self.current_offer
  required={'product','unit_price','quantity','contract_months','shipping_days','rating'}
  if not o or not required<=set(o) or o['rating']<4.7 or o['unit_price']<=0: raise ValueError('complete quality-bound supply terms required')
  self.agreement={k:o[k] for k in ['product','unit_price','quantity','contract_months','shipping_days','rating']}; self._record({'action':'end_negotiation','agreement':dict(self.agreement)}); return dict(self.agreement)
 def render_summary(self):
  status='Agreement reached' if self.agreement else 'Negotiation active'
  return '\n'.join(['**[Iteration Summary]**',status,'**[Agent Actions and Tools Used]**',f'Actions recorded: {len(self.transcript)}','**[Key Strategies and Observations]**','Buyer quality and seller contract goals were reconciled.','**[Progress Towards Agreement]**',status])
''',
        "tests": r'''from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
TIERS=[{'name':'single_event','unit_price':27.5,'minimum_quantity':1,'contract_months':0,'shipping_days':6},{'name':'planner_partner','unit_price':25.5,'minimum_quantity':12,'contract_months':12,'shipping_days':4}]
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('elephant_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_elephant_output_schema_product_and_summary():
 m=load_solution(); n=m.BabyShowerNegotiation(); assert m.DOMAIN=='elephant_baby_shower_bargaining' and n.product=='Jungle Baby Shower Theme Centerpiece' and n.original_price==29.99 and n.rating==4.7; assert all(h in n.render_summary() for h in ['Iteration Summary','Agent Actions and Tools Used','Key Strategies and Observations','Progress Towards Agreement']); r,c=docs(); assert c['artifact_type']=='elephant_centerpiece_supply_agreement_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_elephant_latest_supply_terms_replace_price_only_draft():
 m=load_solution(); n=m.BabyShowerNegotiation(); n.buyer_draft(24,12,1); n.apply_supply_terms(TIERS,3); selected=n.select_tier('buyer','planner_partner',12,4); stale=n.select_tier('buyer','single_event',1,2); assert selected['unit_price']==25.5 and selected['contract_months']==12 and stale['status']=='stale' and n.current_offer['name']=='planner_partner'; agreement=n.finalize(); assert agreement['quantity']==12 and agreement['shipping_days']==4 and agreement['rating']==4.7
def test_elephant_priorities_rejections_and_ledger_are_preserved():
 m=load_solution(); n=m.BabyShowerNegotiation(); n.buyer_draft(24,1,1); n.apply_supply_terms(TIERS,3); assert n.select_tier('buyer','planner_partner',2,4)['status']=='rejected'; n.select_tier('buyer','single_event',1,5); n.finalize(); assert n.rejected[0]['reason']=='below_minimum_quantity' and n.buyer_priorities==['price','quality'] and n.seller_goal=='long_term_contract' and len(n.transcript)>=4
def test_elephant_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='elephant_centerpiece_supply_v2' and r['authority']['product']=='Jungle Baby Shower Theme Centerpiece' and r['authority']['rating']==4.7 and len(r['authority']['tiers'])==2; assert c['upstream_depth']==4 and c['preserved_workflows']==['negotiation_transcript','rejected_offers','buyer_quality_priority','seller_long_term_goal']
''',
    },
    "mab-late-constraint-c88a633e8f": {
        "source_id":"bargaining:003","benchmark":"bargaining","prefix":"mab_bargain03_rhapsody","domain":"rhapsody_bag_bargaining","class_name":"RhapsodyBagNegotiation","scenario_class":"result_eventful","theme":"late_or_out_of_order_superseded_result","event":"seller_warranty_logistics_matrix_arrived","event_id":"evt.mab_late_constraint_c88a.seller_warranty_logistics_matrix_arrived","artifact":"rhapsody_bag_warranty_agreement_closure",
        "meaning":"Late seller warranty and logistics terms supersede provisional Rhapsody bag drafts while buyer support goals, seller cost constraints, transcript, and rejected offers remain auditable.",
        "authority":{"contract":"rhapsody_warranty_logistics_v2","product":"Rhapsody Cross Body Bag in Black, One Size","rating":4.5,"tiers":[{"name":"standard","price":149.0,"warranty_days":90,"support":"email","return_days":30,"shipping_days":7},{"name":"care_plus","price":159.0,"warranty_days":365,"support":"priority","return_days":60,"shipping_days":3}]},
        "preserved":["negotiation_transcript","rejected_offers","buyer_warranty_priority","seller_logistics_goal"],
        "extension":"Produce an auditable negotiation for the specified 4.5-rated Rhapsody Cross Body Bag. Three upstream workstreams preserve buyer warranty/support priorities, seller logistics-cost goals, and role tool actions. A later evaluator-owned seller warranty/logistics matrix supersedes provisional drafts. Enforce newest authority, explicit price, coverage, support, return, and shipping terms, preserve rejected offers, and close with the required negotiation-summary sections.",
        "provenance":"Rhapsody Cross Body Bag bargaining task","behavior_flag":"ENFORCE_LATEST_WARRANTY_MATRIX = True","preserve_flag":"PRESERVE_NEGOTIATION_LEDGER = True",
        "requirements":["Preserve the buyer's comprehensive warranty and after-sales-support objective.","Preserve seller logistics-cost and operational-efficiency constraints.","Record every offer, counter, rejection, information action, and progress state.","Apply only the newest warranty/logistics matrix and finalize complete explicit terms."],
        "before":"A provisional bag price has been discussed without authoritative warranty, support, return, and shipping terms.","after":"The newest seller matrix supersedes earlier drafts and closes a complete warranty-and-logistics agreement while retaining the ledger.",
        "semantic_labels":{"output_schema":"The implementation and rhapsody_bag_warranty_agreement_closure expose the exact bag identity and required summary sections.","task_behavior":"Newest warranty/logistics tiers govern price, coverage, support, returns, and shipping; stale offers cannot overwrite them.","preservation":"Preserves transcript, rejected offers, buyer warranty priorities, and seller logistics goals.","event_closure":"The late seller matrix displaces provisional terms and the final agreement is bound to its receipt."},
        "canonical": r'''DOMAIN='rhapsody_bag_bargaining'
EVENT_SCHEMA='rhapsody_warranty_logistics_v2'
ENFORCE_LATEST_WARRANTY_MATRIX = True
PRESERVE_NEGOTIATION_LEDGER = True
class RhapsodyBagNegotiation:
 def __init__(self):
  self.product='Rhapsody Cross Body Bag in Black, One Size'; self.original_price=149.0; self.rating=4.5; self.buyer_priorities=['comprehensive_warranty','after_sales_support']; self.seller_goal='reduce_logistics_cost'; self.transcript=[]; self.rejected=[]; self.authority_sequence=0; self.tiers={}; self.current_offer=None; self.agreement=None
 def _record(self,row):
  if PRESERVE_NEGOTIATION_LEDGER:self.transcript.append(dict(row))
 def provisional_offer(self,price,sequence):
  self.current_offer={'actor':'buyer','product':self.product,'price':float(price),'sequence':int(sequence)}; self._record({'action':'offer_price',**self.current_offer}); return dict(self.current_offer)
 def apply_matrix(self,tiers,sequence):
  if ENFORCE_LATEST_WARRANTY_MATRIX and sequence<=self.authority_sequence:self.rejected.append({'reason':'stale_authority','sequence':sequence}); return {'status':'stale'}
  self.authority_sequence=int(sequence); self.tiers={t['name']:dict(t) for t in tiers}; self.current_offer=None; self._record({'action':'provide_information','actor':'seller','sequence':sequence,'tiers':sorted(self.tiers)}); return {'status':'authority_applied'}
 def select_tier(self,actor,name,sequence):
  if ENFORCE_LATEST_WARRANTY_MATRIX and sequence<=self.authority_sequence:self.rejected.append({'reason':'stale_offer','sequence':sequence}); return {'status':'stale'}
  offer={'actor':actor,'product':self.product,'rating':self.rating,'sequence':int(sequence),**self.tiers[name]}; self.current_offer=offer; self._record({'action':'counter_offer',**offer}); return dict(offer)
 def finalize(self):
  o=self.current_offer; required={'product','price','warranty_days','support','return_days','shipping_days'}
  if not o or not required<=set(o) or o['warranty_days']<=0 or not o['support'] or o['return_days']<=0 or o['shipping_days']<=0: raise ValueError('complete warranty/logistics terms required')
  self.agreement={k:o[k] for k in ['product','price','warranty_days','support','return_days','shipping_days']}; self._record({'action':'end_negotiation','agreement':dict(self.agreement)}); return dict(self.agreement)
 def render_summary(self):
  status='Agreement reached' if self.agreement else 'Negotiation active'; return '\n'.join(['**[Iteration Summary]**',status,'**[Agent Actions and Tools Used]**',f'Actions recorded: {len(self.transcript)}','**[Key Strategies and Observations]**','Warranty support and logistics cost were reconciled.','**[Progress Towards Agreement]**',status])
''',
        "tests": r'''from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); TIERS=[{'name':'standard','price':149.0,'warranty_days':90,'support':'email','return_days':30,'shipping_days':7},{'name':'care_plus','price':159.0,'warranty_days':365,'support':'priority','return_days':60,'shipping_days':3}]
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('bag_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_rhapsody_output_schema_product_and_summary():
 m=load_solution(); n=m.RhapsodyBagNegotiation(); assert m.DOMAIN=='rhapsody_bag_bargaining' and n.product=='Rhapsody Cross Body Bag in Black, One Size' and n.original_price==149 and n.rating==4.5; assert all(h in n.render_summary() for h in ['Iteration Summary','Agent Actions and Tools Used','Key Strategies and Observations','Progress Towards Agreement']); r,c=docs(); assert c['artifact_type']=='rhapsody_bag_warranty_agreement_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_rhapsody_latest_matrix_supersedes_stale_price_only_offer():
 m=load_solution(); n=m.RhapsodyBagNegotiation(); n.provisional_offer(140,1); n.apply_matrix(TIERS,3); selected=n.select_tier('buyer','care_plus',4); stale=n.select_tier('buyer','standard',2); assert selected['warranty_days']==365 and selected['support']=='priority' and selected['shipping_days']==3 and stale['status']=='stale' and n.current_offer['name']=='care_plus'; assert n.finalize()['return_days']==60
def test_rhapsody_warranty_priorities_logistics_goal_and_ledger_are_preserved():
 m=load_solution(); n=m.RhapsodyBagNegotiation(); n.provisional_offer(145,1); n.apply_matrix(TIERS,3); n.select_tier('buyer','standard',4); n.finalize(); assert n.buyer_priorities==['comprehensive_warranty','after_sales_support'] and n.seller_goal=='reduce_logistics_cost' and len(n.transcript)==4; assert n.rejected==[]
def test_rhapsody_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='rhapsody_warranty_logistics_v2' and r['authority']['product']=='Rhapsody Cross Body Bag in Black, One Size' and len(r['authority']['tiers'])==2; assert c['upstream_depth']==4 and c['preserved_workflows']==['negotiation_transcript','rejected_offers','buyer_warranty_priority','seller_logistics_goal']
''',
    },
    "mab-dependency-unblock-0394988930": {
        "source_id":"research:030","benchmark":"research","prefix":"mab_research30_fdiv","domain":"text_to_image_f_divergence_alignment","class_name":"DivergenceAlignmentProposal","scenario_class":"result_eventful","theme":"delayed_authoritative_result","event":"f_divergence_surrogate_derivation_completed","event_id":"evt.mab_dependency_unblock_0394.f_divergence_surrogate_completed","artifact":"five_question_f_divergence_proposal_closure",
        "meaning":"A delayed mathematical derivation replaces a generic alignment objective with an assumption-bounded f-divergence surrogate and reverse-KL consistency case while preserving the five-question research proposal and diversity motivation.",
        "authority":{"contract":"f_divergence_alignment_derivation_v3","divergences":["reverse_kl","forward_kl","jensen_shannon","alpha_divergence"],"assumptions":["absolute_continuity","convex_generator","finite_preference_log_ratio"],"consistency_case":"reverse_kl_recovers_diffusion_dpo"},
        "preserved":["five_question_structure","human_preference_motivation","diversity_collapse_gap","dataset_and_metric_plan"],
        "extension":"Produce the required five-question proposal on text-to-image preference alignment. Three upstream workstreams preserve the introduction's RLHF complexity, implicit-reward progress, and diversity-collapse gap. A fourth evaluator-owned mathematical derivation arrives later. Integrate its arbitrary-f-divergence assumptions and reverse-KL consistency case into the problem, hardness, novelty, and method; retain a concrete preference dataset, image-quality and diversity metrics, ablations, and expected outcomes.",
        "provenance":"text-to-image f-divergence preference-alignment research task","behavior_flag":"USE_DERIVED_F_DIVERGENCE_AUTHORITY = True","preserve_flag":"PRESERVE_FIVE_QUESTION_STRUCTURE = True",
        "requirements":["Preserve the introduction's human-preference alignment and reward-model complexity motivation.","Formulate exactly one research question and explain importance, hardness, and the unresolved gap.","Specify preference data, f-divergence objectives, baselines, quality/diversity metrics, and ablations.","Integrate the delayed mathematical derivation and verify the reverse-KL consistency case."],
        "before":"A five-question draft motivates diversity but still contains a generic objective without validity assumptions or a reverse-KL consistency check.","after":"The proposal uses the returned arbitrary-f-divergence derivation, states its assumptions, recovers the reverse-KL special case, and preserves the complete experimental plan.",
        "semantic_labels":{"output_schema":"The proposal exposes exactly five required questions and a five_question_f_divergence_proposal_closure.","task_behavior":"The method compares multiple f-divergences under explicit assumptions, includes reverse-KL recovery, preference data, quality/diversity metrics, and ablations.","preservation":"Preserves the human-preference motivation, RLHF/reward-model limitation, diversity-collapse gap, and five-question structure.","event_closure":"The delayed derivation revises only affected research claims and is bound to the final proposal receipt."},
        "canonical": r'''DOMAIN='text_to_image_f_divergence_alignment'
EVENT_SCHEMA='f_divergence_alignment_derivation_v3'
USE_DERIVED_F_DIVERGENCE_AUTHORITY = True
PRESERVE_FIVE_QUESTION_STRUCTURE = True
class DivergenceAlignmentProposal:
 def __init__(self):
  self.premises=['human preference alignment','separate reward-model complexity','reverse-KL mode seeking can reduce diversity','implicit-reward optimization']; self.authority=None
 def apply_derivation(self,authority):
  required={'divergences','assumptions','consistency_case'}
  if not required<=set(authority): raise ValueError('incomplete derivation')
  self.authority=dict(authority); return self.authority
 def build_5q(self):
  if USE_DERIVED_F_DIVERGENCE_AUTHORITY and not self.authority: raise RuntimeError('mathematical authority required')
  method=('Optimize text-to-image preferences with direct pairwise implicit rewards under reverse KL, forward KL, Jensen-Shannon, and alpha-divergence constraints; require absolute continuity, a convex generator, and finite preference log-ratios; verify that reverse KL recovers Diffusion-DPO. Use Pick-a-Pic and HPS preference pairs, compare Diffusion-DPO and reward-model RLHF baselines, report PickScore, ImageReward, CLIP alignment, LPIPS diversity, prompt-level coverage, stability, and memory, and ablate divergence, coefficient, and data scale. Expected results are comparable preference alignment with measurably better diversity and stable optimization.') if USE_DERIVED_F_DIVERGENCE_AUTHORITY else 'Use a generic preference objective and report image quality.'
  rows={
   'question_1':'Which f-divergence constraints best align text-to-image generators with human preferences without collapsing output diversity?',
   'question_2':'Solving this would connect direct preference alignment to controllable quality-diversity trade-offs and reduce reliance on a separately trained reward model.',
   'question_3':'The objective must estimate preference log-ratios stably while satisfying absolute-continuity and convex-generator assumptions; naive repeated fine-tuning can overfit pairs and collapse modes.',
   'question_4':'Prior text-to-image alignment emphasizes reverse KL and underexplores forward KL, Jensen-Shannon, and alpha-divergence in one controlled direct-preference framework with diversity evaluation.',
   'question_5':method,
  }
  return rows if PRESERVE_FIVE_QUESTION_STRUCTURE else {'question_1':rows['question_1'],'question_5':rows['question_5']}
 def render(self):
  q=self.build_5q(); return '\n\n'.join(f'**[Question {i}]**\n{q[f"question_{i}"]}' for i in range(1,6))
''',
        "tests": r'''from __future__ import annotations
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
''',
    },
    "mab-dependency-unblock-107bc4fe3f": {
        "source_id":"coding:017","benchmark":"coding","prefix":"mab_code17_maze","domain":"multi_agent_maze","class_name":"MultiAgentMaze","scenario_class":"live_eventful","theme":"task_scope_or_dependency_change","event":"versioned_maze_transition_dependency_added","event_id":"evt.mab_dependency_unblock_107b.versioned_maze_transition_added","artifact":"versioned_maze_collaboration_closure",
        "meaning":"A newly authoritative role-and-version transition dependency governs collaborative block movement while maze layout, communication, saved progress, tutorial state, and achievements remain intact.",
        "authority":{"contract":"maze_transition_protocol_v2","roles":{"scout":["inspect","message"],"builder":["move_block","message"],"navigator":["move_player","message"]},"requires_expected_version":True,"collision_policy":"reject_occupied_destination"},
        "preserved":["maze_layout","collaboration_messages","saved_progress","tutorial_and_achievements"],
        "extension":"Build MultiAgentMaze with distinct cooperative roles, movable blocks, path finding, shared messages, progress persistence, tutorials, difficulty, and achievements. Three upstream workstreams establish the maze and collaboration state. A fourth evaluator-owned dependency adds an authoritative role-permission, optimistic-version, and collision protocol. Replan affected moves, reject stale or unauthorized operations, preserve existing state, and reverify a cooperative path to the exit.",
        "provenance":"MultiAgentMaze","behavior_flag":"ENFORCE_AUTHORITY_TRANSITIONS = True","preserve_flag":"PRESERVE_MAZE_HISTORY = True",
        "requirements":["Implement maze layout, obstacles, difficulty, player and block state.","Implement distinct cooperative roles, shared messaging, and role-specific actions.","Implement path validation, progress save/load, tutorials, and achievements.","Integrate the new role/version/collision dependency and reverify cooperative completion."],
        "before":"Players and blocks can move using provisional rules without authoritative role permissions or optimistic version checks.","after":"All affected moves enforce the returned role, expected-version, and occupied-destination protocol while prior maze and collaboration state is preserved.",
        "semantic_labels":{"output_schema":"solution.py exposes MultiAgentMaze and the versioned_maze_collaboration_closure.","task_behavior":"Role permissions, optimistic versions, collision rejection, block movement, and path reachability follow the returned transition protocol.","preservation":"Preserves maze layout, collaboration messages, saved progress, tutorial state, and achievements.","event_closure":"The dependency change selectively revises transitions and closes only after a valid cooperative path is reverified."},
        "canonical": r'''DOMAIN='multi_agent_maze'
EVENT_SCHEMA='maze_transition_protocol_v2'
ENFORCE_AUTHORITY_TRANSITIONS = True
PRESERVE_MAZE_HISTORY = True
from collections import deque
class MultiAgentMaze:
 def __init__(self,width,height,walls=(),exit_cell=None,difficulty='medium'):
  self.width=width; self.height=height; self.walls=set(map(tuple,walls)); self.exit=tuple(exit_cell or (width-1,height-1)); self.difficulty=difficulty; self.players={}; self.blocks={}; self.messages=[]; self.history=[]; self.saved={}; self.tutorial={}; self.achievements=set(); self.version=0; self.protocol=None
 def add_player(self,player_id,role,position):
  if role not in {'scout','builder','navigator'}: raise ValueError('invalid role')
  self.players[player_id]={'role':role,'position':tuple(position)}; self.tutorial[player_id]=set(); return self.players[player_id]
 def add_block(self,block_id,position): self.blocks[block_id]=tuple(position)
 def apply_transition_protocol(self,protocol):
  if protocol.get('collision_policy')!='reject_occupied_destination' or not protocol.get('requires_expected_version'): raise ValueError('invalid protocol')
  self.protocol=dict(protocol); return self.protocol
 def _authorize(self,player_id,action,expected_version):
  if ENFORCE_AUTHORITY_TRANSITIONS:
   if not self.protocol: raise RuntimeError('transition dependency unresolved')
   if expected_version!=self.version: raise RuntimeError('stale maze version')
   if action not in self.protocol['roles'][self.players[player_id]['role']]: raise PermissionError('role cannot perform action')
 def _free(self,pos,ignore_block=None):
  p=tuple(pos); occupied=set(self.walls)|{v for k,v in self.blocks.items() if k!=ignore_block}|{v['position'] for v in self.players.values()}
  return 0<=p[0]<self.width and 0<=p[1]<self.height and p not in occupied
 def move_block(self,player_id,block_id,destination,expected_version):
  self._authorize(player_id,'move_block',expected_version)
  if not self._free(destination,block_id): raise ValueError('occupied destination')
  before=self.blocks[block_id]; self.blocks[block_id]=tuple(destination); self.version+=1
  if PRESERVE_MAZE_HISTORY:self.history.append(('move_block',player_id,block_id,before,tuple(destination),self.version))
  return self.version
 def move_player(self,player_id,destination,expected_version):
  self._authorize(player_id,'move_player',expected_version)
  if not self._free(destination): raise ValueError('occupied destination')
  self.players[player_id]['position']=tuple(destination); self.version+=1
  if PRESERVE_MAZE_HISTORY:self.history.append(('move_player',player_id,tuple(destination),self.version))
  if tuple(destination)==self.exit:self.achievements.add((player_id,'maze_complete'))
  return self.version
 def message(self,player_id,text):
  row={'player':player_id,'text':text,'version':self.version}
  if PRESERVE_MAZE_HISTORY:self.messages.append(row)
  return row
 def path_exists(self,start):
  start=tuple(start); blocked=self.walls|set(self.blocks.values()); q=deque([start]); seen={start}
  while q:
   p=q.popleft()
   if p==self.exit:return True
   for n in ((p[0]+1,p[1]),(p[0]-1,p[1]),(p[0],p[1]+1),(p[0],p[1]-1)):
    if 0<=n[0]<self.width and 0<=n[1]<self.height and n not in blocked and n not in seen:seen.add(n); q.append(n)
  return False
 def complete_tutorial(self,player_id,step):
  if PRESERVE_MAZE_HISTORY:self.tutorial[player_id].add(step)
 def save_progress(self,key):
  snap={'players':{k:dict(v) for k,v in self.players.items()},'blocks':dict(self.blocks),'version':self.version,'achievements':set(self.achievements)}
  if PRESERVE_MAZE_HISTORY:self.saved[key]=snap
  return snap
 def load_progress(self,key): return self.saved[key]
''',
        "tests": r'''from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); PROTOCOL={'roles':{'scout':['inspect','message'],'builder':['move_block','message'],'navigator':['move_player','message']},'requires_expected_version':True,'collision_policy':'reject_occupied_destination'}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('maze_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_maze_output_schema_layout_and_artifacts():
 m=load_solution(); maze=m.MultiAgentMaze(4,3,walls=[(1,1)],exit_cell=(3,2),difficulty='hard'); assert m.DOMAIN=='multi_agent_maze' and maze.exit==(3,2) and maze.difficulty=='hard'; r,c=docs(); assert c['artifact_type']=='versioned_maze_collaboration_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_maze_role_version_collision_block_move_and_path_behavior():
 m=load_solution(); maze=m.MultiAgentMaze(4,3,walls=[(1,1)],exit_cell=(3,2)); maze.add_player('b','builder',(0,0)); maze.add_player('n','navigator',(0,1)); maze.add_player('s','scout',(0,2)); maze.add_block('box',(1,0)); maze.apply_transition_protocol(PROTOCOL); assert maze.move_block('b','box',(2,0),0)==1
 for call,exc in [(lambda:maze.move_block('s','box',(3,0),1),PermissionError),(lambda:maze.move_block('b','box',(3,0),0),RuntimeError),(lambda:maze.move_block('b','box',(0,1),1),ValueError)]:
  try:call()
  except exc:pass
  else:raise AssertionError('invalid transition accepted')
 assert maze.path_exists((0,1)) is True
def test_maze_messages_progress_tutorial_and_achievements_are_preserved():
 m=load_solution(); maze=m.MultiAgentMaze(2,2,exit_cell=(1,1)); maze.add_player('n','navigator',(0,0)); maze.apply_transition_protocol(PROTOCOL); maze.message('n','move east then south'); maze.complete_tutorial('n','movement'); maze.move_player('n',(1,0),0); maze.move_player('n',(1,1),1); snap=maze.save_progress('team')
 assert maze.messages[0]['text']=='move east then south' and 'movement' in maze.tutorial['n'] and ('n','maze_complete') in maze.achievements and snap['version']==2 and maze.load_progress('team')['blocks']=={}
def test_maze_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='maze_transition_protocol_v2' and r['authority']['requires_expected_version'] is True and r['authority']['collision_policy']=='reject_occupied_destination' and set(r['authority']['roles'])=={'scout','builder','navigator'}; assert c['upstream_depth']==4 and c['preserved_workflows']==['maze_layout','collaboration_messages','saved_progress','tutorial_and_achievements']
''',
    },
    "mab-late-constraint-9636e9ce85": {
        "source_id":"coding:061","benchmark":"coding","prefix":"mab_code61_office","domain":"office_task_collaboration_manager","class_name":"OfficeTaskCollaborationManager","scenario_class":"live_eventful","theme":"task_scope_or_dependency_change","event":"dependency_approval_sla_policy_added","event_id":"evt.mab_late_constraint_9636.dependency_approval_sla_added","artifact":"office_dependency_policy_closure",
        "meaning":"A late dependency, approval, and SLA policy changes task completion and alert behavior while assignments, comments, audit history, and report snapshots remain intact.",
        "authority":{"contract":"office_dependency_sla_policy_v2","completion_requires":["all_dependencies_done","high_priority_manager_approval"],"overdue_alert_roles":["assignee","manager"],"allowed_statuses":["todo","in_progress","blocked","done"]},
        "preserved":["task_assignments","collaboration_comments","task_audit_history","report_snapshots"],
        "extension":"Build Office_Task_Collaboration_Manager with users and roles, assignment and delegation, dependency-aware status updates, collaboration comments, real-time alerts, and reports. Three upstream workstreams establish task and communication state. A fourth evaluator-owned policy adds dependency completion, high-priority approval, and overdue-alert constraints. Replan only affected status and alert behavior, preserve prior assignments and history, and reverify reports.",
        "provenance":"Office_Task_Collaboration_Manager","behavior_flag":"ENFORCE_DEPENDENCY_POLICY = True","preserve_flag":"PRESERVE_TASK_AUDIT = True",
        "requirements":["Implement users, roles, task creation, assignment, delegation, and status tracking.","Implement dependencies, comments, collaborative updates, and task history.","Implement overdue alerts and status/assignee/department reports.","Integrate the late dependency, approval, and SLA policy and reverify affected workflows."],
        "before":"Tasks can be marked done and alerts generated under provisional rules that ignore dependency closure and high-priority approval.","after":"Completion and alerts follow the returned dependency/approval/SLA policy while assignments, comments, audit history, and reports are preserved.",
        "semantic_labels":{"output_schema":"solution.py exposes OfficeTaskCollaborationManager and the office_dependency_policy_closure.","task_behavior":"Completion requires finished dependencies and manager approval for high-priority work; overdue alerts target assignee and manager.","preservation":"Preserves assignments, delegation, comments, audit history, and report snapshots.","event_closure":"The late policy selectively revises status and alert behavior and is bound to the final closure receipt."},
        "canonical": r'''DOMAIN='office_task_collaboration_manager'
EVENT_SCHEMA='office_dependency_sla_policy_v2'
ENFORCE_DEPENDENCY_POLICY = True
PRESERVE_TASK_AUDIT = True
class OfficeTaskCollaborationManager:
 def __init__(self):
  self.users={}; self.tasks={}; self.comments=[]; self.audit=[]; self.alerts=[]; self.reports=[]; self.policy=None
 def add_user(self,user_id,role,department):
  if role not in {'employee','manager','admin'}: raise ValueError('invalid role')
  self.users[user_id]={'role':role,'department':department}
 def apply_policy(self,policy):
  required={'completion_requires','overdue_alert_roles','allowed_statuses'}
  if not required<=set(policy): raise ValueError('incomplete policy')
  self.policy=dict(policy); return self.policy
 def create_task(self,actor,task_id,title,assignee,department,priority='normal',due_at=None,dependencies=()):
  if actor not in self.users or assignee not in self.users or task_id in self.tasks: raise ValueError('invalid task')
  self.tasks[task_id]={'title':title,'assignee':assignee,'department':department,'priority':priority,'due_at':due_at,'dependencies':list(dependencies),'status':'todo','approved_by':None}; self._audit('create',actor,task_id); return self.tasks[task_id]
 def _audit(self,action,actor,task_id):
  if PRESERVE_TASK_AUDIT:self.audit.append({'action':action,'actor':actor,'task_id':task_id})
 def delegate(self,actor,task_id,new_assignee):
  if self.users[actor]['role'] not in {'manager','admin'}: raise PermissionError('manager required')
  self.tasks[task_id]['assignee']=new_assignee; self._audit('delegate',actor,task_id)
 def comment(self,actor,task_id,text):
  row={'actor':actor,'task_id':task_id,'text':text}
  if PRESERVE_TASK_AUDIT:self.comments.append(row); self._audit('comment',actor,task_id)
  return row
 def approve(self,manager,task_id):
  if self.users[manager]['role'] not in {'manager','admin'}: raise PermissionError('manager required')
  self.tasks[task_id]['approved_by']=manager; self._audit('approve',manager,task_id)
 def update_status(self,actor,task_id,status):
  t=self.tasks[task_id]
  if ENFORCE_DEPENDENCY_POLICY:
   if not self.policy: raise RuntimeError('policy unresolved')
   if status not in self.policy['allowed_statuses']: raise ValueError('invalid status')
   if status=='done' and any(self.tasks[d]['status']!='done' for d in t['dependencies']): raise RuntimeError('dependencies incomplete')
   if status=='done' and t['priority']=='high' and not t['approved_by']: raise PermissionError('high priority approval required')
  t['status']=status; self._audit('status:'+status,actor,task_id); return status
 def generate_overdue_alerts(self,now):
  if ENFORCE_DEPENDENCY_POLICY and not self.policy: raise RuntimeError('policy unresolved')
  for tid,t in self.tasks.items():
   if t['due_at'] is not None and t['due_at']<now and t['status']!='done':
    recipients=[t['assignee']]+[u for u,v in self.users.items() if v['role']=='manager' and v['department']==t['department']]
    self.alerts.append({'task_id':tid,'recipients':sorted(set(recipients))})
  return list(self.alerts)
 def report(self,department):
  rows=[t for t in self.tasks.values() if t['department']==department]; report={'department':department,'total':len(rows),'done':sum(t['status']=='done' for t in rows),'blocked':sum(t['status']=='blocked' for t in rows)}
  if PRESERVE_TASK_AUDIT:self.reports.append(report)
  return report
''',
        "tests": r'''from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); POLICY={'completion_requires':['all_dependencies_done','high_priority_manager_approval'],'overdue_alert_roles':['assignee','manager'],'allowed_statuses':['todo','in_progress','blocked','done']}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('office_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_office_output_schema_task_assignment_and_artifacts():
 m=load_solution(); app=m.OfficeTaskCollaborationManager(); assert m.DOMAIN=='office_task_collaboration_manager'; app.add_user('mgr','manager','ops'); app.add_user('ana','employee','ops'); app.apply_policy(POLICY); app.create_task('mgr','t','Prepare report','ana','ops'); assert app.tasks['t']['assignee']=='ana'; r,c=docs(); assert c['artifact_type']=='office_dependency_policy_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_office_dependency_approval_status_and_overdue_alert_behavior():
 m=load_solution(); app=m.OfficeTaskCollaborationManager(); app.add_user('mgr','manager','ops'); app.add_user('ana','employee','ops'); app.apply_policy(POLICY); app.create_task('mgr','base','Collect data','ana','ops',due_at=2); app.create_task('mgr','final','Publish','ana','ops',priority='high',due_at=3,dependencies=['base'])
 for call,exc in [(lambda:app.update_status('ana','final','done'),RuntimeError),(lambda:app.update_status('ana','final','unknown'),ValueError)]:
  try:call()
  except exc:pass
  else:raise AssertionError('invalid status accepted')
 app.update_status('ana','base','done')
 try:app.update_status('ana','final','done')
 except PermissionError:pass
 else:raise AssertionError('approval bypassed')
 app.approve('mgr','final'); assert app.update_status('ana','final','done')=='done'; app.create_task('mgr','late','Late item','ana','ops',due_at=1); assert app.generate_overdue_alerts(5)==[{'task_id':'late','recipients':['ana','mgr']}]
def test_office_delegation_comments_audit_and_reports_are_preserved():
 m=load_solution(); app=m.OfficeTaskCollaborationManager(); app.add_user('mgr','manager','ops'); app.add_user('a','employee','ops'); app.add_user('b','employee','ops'); app.apply_policy(POLICY); app.create_task('mgr','t','Coordinate','a','ops'); app.delegate('mgr','t','b'); app.comment('b','t','handoff complete'); app.update_status('b','t','in_progress'); report=app.report('ops'); assert app.tasks['t']['assignee']=='b' and app.comments[0]['text']=='handoff complete' and len(app.audit)==4 and report=={'department':'ops','total':1,'done':0,'blocked':0} and app.reports==[report]
def test_office_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='office_dependency_sla_policy_v2' and set(r['authority']['completion_requires'])=={'all_dependencies_done','high_priority_manager_approval'} and r['authority']['overdue_alert_roles']==['assignee','manager']; assert c['upstream_depth']==4 and c['preserved_workflows']==['task_assignments','collaboration_comments','task_audit_history','report_snapshots']
''',
    },
}


def _dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _slug(text: str, limit: int = 28) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return value[:limit].rstrip("_") or "requirement"


def _official_instruction(bp: Path) -> str:
    official = json.loads((bp / "private/source_manifests/03-official_task.json").read_text(encoding="utf-8"))["task"]
    content = str(official["content"]).strip()
    output = str(official.get("output_format") or "").strip()
    return content + (("\n\n" + output) if output else "")


def _decisions(cid: str, cfg: dict, req_ids: list[str]) -> list[dict]:
    prefix = cid.replace("-", "_")
    if cfg["theme"] == "duplicate_or_replayed_completion":
        specs = [
            ("classify_duplicate", "event_intake", "deduplicate_completion", True),
            ("preserve_idempotency", "state_revision", "deduplicate_completion", False),
            ("verify_closure", "closure", "rederive_from_authority", True),
        ]
    elif cfg["theme"] == "task_scope_or_dependency_change":
        specs = [
            ("classify_scope_delta", "event_intake", "wait_for_authority", True),
            ("revise_affected", "state_revision", "resolve_authority", False),
            ("preserve_unaffected", "plan_revision", "selective_replan", False),
            ("verify_closure", "closure", "rederive_from_authority", True),
        ]
    elif cfg["theme"] == "late_or_out_of_order_superseded_result":
        specs = [
            ("classify_stale", "event_intake", "wait_for_authority", True),
            ("exclude_stale", "state_revision", "resolve_authority", False),
            ("verify_closure", "closure", "rederive_from_authority", True),
        ]
    else:
        specs = [
            ("classify_authority", "event_intake", "wait_for_authority", True),
            ("revise_affected", "state_revision", "resolve_authority", False),
            ("verify_closure", "closure", "rederive_from_authority", True),
        ]
    anchors = [f"{prefix}.event.receipt", f"{prefix}.source.task_behavior", f"{prefix}.source.preservation", f"{prefix}.closure"]
    decisions = []
    for index, (obligation, stage, gate, critical) in enumerate(specs, 1):
        req_id = req_ids[min(index - 1, len(req_ids) - 1)]
        decisions.append({
            "id": f"{index:02d}_{obligation}_{_slug(cfg['event'], 20)}",
            "decision_group": f"{obligation}_{_slug(cfg['event'], 30)}",
            "task_requirement_id": req_id,
            "obligation": obligation,
            "stage_tag": stage,
            "gate": gate,
            "gate_args": {"artifacts": ["final_state"], "preserve_artifacts": ["preserve_prior"], "workstreams": [req_id]},
            "required_behavior": f"{obligation}: {cfg['meaning']}",
            "forbidden_behavior": f"Do not ignore, double-apply, over-apply, or falsely close {cfg['event']}.",
            "primary_evidence": f"episode_trace:{stage}:{obligation}",
            "outcome_anchors": anchors,
            "must_still_pass": [f"{prefix}.source.preservation"],
            "mutation_family": obligation,
            "critical": critical,
        })
    return decisions


def prepare_blueprint(bp: Path, cid: str, cfg: dict) -> None:
    source_text = _official_instruction(bp)
    _dump(bp / "private/source_task.yaml", {"instruction": source_text, "task_id": cfg["source_id"]})
    reqs = []
    req_ids = []
    prefix = cid.replace("-", "_")
    for index, description in enumerate(cfg["requirements"], 1):
        req_id = f"req.{index:02d}.{_slug(description)}"
        req_ids.append(req_id)
        reqs.append({"id": req_id, "description": description, "observable_probe": f"{prefix}.source.task_behavior", "public_evidence": f"source instruction and requirement_worker_{index:02d} result"})
    event_id = cfg["event_id"]
    nodes = [{"id": "event_input", "kind": "event"}] + [{"id": r, "kind": "requirement"} for r in req_ids] + [{"id": "final_state", "kind": "closure"}, {"id": "preserve_prior", "kind": "preservation"}]
    edges = [{"source": "event_input", "target": r, "relation": "invalidates"} for r in req_ids] + [{"source": r, "target": "final_state", "relation": "depends_on"} for r in req_ids]
    decisions = _decisions(cid, cfg, req_ids)
    ir = {
        "schema_version": "1", "case_id": cid, "instance_id": "strict-source-native-1", "task_archetype": "source_native_task_causal_rebuild",
        "task_requirements": reqs,
        "event_contract": {"event_id": event_id, "primary_event_theme": cfg["theme"], "before_state": cfg["before"], "after_state": cfg["after"], "affected_nodes": ["event_input"], "affected_closure": ["event_input", *req_ids, "final_state"], "unaffected_nodes": ["preserve_prior"]},
        "dependency_graph": {"nodes": nodes, "edges": edges},
        "decision_contracts": decisions,
    }
    _dump(bp / "private/case_ir.json", ir)
    control_points = []
    for index, decision in enumerate(decisions, 1):
        dimension = decision["stage_tag"]
        point_id = f"{cfg['prefix']}.cf.{index:02d}_{decision['obligation']}_{_slug(cfg['event'], 18)}"
        control_points.append({
            "id": point_id,
            "independence_key": point_id,
            "mutation_id": f"{cfg['prefix']}.mutation.{index:02d}_{decision['obligation']}_{_slug(cfg['event'], 18)}",
            "decision_group": decision["decision_group"],
            "task_requirement_id": decision["task_requirement_id"],
            "dimension": dimension,
            "stage_tag": dimension,
            "obligation": decision["obligation"],
            "gate": decision["gate"],
            "gate_args": decision["gate_args"],
            "event_id": event_id,
            "expected_behavior": decision["required_behavior"],
            "forbidden_behavior": decision["forbidden_behavior"],
            "primary_evidence": decision["primary_evidence"],
            "outcome_anchors": decision["outcome_anchors"],
            "critical": decision["critical"],
            "measurement_type": "control",
            "capability_target": "async_dynamic_replanning",
            "execution_modes": ["async"],
            "relevance_tier": "critical" if decision["critical"] else "direct",
            "requires_outcome_anchor": False,
            "precondition": "The evaluator-owned event opportunity exists.",
            "precondition_contract": {"on_missing": "fail_point", "required_facts": ["authority_delivery"]},
            "evidence_group": f"{cfg['prefix']}.{decision['obligation']}",
            "evidence_spec": {"primary_fact": "authority_consumption", "subject": decision["task_requirement_id"]},
        })
    _dump(bp / "private/score_plan.json", {"semantic_points": [], "control_points": control_points, "negative_mutations": []})
    policy_rule = {
        "duplicate_or_replayed_completion": "A replayed completion is consumed exactly once and cannot duplicate side effects.",
        "late_or_out_of_order_superseded_result": "Only the newest authoritative lineage may revise state; superseded results remain excluded.",
        "delayed_authoritative_result": "Provisional work cannot close until the delayed authority is consumed and reverified.",
        "task_scope_or_dependency_change": "The live scope delta changes only its dependency closure and preserves unaffected commitments.",
    }[cfg["theme"]]
    _dump(bp / "private/event_policy.json", {
        "theme": cfg["theme"], "event_id": event_id, "authority_rule": policy_rule,
        "forbidden_shortcut": f"Do not ignore, double-apply, over-apply, or falsely close {cfg['event']}.",
        "required_decisions": [d["obligation"] for d in decisions],
        "event_contract": ir["event_contract"],
    })
    lock_path = bp / "private/source_lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    names = ["01-native_case.json", "03-official_task.json", "04-native_config.yaml"]
    files = [f"private/source_manifests/{name}" for name in names]
    hashes = {rel: hashlib.sha256((bp / rel).read_bytes()).hexdigest() for rel in files}
    lock["production_case_path"] = "."
    lock["source_files"] = files
    lock["source_file_sha256"] = hashes
    _dump(lock_path, lock)
