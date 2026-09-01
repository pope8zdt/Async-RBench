from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path


ALL_IDS = [
    "mab-dependency-unblock-472d364155",
    "mab-dependency-unblock-5585821bdf",
    "mab-late-constraint-13dc7627a3",
    "mab-late-constraint-79372889b3",
    "mab-dependency-unblock-ed6082b496",
    "mab-dependency-unblock-fe0736601e",
    "mab-late-test-evidence-60efb2bdee",
    "mab-dependency-unblock-fa3ee479d7",
]

RAW_SOURCE_CASES = {
    "mab-dependency-unblock-ed6082b496",
    "mab-dependency-unblock-fe0736601e",
    "mab-late-test-evidence-60efb2bdee",
    "mab-dependency-unblock-fa3ee479d7",
}


def research_canonical(domain: str, schema: str, question: str, importance: str, hardness: str, gap: str, method: str, premises: list[str]) -> str:
    return f'''DOMAIN={domain!r}
EVENT_SCHEMA={schema!r}
USE_RETURNED_RESEARCH_AUTHORITY = True
PRESERVE_FIVE_QUESTION_STRUCTURE = True
TOPIC_QUESTION={question!r}
IMPORTANCE={importance!r}
HARDNESS={hardness!r}
RESEARCH_GAP={gap!r}
METHOD={method!r}
SOURCE_PREMISES={premises!r}
class ResearchProposal:
 def __init__(self): self.authority=None; self.premises=list(SOURCE_PREMISES)
 def apply_authority(self,authority):
  if authority.get('contract')!=EVENT_SCHEMA: raise ValueError('wrong research authority')
  self.authority=dict(authority); return self.authority
 def build_5q(self):
  if USE_RETURNED_RESEARCH_AUTHORITY and not self.authority: raise RuntimeError('research authority required')
  method=METHOD if USE_RETURNED_RESEARCH_AUTHORITY else 'Run a generic baseline without the returned benchmark contract.'
  rows={{'question_1':TOPIC_QUESTION,'question_2':IMPORTANCE,'question_3':HARDNESS,'question_4':RESEARCH_GAP,'question_5':method}}
  return rows if PRESERVE_FIVE_QUESTION_STRUCTURE else {{'question_1':rows['question_1'],'question_5':rows['question_5']}}
 def render(self):
  q=self.build_5q(); return '\\n\\n'.join(f'**[Question {{i}}] - {{q[f"question_{{i}}"]}}' for i in range(1,6))
'''


def research_tests(domain: str, schema: str, artifact: str, keywords: list[str], preserved: list[str], premise_terms: list[str]) -> str:
    return f'''from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); AUTHORITY={{'contract':{schema!r},'benchmark_dimensions':['task_specific_method','data_protocol','metrics','ablations'],'version':2}}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('research_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_research_exact_five_question_schema_and_artifacts():
 m=load_solution(); p=m.ResearchProposal(); p.apply_authority(AUTHORITY); q=p.build_5q(); assert m.DOMAIN=={domain!r} and list(q)==[f'question_{{i}}' for i in range(1,6)] and q['question_1'].count('?')==1 and all(q.values()); assert all(f'Question {{i}}' in p.render() for i in range(1,6)); r,c=docs(); assert c['artifact_type']=={artifact!r} and c['upstream_depth']==4 and c['event_receipt_sha256']==r['receipt_sha256']
def test_research_task_specific_method_data_metrics_and_ablations():
 m=load_solution(); p=m.ResearchProposal(); p.apply_authority(AUTHORITY); text=' '.join(p.build_5q().values()).lower(); assert all(k in text for k in {keywords!r}); assert 'ablat' in text and any(x in text for x in ['dataset','benchmark','video','sequence','image'])
def test_research_source_premises_and_structure_are_preserved():
 m=load_solution(); p=m.ResearchProposal(); p.apply_authority(AUTHORITY); q=p.build_5q(); joined=' '.join(q.values()).lower(); assert len(q)==5 and all(term in (' '.join(p.premises)+' '+joined).lower() for term in {premise_terms!r})
def test_research_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=={schema!r} and r['authority']['contract']==m.EVENT_SCHEMA and r['authority']['version']==2; assert c['preserved_workflows']=={preserved!r} and c['source_semantics_reverified'] is True
'''


RUNTIME = {
    "mab-dependency-unblock-472d364155": {
        "source_id":"research:025","benchmark":"research","prefix":"mab_research25_exavatar","domain":"monocular_expressive_avatar","class_name":"ResearchProposal","scenario_class":"result_eventful","theme":"delayed_authoritative_result","event":"occlusion_coverage_benchmark_completed","event_id":"evt.mab_dependency_unblock_472d.avatar_coverage_benchmark_completed","artifact":"monocular_exavatar_research_closure",
        "meaning":"A delayed benchmark protocol replaces a generic avatar evaluation plan with expression, hand, body, occlusion, and novel-pose coverage while retaining the monocular-video, SMPL-X, and 3D Gaussian premises.",
        "authority":{"contract":"exavatar_coverage_benchmark_v2","benchmark_dimensions":["face_expression","hand_pose","body_pose","occlusion_completion"],"version":2},
        "preserved":["five_question_structure","monocular_capture_premise","smplx_3dgs_representation","novel_pose_evaluation_plan"],
        "extension":"Produce the required five-question proposal for expressive whole-body avatars from short monocular video. Three workstreams preserve the SMPL-X/3DGS representation, limited-pose problem, and occlusion ambiguity. A fourth evaluator-owned benchmark arrives later. Integrate expression, hand, body, occlusion, and novel-pose coverage, with concrete data, geometry/rendering metrics, ablations, and expected outcomes.",
        "provenance":"expressive monocular whole-body avatar research task","behavior_flag":"USE_RETURNED_RESEARCH_AUTHORITY = True","preserve_flag":"PRESERVE_FIVE_QUESTION_STRUCTURE = True",
        "requirements":["Preserve the monocular expressive-avatar problem and SMPL-X plus 3DGS context.","Formulate exactly one question and explain importance, hardness, and prior limitations.","Specify capture data, expression/hand/body evaluation, rendering and geometry metrics, and ablations.","Integrate the delayed occlusion-and-coverage benchmark and reverify the five-question proposal."],
        "before":"The proposal names monocular avatar ambiguity but lacks an authoritative coverage protocol for expressions, hands, body poses, and occlusions.","after":"The returned benchmark closes the proposal with explicit coverage, metrics, ablations, and expected novel-pose outcomes.",
        "semantic_labels":{"output_schema":"The result has exactly five questions and a monocular_exavatar_research_closure.","task_behavior":"The method binds monocular capture, SMPL-X, 3D Gaussian rendering, uncertainty-aware occlusion completion, task-specific data, metrics, and ablations.","preservation":"Preserves monocular capture, expressive face/hand/body drivability, hybrid representation, and novel-pose motivation.","event_closure":"The delayed coverage benchmark revises the method and evaluation without erasing the source premises."},
    },
    "mab-dependency-unblock-5585821bdf": {
        "source_id":"research:027","benchmark":"research","prefix":"mab_research27_driveexpl","domain":"driving_counterfactual_explanations","class_name":"ResearchProposal","scenario_class":"result_eventful","theme":"delayed_authoritative_result","event":"causal_explanation_protocol_completed","event_id":"evt.mab_dependency_unblock_5585.causal_explanation_protocol_completed","artifact":"driving_explanation_research_closure",
        "meaning":"A delayed causal evaluation protocol replaces saliency-only validation with faithful concept and counterfactual explanations for safety-critical driving while preserving human-understandability and liability goals.",
        "authority":{"contract":"driving_causal_explanation_protocol_v2","benchmark_dimensions":["causal_fidelity","counterfactual_validity","stability","human_usefulness"],"version":2},
        "preserved":["five_question_structure","safety_critical_motivation","saliency_limitations","human_explanation_goal"],
        "extension":"Produce the required five-question proposal for local explanations of autonomous-driving decisions. Preserve the source concern that saliency can be misleading. The fourth workstream delivers a causal concept/counterfactual protocol after the initial proposal. Integrate scene concepts such as traffic lights, pedestrians, lane markings, vehicle distance and lateral space; specify interventions, datasets, fidelity/stability/human metrics, ablations, and expected outcomes.",
        "provenance":"autonomous-driving local explanation research task","behavior_flag":"USE_RETURNED_RESEARCH_AUTHORITY = True","preserve_flag":"PRESERVE_FIVE_QUESTION_STRUCTURE = True",
        "requirements":["Preserve the safety-critical need for understandable local driving explanations.","Contrast causal concept/counterfactual explanations with misleading saliency maps.","Specify driving scenes, interventions, fidelity, stability, human-usefulness metrics, and ablations.","Integrate the delayed causal explanation protocol and verify the final five-question proposal."],
        "before":"A local-explanation proposal identifies saliency failures but lacks a causal intervention and human-evaluation protocol.","after":"The returned protocol binds concept interventions, counterfactual validity, stability, and human usefulness to the proposal.",
        "semantic_labels":{"output_schema":"The result has exactly five questions and a driving_explanation_research_closure.","task_behavior":"The proposal tests causal concepts and counterfactual scenes rather than relying on saliency, with driving-specific data and fidelity, stability, and human metrics.","preservation":"Preserves safety-critical trust, liability, misleading-saliency evidence, and human-understandability goals.","event_closure":"The delayed causal protocol revises method and evaluation while retaining the source motivation."},
    },
    "mab-late-constraint-13dc7627a3": {
        "source_id":"research:044","benchmark":"research","prefix":"mab_research44_sequence","domain":"streaming_sequence_architectures","class_name":"ResearchProposal","scenario_class":"live_eventful","theme":"task_scope_or_dependency_change","event":"streaming_latency_memory_scope_added","event_id":"evt.mab_late_constraint_13dc.streaming_budget_scope_added","artifact":"streaming_tcn_rnn_research_closure",
        "meaning":"A late streaming latency and memory requirement expands the TCN-versus-RNN comparison without discarding sequence accuracy, receptive-field, or long-memory evaluation.",
        "authority":{"contract":"streaming_sequence_budget_v2","benchmark_dimensions":["accuracy","latency","peak_memory","effective_history"],"version":2},
        "preserved":["five_question_structure","tcn_rnn_comparison","sequence_task_breadth","long_memory_motivation"],
        "extension":"Produce the required five-question proposal building on the broad TCN-versus-RNN sequence comparison. Three workstreams preserve recurrent baselines, temporal convolutional receptive fields, and diverse sequence tasks. A fourth evaluator-owned scope delta adds streaming latency, peak-memory, and effective-history budgets. Selectively revise the proposal with streaming data, accuracy/latency/memory metrics, controlled receptive-field ablations, and expected trade-offs.",
        "provenance":"TCN versus recurrent sequence-modeling research task","behavior_flag":"USE_RETURNED_RESEARCH_AUTHORITY = True","preserve_flag":"PRESERVE_FIVE_QUESTION_STRUCTURE = True",
        "requirements":["Preserve the broad empirical comparison between TCN, LSTM, and GRU sequence models.","Formulate a streaming sequence-modeling question and explain importance, hardness, and prior gaps.","Specify music, language, and synthetic long-memory tasks with accuracy and receptive-field ablations.","Integrate the late latency, memory, and effective-history scope without dropping existing comparisons."],
        "before":"The proposal compares TCNs and recurrent models offline but has no streaming latency, peak-memory, or effective-history constraint.","after":"The scope-expanded proposal measures accuracy together with streaming latency, memory, and history under controlled architecture ablations.",
        "semantic_labels":{"output_schema":"The result has exactly five questions and a streaming_tcn_rnn_research_closure.","task_behavior":"The method compares TCN, LSTM, and GRU on music, language, and stress tests under accuracy, latency, memory, and effective-history budgets.","preservation":"Preserves recurrent home-turf tasks, temporal convolutional receptive-field analysis, and long-memory motivation.","event_closure":"The new streaming scope selectively augments the experimental plan and retains all unaffected comparisons."},
    },
    "mab-late-constraint-79372889b3": {
        "source_id":"research:056","benchmark":"research","prefix":"mab_research56_magvit","domain":"open_lookup_free_visual_tokenizer","class_name":"ResearchProposal","scenario_class":"live_eventful","theme":"task_scope_or_dependency_change","event":"codebook_efficiency_scope_added","event_id":"evt.mab_late_constraint_7937.codebook_efficiency_scope_added","artifact":"open_magvit_tokenizer_research_closure",
        "meaning":"A late codebook-efficiency and low-memory scope extends the open lookup-free tokenizer proposal while preserving reconstruction, autoregressive scaling, and asymmetric factorization goals.",
        "authority":{"contract":"open_magvit_efficiency_benchmark_v2","benchmark_dimensions":["rfid","codebook_utilization","generation_fid","throughput_memory"],"version":2},
        "preserved":["five_question_structure","lookup_free_quantization","asymmetric_token_factorization","autoregressive_scaling_plan"],
        "extension":"Produce the required five-question proposal for open lookup-free visual tokenization and autoregressive image generation. Preserve reconstruction quality, super-large codebook utilization, asymmetric token factorization, and next-sub-token prediction. A late evaluator-owned scope adds low-memory throughput and utilization evaluation. Integrate ImageNet protocols, rFID/FID/utilization/throughput/memory metrics, factorization and codebook ablations, and expected scaling outcomes.",
        "provenance":"Open-MAGVIT2 lookup-free tokenizer research task","behavior_flag":"USE_RETURNED_RESEARCH_AUTHORITY = True","preserve_flag":"PRESERVE_FIVE_QUESTION_STRUCTURE = True",
        "requirements":["Preserve lookup-free quantization, reconstruction quality, and open tokenizer replication goals.","Preserve asymmetric token factorization and next-sub-token autoregressive generation.","Specify ImageNet data, rFID, FID, codebook utilization, scaling, and ablation protocols.","Integrate the late throughput and peak-memory scope without dropping reconstruction or generation evaluation."],
        "before":"The proposal covers reconstruction and generation quality but omits codebook-efficiency, throughput, and peak-memory constraints.","after":"The scope-expanded proposal jointly evaluates rFID, generation FID, utilization, throughput, memory, and scaling.",
        "semantic_labels":{"output_schema":"The result has exactly five questions and an open_magvit_tokenizer_research_closure.","task_behavior":"The method binds lookup-free quantization, asymmetric factorization, next-sub-token prediction, ImageNet, rFID/FID, utilization, throughput, memory, and ablations.","preservation":"Preserves open replication, reconstruction quality, super-large codebooks, and autoregressive scaling.","event_closure":"The efficiency scope augments evaluation without erasing tokenizer or generation objectives."},
    },
    "mab-dependency-unblock-ed6082b496": {
        "source_id":"coding:001","benchmark":"coding","prefix":"mab_code01_culture","domain":"cultural_exchange_hub","class_name":"CulturalExchangeHub","scenario_class":"result_eventful","theme":"delayed_authoritative_result","event":"module_dependency_contract_completed","event_id":"evt.mab_dependency_unblock_ed60.module_dependency_contract_completed","artifact":"cultural_exchange_dependency_closure",
        "meaning":"A delayed module dependency contract unblocks virtual tours, language exchange, workshops, and feedback in the required order while preserving profiles and completed learning activity.",
        "authority":{"contract":"cultural_exchange_dependency_v2","order":["profiles","virtual_tours","language_exchange","workshops","feedback"],"translation_required":True,"rating_requires_experience":True},
        "preserved":["user_profiles","tour_progress","language_sessions","workshop_discussions"],
        "extension":"Build CulturalExchangeHub with profiles and cultural interests, interactive tour hotspots and audio, paired language practice with translation, live or recorded workshops, discussions, and experience ratings. Three workstreams establish profiles, tours, and learning state. A fourth evaluator-owned dependency contract arrives later. Enforce the source-required module order, translation and experience prerequisites, preserve completed activity, and close the end-to-end learning flow.",
        "provenance":"CulturalExchangeHub","behavior_flag":"ENFORCE_MODULE_DEPENDENCIES = True","preserve_flag":"PRESERVE_CULTURAL_ACTIVITY = True",
        "requirements":["Implement profiles with cultural background, interests, and profile image metadata.","Implement interactive virtual tours with hotspots and audio guides after profiles.","Implement paired language exchange, translation, workshops, questions, and discussions in dependency order.","Integrate feedback ratings only after valid experiences and reverify the full module chain."],
        "before":"Profiles and provisional learning modules exist, but the authoritative dependency and experience-gating contract has not arrived.","after":"Tours, language sessions, workshops, and feedback follow the returned order and preserve completed cultural activity.",
        "semantic_labels":{"output_schema":"solution.py exposes CulturalExchangeHub and the cultural_exchange_dependency_closure.","task_behavior":"Profiles unlock tours, tours unlock translated language exchange, language unlocks workshops, and only completed experiences can be rated.","preservation":"Preserves profile backgrounds/interests, tour progress, language sessions, workshop questions, and discussions.","event_closure":"The delayed dependency contract closes the full profile-to-feedback workflow without resetting prior activity."},
        "canonical": r'''DOMAIN='cultural_exchange_hub'
EVENT_SCHEMA='cultural_exchange_dependency_v2'
ENFORCE_MODULE_DEPENDENCIES = True
PRESERVE_CULTURAL_ACTIVITY = True
class CulturalExchangeHub:
 def __init__(self): self.profiles={}; self.tours={}; self.tour_visits=[]; self.language_sessions=[]; self.workshops={}; self.discussions=[]; self.ratings=[]; self.contract=None
 def apply_dependency_contract(self,contract):
  if contract.get('order')!=['profiles','virtual_tours','language_exchange','workshops','feedback']: raise ValueError('invalid module order')
  self.contract=dict(contract); return self.contract
 def register(self,user_id,background,interests,profile_picture):
  if not all([user_id,background,interests,profile_picture]): raise ValueError('complete profile required')
  self.profiles[user_id]={'background':background,'interests':list(interests),'profile_picture':profile_picture}; return self.profiles[user_id]
 def add_tour(self,tour_id,landmark,hotspots,audio_guide): self.tours[tour_id]={'landmark':landmark,'hotspots':dict(hotspots),'audio_guide':audio_guide}
 def visit_tour(self,user_id,tour_id,hotspot):
  if ENFORCE_MODULE_DEPENDENCIES and (not self.contract or user_id not in self.profiles): raise RuntimeError('profile dependency unresolved')
  info=self.tours[tour_id]['hotspots'][hotspot]
  if PRESERVE_CULTURAL_ACTIVITY:self.tour_visits.append((user_id,tour_id,hotspot))
  return {'info':info,'audio':self.tours[tour_id]['audio_guide']}
 def language_exchange(self,a,b,language,text):
  if ENFORCE_MODULE_DEPENDENCIES and not any(v[0] in {a,b} for v in self.tour_visits): raise RuntimeError('tour dependency unresolved')
  translated=f'[{language}] {text}'; row={'users':tuple(sorted((a,b))),'language':language,'text':text,'translation':translated}
  if PRESERVE_CULTURAL_ACTIVITY:self.language_sessions.append(row)
  return row
 def add_workshop(self,workshop_id,expert,mode):
  if mode not in {'live','recorded'}: raise ValueError('invalid mode')
  self.workshops[workshop_id]={'expert':expert,'mode':mode,'participants':set(),'questions':[]}
 def join_workshop(self,user_id,workshop_id,question=None):
  if ENFORCE_MODULE_DEPENDENCIES and not any(user_id in s['users'] for s in self.language_sessions): raise RuntimeError('language dependency unresolved')
  w=self.workshops[workshop_id]; w['participants'].add(user_id)
  if question:w['questions'].append((user_id,question)); self.discussions.append((workshop_id,user_id,question))
 def rate(self,user_id,module_id,score,review):
  experienced=any(v[0]==user_id and v[1]==module_id for v in self.tour_visits) or (module_id in self.workshops and user_id in self.workshops[module_id]['participants'])
  if ENFORCE_MODULE_DEPENDENCIES and (not experienced or not 1<=score<=5): raise PermissionError('completed experience required')
  row={'user':user_id,'module':module_id,'score':score,'review':review}; self.ratings.append(row); return row
''',
        "tests": r'''from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); CONTRACT={'order':['profiles','virtual_tours','language_exchange','workshops','feedback'],'translation_required':True,'rating_requires_experience':True}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('culture_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_culture_output_schema_profiles_tours_and_artifacts():
 m=load_solution(); h=m.CulturalExchangeHub(); assert m.DOMAIN=='cultural_exchange_hub'; h.apply_dependency_contract(CONTRACT); h.register('ana','Peru',['music'],'ana.png'); h.add_tour('machu','Machu Picchu',{'gate':'History'},'audio-es'); assert h.visit_tour('ana','machu','gate')=={'info':'History','audio':'audio-es'}; r,c=docs(); assert c['artifact_type']=='cultural_exchange_dependency_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_culture_dependency_order_translation_workshop_and_rating_behavior():
 m=load_solution(); h=m.CulturalExchangeHub(); h.apply_dependency_contract(CONTRACT); h.register('a','Peru',['food'],'a.png'); h.register('b','Japan',['language'],'b.png'); h.add_tour('t','Temple',{'h':'Heritage'},'guide'); h.add_workshop('w','expert','live')
 for call in [lambda:h.language_exchange('a','b','ja','hello'),lambda:h.join_workshop('a','w'),lambda:h.rate('a','w',5,'great')]:
  try:call()
  except (RuntimeError,PermissionError):pass
  else:raise AssertionError('dependency bypassed')
 h.visit_tour('a','t','h'); session=h.language_exchange('a','b','ja','hello'); h.join_workshop('a','w','How is it made?'); assert session['translation']=='[ja] hello' and h.rate('a','w',5,'great')['score']==5
def test_culture_profiles_learning_activity_and_discussions_are_preserved():
 m=load_solution(); h=m.CulturalExchangeHub(); h.apply_dependency_contract(CONTRACT); h.register('a','Ghana',['art'],'a.png'); h.register('b','Italy',['art'],'b.png'); h.add_tour('t','Gallery',{'x':'Artifact'},'audio'); h.visit_tour('a','t','x'); h.language_exchange('a','b','it','ciao'); h.add_workshop('w','curator','recorded'); h.join_workshop('a','w','Materials?'); assert h.profiles['a']['background']=='Ghana' and h.tour_visits and h.language_sessions and h.discussions==[('w','a','Materials?')]
def test_culture_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='cultural_exchange_dependency_v2' and r['authority']['order']==['profiles','virtual_tours','language_exchange','workshops','feedback'] and r['authority']['translation_required'] is True; assert c['upstream_depth']==4 and c['preserved_workflows']==['user_profiles','tour_progress','language_sessions','workshop_discussions']
''',
    },
    "mab-dependency-unblock-fe0736601e": {
        "source_id":"coding:003","benchmark":"coding","prefix":"mab_code03_schedule","domain":"collaborative_schedule_planner","class_name":"CollaborativeSchedulePlanner","scenario_class":"result_eventful","theme":"partial_then_complete_result","event":"optimizer_constraints_completed","event_id":"evt.mab_dependency_unblock_fe07.optimizer_constraints_completed","artifact":"team_schedule_optimizer_closure",
        "meaning":"A completed availability, dependency, and preference contract replaces provisional priority-only scheduling while preserving tasks, feedback, notifications, and report history.",
        "authority":{"contract":"team_schedule_optimizer_v2","constraints":["availability","task_dependencies","no_overlap","priority","feedback"],"slot_minutes":30},
        "preserved":["user_tasks","team_feedback","change_notifications","gantt_and_usage_reports"],
        "extension":"Build CollaborativeSchedulePlanner with users, tasks, duration, priority and dependencies, shared availability, collaborative edits, notifications, adaptive feedback, and Gantt/time-usage reports. Three workstreams create task and collaboration state with a provisional priority schedule. The fourth returns the complete optimizer contract. Replace only affected slot selection, enforce dependency and no-overlap constraints, preserve edits and feedback, and reverify reports.",
        "provenance":"CollaborativeSchedulePlanner","behavior_flag":"USE_COMPLETE_OPTIMIZER = True","preserve_flag":"PRESERVE_SCHEDULE_HISTORY = True",
        "requirements":["Implement users, tasks, duration, priority, dependencies, and availability.","Implement collaborative edits and notifications for schedule changes.","Implement feedback-driven priority adjustment and deterministic no-overlap optimization.","Integrate the completed optimizer contract and generate Gantt and time-usage reports."],
        "before":"A provisional schedule uses task priority but does not yet enforce shared availability, dependencies, and non-overlap together.","after":"The complete optimizer contract produces a dependency-valid, availability-bound schedule and preserves collaboration evidence.",
        "semantic_labels":{"output_schema":"solution.py exposes CollaborativeSchedulePlanner and the team_schedule_optimizer_closure.","task_behavior":"Scheduling is deterministic, dependency ordered, availability bound, non-overlapping, priority aware, and responsive to feedback.","preservation":"Preserves user tasks, team feedback, change notifications, and generated report history.","event_closure":"The complete optimizer replaces provisional slots and revalidates Gantt and usage reports."},
        "canonical": r'''DOMAIN='collaborative_schedule_planner'
EVENT_SCHEMA='team_schedule_optimizer_v2'
USE_COMPLETE_OPTIMIZER = True
PRESERVE_SCHEDULE_HISTORY = True
class CollaborativeSchedulePlanner:
 def __init__(self): self.users={}; self.tasks={}; self.availability={}; self.feedback=[]; self.notifications=[]; self.schedules={}; self.reports=[]; self.contract=None
 def add_user(self,user_id,available_slots): self.users[user_id]={}; self.availability[user_id]=list(available_slots)
 def add_task(self,task_id,owner,name,duration,priority,dependencies=()):
  if owner not in self.users or duration<=0 or priority<1: raise ValueError('invalid task')
  self.tasks[task_id]={'owner':owner,'name':name,'duration':int(duration),'priority':int(priority),'dependencies':list(dependencies)}; return self.tasks[task_id]
 def apply_optimizer_contract(self,contract):
  if set(contract.get('constraints',[]))!={'availability','task_dependencies','no_overlap','priority','feedback'}: raise ValueError('incomplete optimizer')
  self.contract=dict(contract); return self.contract
 def edit_task(self,actor,task_id,**changes):
  self.tasks[task_id].update(changes)
  if PRESERVE_SCHEDULE_HISTORY:self.notifications.append({'actor':actor,'task_id':task_id,'changes':sorted(changes)})
 def provide_feedback(self,user_id,task_id,delta):
  self.tasks[task_id]['priority']=max(1,self.tasks[task_id]['priority']+int(delta)); row={'user':user_id,'task':task_id,'delta':int(delta)}
  if PRESERVE_SCHEDULE_HISTORY:self.feedback.append(row)
  return row
 def _topological(self):
  pending=set(self.tasks); done=[]
  while pending:
   ready=[t for t in pending if set(self.tasks[t]['dependencies'])<=set(done)]
   if not ready: raise ValueError('dependency cycle')
   ready.sort(key=lambda t:(-self.tasks[t]['priority'],t)); done.extend(ready); pending-=set(ready)
  return done
 def optimize(self):
  if USE_COMPLETE_OPTIMIZER and not self.contract: raise RuntimeError('optimizer incomplete')
  occupied={u:set() for u in self.users}; schedule={}
  for tid in self._topological():
   t=self.tasks[tid]; slots=sorted(self.availability[t['owner']]); needed=(t['duration']+29)//30; start=None
   for i in range(len(slots)-needed+1):
    block=slots[i:i+needed]
    if block==list(range(block[0],block[0]+needed)) and not occupied[t['owner']].intersection(block): start=block; break
   if start is None: raise RuntimeError('no feasible slot')
   schedule[tid]={'owner':t['owner'],'start_slot':start[0],'end_slot':start[-1]+1,'priority':t['priority']}; occupied[t['owner']].update(start)
  self.schedules=schedule; return schedule
 def report(self):
  rows=[{'task_id':t,**v} for t,v in sorted(self.schedules.items(),key=lambda x:x[1]['start_slot'])]; usage={u:sum(v['end_slot']-v['start_slot'] for v in self.schedules.values() if v['owner']==u)*30 for u in self.users}; report={'gantt':rows,'minutes_by_user':usage}
  if PRESERVE_SCHEDULE_HISTORY:self.reports.append(report)
  return report
''',
        "tests": r'''from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); CONTRACT={'constraints':['availability','task_dependencies','no_overlap','priority','feedback'],'slot_minutes':30}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('schedule_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_schedule_output_schema_tasks_and_artifacts():
 m=load_solution(); p=m.CollaborativeSchedulePlanner(); assert m.DOMAIN=='collaborative_schedule_planner'; p.add_user('a',[0,1,2]); p.add_task('t','a','Plan',30,2); p.apply_optimizer_contract(CONTRACT); assert p.optimize()['t']['start_slot']==0; r,c=docs(); assert c['artifact_type']=='team_schedule_optimizer_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_schedule_dependencies_availability_non_overlap_priority_and_feedback():
 m=load_solution(); p=m.CollaborativeSchedulePlanner(); p.add_user('a',[0,1,2,3]); p.add_task('base','a','Base',60,1); p.add_task('urgent','a','Urgent',30,3,['base']); p.add_task('other','a','Other',30,2); p.apply_optimizer_contract(CONTRACT); p.provide_feedback('a','other',2); s=p.optimize(); assert s['base']['end_slot']<=s['urgent']['start_slot'] and len({x for v in s.values() for x in range(v['start_slot'],v['end_slot'])})==4 and s['other']['priority']==4
def test_schedule_edits_feedback_notifications_and_reports_are_preserved():
 m=load_solution(); p=m.CollaborativeSchedulePlanner(); p.add_user('a',[0,1,2]); p.add_task('t','a','Draft',30,1); p.edit_task('a','t',name='Final'); p.provide_feedback('a','t',2); p.apply_optimizer_contract(CONTRACT); p.optimize(); report=p.report(); assert p.tasks['t']['name']=='Final' and p.notifications[0]['changes']==['name'] and p.feedback[0]['delta']==2 and report['minutes_by_user']=={'a':30} and p.reports==[report]
def test_schedule_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='team_schedule_optimizer_v2' and set(r['authority']['constraints'])=={'availability','task_dependencies','no_overlap','priority','feedback'} and r['authority']['slot_minutes']==30; assert c['upstream_depth']==4 and c['preserved_workflows']==['user_tasks','team_feedback','change_notifications','gantt_and_usage_reports']
''',
    },
    "mab-late-test-evidence-60efb2bdee": {
        "source_id":"coding:005","benchmark":"coding","prefix":"mab_code05_officesched","domain":"office_task_scheduler","class_name":"OfficeTaskScheduler","scenario_class":"result_eventful","theme":"duplicate_or_replayed_completion","event":"office_edge_test_evidence_replayed","event_id":"evt.mab_late_test_evidence_60ef.office_edge_tests_replayed","artifact":"office_scheduler_test_evidence_closure",
        "meaning":"Returned authorization, deadline, assignment, notification, and reporting edge tests are applied exactly once when completion is replayed, while tasks, comments, and audit history remain intact.",
        "authority":{"contract":"office_scheduler_edge_tests_v2","evidence_id":"office-edge-suite-2026-08","cases":["nonexistent_assignee","past_deadline","unauthorized_task_access","overdue_report"]},
        "preserved":["task_assignments","status_history","task_comments","notification_and_report_history"],
        "extension":"Build OfficeTaskScheduler with users, task creation and assignment, deadlines, priorities, dashboards, notifications, status changes, comments, and reports. Three workstreams establish task and reporting behavior. A fourth evaluator-owned edge-test completion may be replayed. Deduplicate it by evidence identity, enforce nonexistent-user, past-deadline and unauthorized-access cases, preserve valid task state, and reverify overdue and completion reports.",
        "provenance":"OfficeTaskScheduler","behavior_flag":"APPLY_UNIQUE_EDGE_TESTS = True","preserve_flag":"PRESERVE_OFFICE_TASK_HISTORY = True",
        "requirements":["Implement users, task creation, assignment, deadline, priority, and dashboard views.","Implement authorized status updates, comments, assignment and deadline notifications.","Implement completion-rate, overdue, and task-distribution reports.","Deduplicate and integrate returned edge tests, then reverify affected task behavior."],
        "before":"Core scheduling works, but task-specific edge tests arrive late and the same completion can be replayed.","after":"The edge suite is registered once, invalid assignment/deadline/access behavior is rejected, and reports are reverified without duplicate effects.",
        "semantic_labels":{"output_schema":"solution.py exposes OfficeTaskScheduler and the office_scheduler_test_evidence_closure.","task_behavior":"Nonexistent assignees, past deadlines, unauthorized access, status transitions, notifications, and overdue reports follow task-specific rules; replay is idempotent.","preservation":"Preserves valid assignments, status history, comments, notifications, and report history.","event_closure":"The edge-test receipt and evidence identity are consumed once and bound to final report verification."},
        "canonical": r'''DOMAIN='office_task_scheduler'
EVENT_SCHEMA='office_scheduler_edge_tests_v2'
APPLY_UNIQUE_EDGE_TESTS = True
PRESERVE_OFFICE_TASK_HISTORY = True
class OfficeTaskScheduler:
 def __init__(self,now=100): self.now=now; self.users={}; self.tasks={}; self.comments=[]; self.notifications=[]; self.history=[]; self.reports=[]; self.evidence_ids=set(); self.evidence_application_count=0
 def add_user(self,user_id,role='member'):
  if not user_id: raise ValueError('user required')
  self.users[user_id]={'role':role}
 def apply_test_evidence(self,evidence_id,cases):
  if APPLY_UNIQUE_EDGE_TESTS and evidence_id in self.evidence_ids:return {'status':'duplicate','applied':0}
  self.evidence_ids.add(evidence_id); self.evidence_application_count+=1; return {'status':'applied','applied':len(cases)}
 def create_task(self,actor,task_id,title,assignee,deadline,priority):
  if actor not in self.users or assignee not in self.users: raise KeyError('unknown user')
  if deadline<=self.now: raise ValueError('deadline must be future')
  if priority not in {'low','medium','high'}: raise ValueError('priority')
  self.tasks[task_id]={'title':title,'creator':actor,'assignee':assignee,'deadline':deadline,'priority':priority,'status':'pending'}; self.notifications.append({'user':assignee,'kind':'assignment','task':task_id}); self._record('create',actor,task_id); return self.tasks[task_id]
 def _record(self,action,actor,task_id):
  if PRESERVE_OFFICE_TASK_HISTORY:self.history.append({'action':action,'actor':actor,'task':task_id})
 def dashboard(self,user_id): return [dict(task_id=k,**v) for k,v in self.tasks.items() if v['assignee']==user_id or v['creator']==user_id]
 def update_status(self,actor,task_id,status):
  t=self.tasks[task_id]
  if actor not in {t['assignee'],t['creator']} and self.users[actor]['role']!='manager': raise PermissionError('unauthorized task access')
  if status not in {'pending','in_progress','completed'}: raise ValueError('status')
  t['status']=status; self._record('status:'+status,actor,task_id); return status
 def add_comment(self,actor,task_id,text):
  t=self.tasks[task_id]
  if actor not in {t['assignee'],t['creator']} and self.users[actor]['role']!='manager': raise PermissionError('unauthorized task access')
  row={'actor':actor,'task':task_id,'text':text}; self.comments.append(row); self._record('comment',actor,task_id); return row
 def deadline_notifications(self,now,window=10):
  rows=[]
  for tid,t in self.tasks.items():
   if t['status']!='completed' and 0<=t['deadline']-now<=window: rows.append({'user':t['assignee'],'kind':'deadline','task':tid})
  self.notifications.extend(rows); return rows
 def report(self,now):
  total=len(self.tasks); done=sum(t['status']=='completed' for t in self.tasks.values()); overdue=[k for k,t in self.tasks.items() if t['deadline']<now and t['status']!='completed']; distribution={u:sum(t['assignee']==u for t in self.tasks.values()) for u in self.users}; r={'completion_rate':done/total if total else 0.0,'overdue':overdue,'distribution':distribution}
  if PRESERVE_OFFICE_TASK_HISTORY:self.reports.append(r)
  return r
''',
        "tests": r'''from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); CASES=['nonexistent_assignee','past_deadline','unauthorized_task_access','overdue_report']
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('office_sched_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_office_scheduler_output_schema_dashboard_and_artifacts():
 m=load_solution(); s=m.OfficeTaskScheduler(); assert m.DOMAIN=='office_task_scheduler'; s.add_user('a'); s.add_user('b'); s.create_task('a','t','Review','b',120,'high'); assert s.dashboard('b')[0]['task_id']=='t'; r,c=docs(); assert c['artifact_type']=='office_scheduler_test_evidence_closure' and c['event_receipt_sha256']==r['receipt_sha256']
def test_office_scheduler_edge_cases_and_replay_are_idempotent():
 m=load_solution(); s=m.OfficeTaskScheduler(); s.add_user('a'); s.add_user('b'); s.add_user('x'); first=s.apply_test_evidence('office-edge-suite-2026-08',CASES); replay=s.apply_test_evidence('office-edge-suite-2026-08',CASES); assert first['applied']==4 and replay=={'status':'duplicate','applied':0} and s.evidence_application_count==1
 for call,exc in [(lambda:s.create_task('a','x','Bad','missing',120,'low'),KeyError),(lambda:s.create_task('a','x','Bad','b',99,'low'),ValueError)]:
  try:call()
  except exc:pass
  else:raise AssertionError('edge case accepted')
 s.create_task('a','t','Valid','b',110,'high')
 try:s.update_status('x','t','completed')
 except PermissionError:pass
 else:raise AssertionError('unauthorized access accepted')
def test_office_scheduler_status_comments_notifications_and_reports_are_preserved():
 m=load_solution(); s=m.OfficeTaskScheduler(); s.add_user('a'); s.add_user('b'); s.create_task('a','t','Valid','b',110,'medium'); s.update_status('b','t','in_progress'); s.add_comment('b','t','working'); assert s.deadline_notifications(105)==[{'user':'b','kind':'deadline','task':'t'}]; report=s.report(111); assert report['overdue']==['t'] and report['distribution']['b']==1 and s.comments[0]['text']=='working' and len(s.history)==3 and s.reports==[report]
def test_office_scheduler_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='office_scheduler_edge_tests_v2' and r['authority']['evidence_id']=='office-edge-suite-2026-08' and set(r['authority']['cases'])==set(CASES); assert c['upstream_depth']==4 and c['preserved_workflows']==['task_assignments','status_history','task_comments','notification_and_report_history']
''',
    },
    "mab-dependency-unblock-fa3ee479d7": {
        "source_id":"coding:007","benchmark":"coding","prefix":"mab_code07_craft","domain":"collaborate_craft","class_name":"CollaborateCraft","scenario_class":"result_eventful","theme":"delayed_authoritative_result","event":"group_integrity_contract_completed","event_id":"evt.mab_dependency_unblock_fa3e.group_integrity_contract_completed","artifact":"craft_group_integrity_closure",
        "meaning":"A delayed media, leadership, membership, and task-integrity contract unblocks collaborative craft projects while preserving profiles, posts, feedback, messages, and search state.",
        "authority":{"contract":"craft_group_integrity_v2","media_types":["image/jpeg","image/png","video/mp4"],"leader_only":["invite","assign_task"],"comment_votes":[-1,1]},
        "preserved":["user_profiles","craft_posts_and_tags","comments_and_votes","private_and_group_messages"],
        "extension":"Build CollaborateCraft with profiles, validated photo/video project posts and tags, leader-managed group projects, invitations, assignments and progress, comments with votes, private/group messaging, and search. Three workstreams establish social and project state. A fourth evaluator-owned integrity contract arrives later. Enforce media types, membership and leader-only actions, preserve valid community content, and reverify search and project consistency.",
        "provenance":"CollaborateCraft crafting community","behavior_flag":"ENFORCE_GROUP_INTEGRITY = True","preserve_flag":"PRESERVE_CRAFT_COMMUNITY = True",
        "requirements":["Implement profiles and validated craft project posts with media and tags.","Implement leader-managed group membership, task assignment, and progress tracking.","Implement comments, helpfulness votes, private/group messages, and keyword/tag/profile search.","Integrate the delayed media and group-integrity contract and reverify consistency."],
        "before":"Profiles, posts, and provisional groups exist without authoritative media-type, membership, and leader-only mutation rules.","after":"The returned contract governs media and group changes while preserving valid posts, feedback, messaging, and search results.",
        "semantic_labels":{"output_schema":"solution.py exposes CollaborateCraft and the craft_group_integrity_closure.","task_behavior":"Media validation, leader-only invitations/assignments, member comments/messages, progress, voting, and search obey the returned integrity contract.","preservation":"Preserves profiles, tagged posts, group state, comments and votes, private and group messages.","event_closure":"The delayed integrity authority unblocks safe group collaboration and revalidates search without erasing content."},
        "canonical": r'''DOMAIN='collaborate_craft'
EVENT_SCHEMA='craft_group_integrity_v2'
ENFORCE_GROUP_INTEGRITY = True
PRESERVE_CRAFT_COMMUNITY = True
class CollaborateCraft:
 def __init__(self): self.profiles={}; self.posts={}; self.groups={}; self.comments={}; self.messages=[]; self.contract=None
 def apply_integrity_contract(self,contract):
  if set(contract.get('leader_only',[]))!={'invite','assign_task'}: raise ValueError('invalid integrity contract')
  self.contract=dict(contract); return self.contract
 def create_profile(self,user,bio,picture):
  if not all([user,bio,picture]): raise ValueError('profile fields required')
  self.profiles[user]={'bio':bio,'picture':picture}; return self.profiles[user]
 def post_project(self,post_id,user,media_type,media,description,tags):
  if ENFORCE_GROUP_INTEGRITY and (not self.contract or media_type not in self.contract['media_types']): raise ValueError('invalid media')
  if user not in self.profiles or not description or not tags: raise ValueError('invalid post')
  self.posts[post_id]={'user':user,'media_type':media_type,'media':media,'description':description,'tags':set(tags)}; return self.posts[post_id]
 def create_group(self,group_id,leader,title):
  if leader not in self.profiles: raise KeyError(leader)
  self.groups[group_id]={'leader':leader,'title':title,'members':{leader},'tasks':{},'progress':0}; return self.groups[group_id]
 def invite(self,actor,group_id,user):
  g=self.groups[group_id]
  if ENFORCE_GROUP_INTEGRITY and actor!=g['leader']: raise PermissionError('leader required')
  if user not in self.profiles: raise KeyError(user)
  g['members'].add(user)
 def assign_task(self,actor,group_id,task_id,assignee):
  g=self.groups[group_id]
  if ENFORCE_GROUP_INTEGRITY and (actor!=g['leader'] or assignee not in g['members']): raise PermissionError('leader/member required')
  g['tasks'][task_id]={'assignee':assignee,'done':False}
 def complete_task(self,user,group_id,task_id):
  t=self.groups[group_id]['tasks'][task_id]
  if t['assignee']!=user: raise PermissionError('wrong assignee')
  t['done']=True; g=self.groups[group_id]; g['progress']=round(sum(x['done'] for x in g['tasks'].values())/len(g['tasks']),3); return g['progress']
 def comment(self,user,target,text):
  if user not in self.profiles or not text: raise ValueError('invalid comment')
  cid=f'c{len(self.comments)+1}'; self.comments[cid]={'user':user,'target':target,'text':text,'score':0}; return cid
 def vote(self,user,comment_id,value):
  if ENFORCE_GROUP_INTEGRITY and value not in self.contract['comment_votes']: raise ValueError('vote must be -1 or 1')
  self.comments[comment_id]['score']+=value; return self.comments[comment_id]['score']
 def message(self,sender,recipient,text,group=False):
  if group and sender not in self.groups[recipient]['members']: raise PermissionError('not group member')
  if not group and recipient not in self.profiles: raise KeyError(recipient)
  row={'sender':sender,'recipient':recipient,'text':text,'group':group}; self.messages.append(row); return row
 def search(self,query):
  q=query.lower(); users=[u for u,p in self.profiles.items() if q in u.lower() or q in p['bio'].lower()]; posts=[k for k,p in self.posts.items() if q in p['description'].lower() or any(q in t.lower() for t in p['tags'])]; groups=[k for k,g in self.groups.items() if q in g['title'].lower()]; return {'users':sorted(users),'posts':sorted(posts),'groups':sorted(groups)}
''',
        "tests": r'''from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data'); CONTRACT={'media_types':['image/jpeg','image/png','video/mp4'],'leader_only':['invite','assign_task'],'comment_votes':[-1,1]}
def load_solution():
 p=OUT/'solution.py'; s=importlib.util.spec_from_file_location('craft_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def test_craft_output_schema_profiles_posts_and_artifacts():
 m=load_solution(); c=m.CollaborateCraft(); assert m.DOMAIN=='collaborate_craft'; c.apply_integrity_contract(CONTRACT); c.create_profile('ana','knitter','a.png'); c.post_project('p','ana','image/png','scarf.png','Blue scarf',['knitting']); assert c.search('knitting')['posts']==['p']; r,x=docs(); assert x['artifact_type']=='craft_group_integrity_closure' and x['event_receipt_sha256']==r['receipt_sha256']
def test_craft_media_leadership_membership_assignment_and_progress_behavior():
 m=load_solution(); c=m.CollaborateCraft(); c.apply_integrity_contract(CONTRACT); c.create_profile('lead','woodworker','l.png'); c.create_profile('member','painter','m.png'); c.create_group('g','lead','Community bench')
 for call in [lambda:c.post_project('bad','lead','application/exe','x','bad',['x']),lambda:c.invite('member','g','member')]:
  try:call()
  except (ValueError,PermissionError):pass
  else:raise AssertionError('integrity bypassed')
 c.invite('lead','g','member'); c.assign_task('lead','g','paint','member'); assert c.complete_task('member','g','paint')==1.0
def test_craft_comments_votes_messages_and_search_are_preserved():
 m=load_solution(); c=m.CollaborateCraft(); c.apply_integrity_contract(CONTRACT); c.create_profile('a','knitting fan','a.png'); c.create_profile('b','woodworking fan','b.png'); c.post_project('p','a','image/jpeg','x.jpg','Warm scarf',['knitting']); c.create_group('g','a','Scarf team'); c.invite('a','g','b'); cid=c.comment('b','p','Helpful pattern'); assert c.vote('a',cid,1)==1; c.message('a','b','hello'); c.message('b','g','ready',True); result=c.search('scarf'); assert result['posts']==['p'] and result['groups']==['g'] and len(c.messages)==2 and c.comments[cid]['score']==1
def test_craft_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='craft_group_integrity_v2' and set(r['authority']['media_types'])=={'image/jpeg','image/png','video/mp4'} and set(r['authority']['leader_only'])=={'invite','assign_task'}; assert c['upstream_depth']==4 and c['preserved_workflows']==['user_profiles','craft_posts_and_tags','comments_and_votes','private_and_group_messages']
''',
    },
}


RUNTIME["mab-dependency-unblock-472d364155"].update({
    "canonical": research_canonical("monocular_expressive_avatar","exavatar_coverage_benchmark_v2","How can a short monocular video produce an expressive whole-body avatar that generalizes to unseen facial expressions, hand poses, body poses, and occluded geometry?","This would democratize animatable avatars for telepresence, entertainment, and interaction without calibrated multi-view or RGBD capture.","A monocular clip has sparse expression and pose coverage, self-occlusion, non-rigid clothing, and ambiguous unseen surfaces, so naive fitting bakes appearance and fails under novel articulation.","Existing casual-video avatars emphasize body motion or require scans and accurate registrations; they do not jointly quantify face, hand, body, and occlusion generalization.","Train an uncertainty-aware SMPL-X-conditioned 3D Gaussian surface model from monocular video, augment expression and hand/body pose coverage, and regularize occluded geometry. Evaluate on held-out people and novel motions with face/hand/body pose strata, rendering PSNR, SSIM and LPIPS, geometry error, identity consistency and runtime; ablate uncertainty, pose augmentation, mesh connectivity, and Gaussian attachment. Expected results improve novel-expression and occlusion rendering without sacrificing real-time animation.",["short monocular video","SMPL-X whole-body control","3D Gaussian splatting","limited expression and pose diversity","occluded geometry ambiguity"]),
    "tests": research_tests("monocular_expressive_avatar","exavatar_coverage_benchmark_v2","monocular_exavatar_research_closure",["monocular","smpl-x","3d gaussian","occlusion","psnr","ssim","lpips","geometry","ablat"],["five_question_structure","monocular_capture_premise","smplx_3dgs_representation","novel_pose_evaluation_plan"],["monocular","smpl-x","3d gaussian","occlusion"]),
})
RUNTIME["mab-dependency-unblock-5585821bdf"].update({
    "canonical": research_canonical("driving_counterfactual_explanations","driving_causal_explanation_protocol_v2","Can causal concept and counterfactual explanations faithfully describe why an autonomous-driving model stops, turns, or overtakes in complex urban scenes?","Faithful local explanations can improve debugging, liability analysis, bias discovery, operator trust, and safe deployment of black-box driving systems.","Traffic actors, lights, lane markings, distance and lateral space are correlated; interventions must remain physically plausible, preserve scene semantics, and separate model causality from human expectation.","Saliency maps can behave like edge detectors and remain insensitive to the model, while prior concept explanations rarely combine causal fidelity, counterfactual validity, stability and human usefulness.","Learn scene concepts for traffic lights, pedestrians, lane markings, front-vehicle distance and lateral clearance, then generate physically plausible counterfactual interventions for BDD100K and nuScenes driving decisions. Measure deletion/intervention fidelity, counterfactual validity, stability, sparsity, simulator safety and expert/user agreement; compare saliency and concept baselines and ablate concept supervision, causal graph and plausibility constraints. Expected results yield more faithful and understandable failure explanations.",["safety-critical autonomous driving","black-box local explanations","saliency maps can be misleading","human trust and liability"]),
    "tests": research_tests("driving_counterfactual_explanations","driving_causal_explanation_protocol_v2","driving_explanation_research_closure",["traffic light","pedestrian","lane","counterfactual","bdd100k","nuscenes","fidelity","stability","human","ablat"],["five_question_structure","safety_critical_motivation","saliency_limitations","human_explanation_goal"],["safety-critical","saliency","human","liability"]),
})
RUNTIME["mab-late-constraint-13dc7627a3"].update({
    "canonical": research_canonical("streaming_sequence_architectures","streaming_sequence_budget_v2","When do temporal convolutional networks outperform LSTM and GRU models under streaming latency, peak-memory, and long-history constraints across sequence tasks?","A controlled answer would replace architecture folklore with deployable accuracy-efficiency guidance for audio, language and long-memory systems.","Receptive field, recurrent state, truncation, batching and hardware kernels couple accuracy, latency and memory, so offline parameter-matched comparisons do not predict streaming behavior.","Prior broad TCN comparisons emphasize accuracy and effective memory but do not jointly control online latency, peak memory, chunk size and history under one protocol.","Compare residual dilated TCN, LSTM and GRU models on polyphonic music, word/character language modeling and synthetic copy/addition stress tests using matched parameters and streaming chunks. Report likelihood or accuracy, p50/p95 latency, peak memory, throughput and effective-history probes; ablate dilation, kernel, recurrent state, truncation and chunk size. Expected results map where TCN parallelism or recurrent state gives the best constrained frontier.",["TCN versus recurrent sequence modeling","polyphonic music and language tasks","synthetic long-memory stress tests","effective receptive field"]),
    "tests": research_tests("streaming_sequence_architectures","streaming_sequence_budget_v2","streaming_tcn_rnn_research_closure",["tcn","lstm","gru","polyphonic","language","latency","peak memory","effective-history","chunk","ablat"],["five_question_structure","tcn_rnn_comparison","sequence_task_breadth","long_memory_motivation"],["tcn","recurrent","sequence","memory"]),
})
RUNTIME["mab-late-constraint-79372889b3"].update({
    "canonical": research_canonical("open_lookup_free_visual_tokenizer","open_magvit_efficiency_benchmark_v2","How can an open lookup-free visual tokenizer and asymmetric sub-token autoregressive model scale codebook capacity while improving reconstruction, generation quality, utilization, throughput, and memory?","An open, efficient tokenizer would remove a closed-source bottleneck and enable reproducible scalable autoregressive image generation.","Super-large binary codebooks create optimization, utilization and vocabulary-prediction challenges; factorization choices trade reconstruction detail against sequence length, throughput and memory.","Existing VQ tokenizers underuse limited codebooks, while the strongest lookup-free tokenizer is closed and prior replications do not jointly study factorization, generation scaling and efficiency.","Reimplement lookup-free quantization and asymmetric token factorization with next-sub-token prediction on ImageNet 128 and 256, scale plain autoregressive transformers, and report rFID, generation FID, codebook utilization, entropy, throughput, peak memory and scaling curves. Compare VQ-VAE, lookup-free and masked-generation baselines; ablate codebook bits, sub-vocabulary split, interaction loss and model size. Expected results retain Open-MAGVIT-level reconstruction while improving open AR quality-efficiency trade-offs.",["lookup-free visual quantization","closed MAGVIT-v2 tokenizer","asymmetric token factorization","next sub-token prediction","autoregressive image generation"]),
    "tests": research_tests("open_lookup_free_visual_tokenizer","open_magvit_efficiency_benchmark_v2","open_magvit_tokenizer_research_closure",["lookup-free","asymmetric","sub-token","imagenet","rfid","fid","utilization","throughput","peak memory","ablat"],["five_question_structure","lookup_free_quantization","asymmetric_token_factorization","autoregressive_scaling_plan"],["lookup-free","codebook","autoregressive","factorization"]),
})


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
    elif cfg["theme"] == "partial_then_complete_result":
        specs = [
            ("classify_completeness", "event_intake", "wait_for_authority", True),
            ("revise_affected", "state_revision", "resolve_authority", False),
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
        "partial_then_complete_result": "Partial evidence remains provisional until the complete result revises affected state and closure is reverified.",
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


def ensure_blueprints(bp_root: Path) -> None:
    """Create missing coding blueprints from their pinned source-native snapshots."""
    workspace = bp_root.parents[2]
    source_root = workspace / "artifacts/source-native-v4/cases/multiagentbench"
    template = bp_root / "mab-dependency-unblock-472d364155"
    for cid in sorted(RAW_SOURCE_CASES):
        dst = bp_root / cid
        if not dst.exists():
            shutil.copytree(
                template,
                dst,
                ignore=shutil.ignore_patterns(
                    "materialize_runtime_batch.py",
                    "strict_batch_config_next8.py",
                    "__pycache__",
                ),
            )
        src = source_root / cid
        mapping = {
            "native_case.json": "01-native_case.json",
            "official_task.json": "03-official_task.json",
            "native_config.yaml": "04-native_config.yaml",
        }
        manifest_rows = []
        for source_name, private_name in mapping.items():
            source_path = src / source_name
            target = dst / "private/source_manifests" / private_name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target)
            manifest_rows.append({
                "source": f"source-native-v4/{cid}/{source_name}",
                "private_copy": f"private/source_manifests/{private_name}",
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            })
        cfg = RUNTIME[cid]
        native = json.loads((src / "native_case.json").read_text(encoding="utf-8"))
        public = json.loads((dst / "public_case.yaml").read_text(encoding="utf-8"))
        public["case_id"] = cid
        public["source_tasks"] = [{"benchmark": "MultiAgentBench", "id": cfg["source_id"]}]
        _dump(dst / "public_case.yaml", public)
        _dump(dst / "private/source_adapter.json", {
            "benchmark": "MultiAgentBench",
            "source_task_id": cfg["source_id"],
            "participant_source": "task/task_file/participant_task.json",
            "private_source_manifests": manifest_rows,
            "runtime_plan": {
                "adapter": (native.get("native_runtime") or {}).get("adapter"),
                "source_scenario": (native.get("source_binding") or {}).get("scenario"),
                "source_revision": (native.get("source_binding") or {}).get("upstream_revision"),
                "requires_authored_private_oracle": True,
            },
        })
        official = json.loads((src / "official_task.json").read_text(encoding="utf-8"))["task"]
        instruction = str(official["content"]).strip()
        output = str(official.get("output_format") or "").strip()
        if output:
            instruction += "\n\n" + output
        _dump(dst / "task/task_file/participant_task.json", {"task_id": cfg["source_id"], "instruction": instruction})
        _dump(dst / "task/task_file/async_contract.json", {
            "case_id": cid,
            "source_task_id": cfg["source_id"],
            "event_theme": cfg["theme"],
            "upstream_depth": 4,
            "participant_truth_exposed": False,
        })
        status = json.loads((dst / "STATUS.json").read_text(encoding="utf-8"))
        status.update({"case_id": cid, "status": "blueprint_materialized_pending_source_native_implementation", "source_fidelity": []})
        _dump(dst / "STATUS.json", status)
        (dst / "PROVENANCE.md").write_text(
            f"# Provenance\n\nPinned official MultiAgentBench task `{cfg['source_id']}`. "
            "The private source manifests are case-contained and hash locked.\n",
            encoding="utf-8",
        )
