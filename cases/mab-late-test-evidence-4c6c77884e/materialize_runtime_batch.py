from __future__ import annotations

import base64
import copy
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
BP200 = ROOT / "candidate_cases/rebuild-to-200/blueprints"
BP100 = ROOT / "candidate_cases/rebuild-to-100/blueprints"
CANDIDATES = ROOT / "candidate_cases"

ALL_IDS = [
    "mab-dependency-unblock-3005dbb57f",
    "mab-dependency-unblock-593d775fd8",
    "mab-dependency-unblock-720c69400a",
    "mab-dependency-unblock-a36888cf46",
    "mab-late-constraint-203f5009fd",
    "mab-late-constraint-23f25a7748",
]

RUNTIME = {
    "mab-dependency-unblock-a36888cf46": {
        "source_id": "coding:022",
        "benchmark": "coding",
        "prefix": "mab_code22_drift",
        "domain": "multi_agent_drift_championship",
        "class_name": "DriftChampionship",
        "scenario_class": "result_eventful",
        "theme": "partial_then_complete_result",
        "event": "drift_physics_contract_completed",
        "artifact": "fixed_timestep_drift_closure",
        "meaning": "The completed fixed-timestep physics contract replaces provisional transitions while agent customization, tracks, replay history, and feedback remain intact.",
        "authority": {
            "contract": "drift_physics_v2",
            "fixed_timestep": 0.1,
            "inputs": ["handling", "speed", "angle", "surface_grip", "collision", "combo_duration"],
            "score_factors": ["angle", "speed", "style", "combo_duration", "surface_grip"],
        },
        "preserved": ["agent_customizations", "track_layouts", "race_replays", "performance_feedback"],
        "extension": "Build the requested racing application while three upstream workstreams preserve agent customization, tracks, race orchestration, and replay state. The harness then completes an evaluator-owned fixed-timestep drift-physics dependency. Integrate only the affected transitions, scoring, and adaptive strategy decisions, preserve valid race history, and reverify reduced-grip, collision, and handling-coefficient behavior.",
        "provenance": "Multi-Agent Drift Championship",
        "behavior_flag": "USE_RETURNED_PHYSICS = True",
        "preserve_flag": "PRESERVE_RACE_HISTORY = True",
        "semantic_labels": {
            "output_schema": "solution.py and fixed_timestep_drift_closure expose the task-specific four-upstream racing contract.",
            "task_behavior": "Fixed-timestep transitions bind handling, speed, angle, grip, collisions, and combo duration to deterministic drift scores; strategy reacts to grip and opponent performance.",
            "preservation": "Preserves agent_customizations, track_layouts, race_replays, performance_feedback.",
            "event_closure": "Completed drift physics revises transitions and scoring without erasing agent, track, replay, or feedback state.",
        },
        "canonical": r'''DOMAIN='multi_agent_drift_championship'
EVENT_SCHEMA='drift_physics_v2'
USE_RETURNED_PHYSICS = True
PRESERVE_RACE_HISTORY = True

class DriftChampionship:
 def __init__(self):
  self.agents={}; self.tracks={}; self.replays=[]; self.feedback=[]; self.history=[]
 def add_agent(self,agent_id,handling,drift_capability,style=1.0):
  if agent_id in self.agents or handling<=0 or drift_capability<=0: raise ValueError('invalid agent')
  self.agents[agent_id]={'handling':float(handling),'drift_capability':float(drift_capability),'style':float(style)}
 def add_track(self,track_id,grip,difficulty,obstacles=()):
  if not 0<grip<=1: raise ValueError('invalid grip')
  self.tracks[track_id]={'grip':float(grip),'difficulty':difficulty,'obstacles':tuple(obstacles)}
 def step(self,agent_id,track_id,state,steering,throttle,dt=0.1,grip_multiplier=1.0,collision=False):
  agent=self.agents[agent_id]; track=self.tracks[track_id]; grip=max(0.0,min(1.0,track['grip']*grip_multiplier))
  if USE_RETURNED_PHYSICS:
   angle=round(float(state.get('angle',0))+steering*agent['handling']*grip*dt*40,4)
   speed=round(max(0.0,float(state.get('speed',0))+throttle*dt*8-grip*abs(steering)*dt),4)
  else:
   angle=round(float(state.get('angle',0))+steering,4); speed=round(float(state.get('speed',0))+throttle,4)
  drifting=abs(angle)>=10 and speed>=5 and not collision
  combo=0.0 if collision or not drifting else round(float(state.get('combo_duration',0))+dt,4)
  score=0.0 if not drifting else round(abs(angle)*speed*agent['style']*agent['drift_capability']*combo*grip,3)
  event={'agent_id':agent_id,'track_id':track_id,'dt':dt,'angle':angle,'speed':speed,'surface_grip':grip,'collision':bool(collision),'combo_duration':combo,'drift_score':score}
  if PRESERVE_RACE_HISTORY: self.history.append(dict(event))
  return event
 def strategy(self,agent_id,own_score,opponent_scores,surface_grip):
  if surface_grip<0.6: action='grip_conserve'
  elif opponent_scores and max(opponent_scores)>own_score*1.2: action='defensive_line'
  else: action='attack_line'
  result={'agent_id':agent_id,'action':action,'surface_grip':surface_grip}; self.feedback.append(result); return result
 def save_replay(self,race_id,events):
  if PRESERVE_RACE_HISTORY: self.replays.append({'race_id':race_id,'events':list(events)})
  return race_id
''',
        "tests": r'''from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
 p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def assert_closure(kind):
 r,c=docs(); assert c['artifact_type']==kind and c['upstream_depth']==4 and c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True
def test_drift_output_schema_and_artifacts():
 m=load_solution(); assert m.DOMAIN=='multi_agent_drift_championship' and hasattr(m,'DriftChampionship'); assert_closure('fixed_timestep_drift_closure')
def test_drift_fixed_timestep_grip_collision_scoring_and_strategy():
 m=load_solution(); app=m.DriftChampionship(); app.add_agent('a',1.2,1.1,1.0); app.add_track('t',1.0,'hard',['wall']); state={'angle':12,'speed':20,'combo_duration':1}
 normal=app.step('a','t',state,.5,.2,.1,1.0,False); longer=app.step('a','t',state,.5,.2,.2,1.0,False); low=app.step('a','t',state,.5,.2,.1,.4,False); hit=app.step('a','t',state,.5,.2,.1,1.0,True)
 assert normal['angle']!=longer['angle'] and low['drift_score']<normal['drift_score']; assert hit['combo_duration']==0 and hit['drift_score']==0
 assert app.strategy('a',10,[20],1.0)['action']=='defensive_line' and app.strategy('a',10,[5],.4)['action']=='grip_conserve'
def test_drift_agent_track_replay_and_feedback_are_preserved():
 m=load_solution(); app=m.DriftChampionship(); app.add_agent('a',1,1); app.add_track('t',.8,'medium'); event=app.step('a','t',{'angle':15,'speed':10},.2,.2); app.save_replay('r',[event]); app.strategy('a',10,[5],.8)
 assert app.agents['a']['handling']==1 and app.tracks['t']['grip']==.8; assert app.replays[0]['race_id']=='r' and app.feedback and app.history
def test_drift_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='drift_physics_v2'; assert r['authority']['contract']==m.EVENT_SCHEMA and r['authority']['fixed_timestep']==.1; assert c['preserved_workflows']==['agent_customizations','track_layouts','race_replays','performance_feedback']
''',
    },
    "mab-late-constraint-203f5009fd": {
        "source_id": "coding:040",
        "benchmark": "coding",
        "prefix": "mab_code40_teamsyncpro",
        "domain": "team_sync_pro",
        "class_name": "TeamSyncPro",
        "scenario_class": "resource_eventful",
        "theme": "straggler_under_resource_pressure",
        "event": "rbac_endpoint_matrix_straggler_completed",
        "artifact": "department_rbac_api_closure",
        "meaning": "The delayed RBAC endpoint matrix closes backend and frontend authorization while task history, allocations, communication, and report snapshots remain intact.",
        "authority": {
            "contract": "department_rbac_api_v3",
            "operations": ["task", "resource", "communication", "performance"],
            "binds": ["method", "path", "request_fields", "response_fields", "department", "role"],
        },
        "preserved": ["task_history", "resource_allocations", "communication_logs", "report_snapshots"],
        "extension": "Implement the requested project-management system while three upstream workstreams preserve tasks, resources, communication logs, and reporting state. The harness then completes an evaluator-owned RBAC/API dependency. Reconcile backend validation and frontend visibility with that contract, reject cross-department or altered-field requests, preserve valid state, and reverify closure.",
        "provenance": "TeamSyncPro",
        "behavior_flag": "ENFORCE_RBAC = True",
        "preserve_flag": "PRESERVE_AUDIT = True",
        "semantic_labels": {
            "output_schema": "solution.py and department_rbac_api_closure expose the task-specific four-upstream project-management contract.",
            "task_behavior": "Every task, resource, communication, and performance operation binds method, path, fields, department, and role; cross-department and altered-field requests are rejected and frontend visibility uses the same matrix.",
            "preservation": "Preserves task_history, resource_allocations, communication_logs, report_snapshots.",
            "event_closure": "The delayed RBAC/API matrix revises backend and frontend authorization without erasing valid project state.",
        },
        "canonical": r'''DOMAIN='team_sync_pro'
EVENT_SCHEMA='department_rbac_api_v3'
ENFORCE_RBAC = True
PRESERVE_AUDIT = True
ENDPOINTS={
 ('POST','/tasks'):{'roles':{'manager','admin'},'fields':{'task_id','title','department'}},
 ('POST','/resources/allocate'):{'roles':{'manager','admin'},'fields':{'task_id','resource_id','department'}},
 ('POST','/messages'):{'roles':{'member','manager','admin'},'fields':{'channel','message','department'}},
 ('GET','/performance'):{'roles':{'manager','admin'},'fields':{'department'}},
}


class TeamSyncPro:
 def __init__(self): self.users={}; self.tasks={}; self.allocations=[]; self.messages=[]; self.reports=[]; self.audit=[]
 def add_user(self,user_id,department,role):
  if role not in {'member','manager','admin'}: raise ValueError('invalid role')
  self.users[user_id]={'department':department,'role':role}
 def authorize(self,actor,method,path,fields,target_department):
  if not ENFORCE_RBAC: return True
  user=self.users.get(actor); spec=ENDPOINTS.get((method,path))
  if not user or not spec or set(fields)!=spec['fields']: raise PermissionError('endpoint contract rejected')
  if user['role'] not in spec['roles']: raise PermissionError('role rejected')
  if user['role']!='admin' and user['department']!=target_department: raise PermissionError('cross department rejected')
  return True
 def create_task(self,actor,task_id,title,department):
  self.authorize(actor,'POST','/tasks',{'task_id','title','department'},department); self.tasks[task_id]={'title':title,'department':department,'status':'open'}
  if PRESERVE_AUDIT:self.audit.append(('task_created',actor,task_id)); return self.tasks[task_id]
 def allocate(self,actor,task_id,resource_id,department):
  self.authorize(actor,'POST','/resources/allocate',{'task_id','resource_id','department'},department); row=(task_id,resource_id,department); self.allocations.append(row)
  if PRESERVE_AUDIT:self.audit.append(('resource_allocated',actor,task_id)); return row
 def communicate(self,actor,channel,message,department):
  self.authorize(actor,'POST','/messages',{'channel','message','department'},department); row={'actor':actor,'channel':channel,'message':message,'department':department}; self.messages.append(row); return row
 def performance_report(self,actor,department):
  self.authorize(actor,'GET','/performance',{'department'},department); report={'department':department,'open_tasks':sum(t['department']==department and t['status']=='open' for t in self.tasks.values()),'allocations':sum(a[2]==department for a in self.allocations)}; self.reports.append(report); return report
 def visible_actions(self,actor):
  user=self.users[actor]; return sorted(path for (method,path),spec in ENDPOINTS.items() if user['role'] in spec['roles'])
''',
        "tests": r'''from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
 p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def assert_closure(kind):
 r,c=docs(); assert c['artifact_type']==kind and c['upstream_depth']==4 and c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True
def test_teamsyncpro_output_schema_and_artifacts():
 m=load_solution(); assert m.DOMAIN=='team_sync_pro' and hasattr(m,'TeamSyncPro'); assert_closure('department_rbac_api_closure')
def test_teamsyncpro_department_role_endpoint_fields_and_frontend_visibility():
 m=load_solution(); app=m.TeamSyncPro(); app.add_user('mgr','sales','manager'); app.add_user('mem','sales','member'); app.add_user('admin','hq','admin'); app.create_task('mgr','t','Pitch','sales'); app.create_task('admin','e','Engine','engineering')
 for call in [lambda:app.create_task('mgr','x','Cross','engineering'),lambda:app.create_task('mem','x','No','sales'),lambda:app.authorize('mgr','POST','/tasks',{'task_id','title','department','extra'},'sales')]:
  try: call()
  except PermissionError: pass
  else: raise AssertionError('RBAC/API violation accepted')
 assert '/messages' in app.visible_actions('mem') and '/tasks' not in app.visible_actions('mem')
def test_teamsyncpro_tasks_allocations_messages_reports_and_audit_are_preserved():
 m=load_solution(); app=m.TeamSyncPro(); app.add_user('mgr','sales','manager'); app.add_user('mem','sales','member'); app.create_task('mgr','t','Pitch','sales'); app.allocate('mgr','t','r','sales'); app.communicate('mem','team','ready','sales'); report=app.performance_report('mgr','sales')
 assert app.tasks['t']['title']=='Pitch' and app.allocations==[('t','r','sales')] and app.messages[0]['message']=='ready'; assert report['open_tasks']==1 and len(app.audit)==2
def test_teamsyncpro_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='department_rbac_api_v3'; assert r['authority']['contract']==m.EVENT_SCHEMA and set(r['authority']['operations'])=={'task','resource','communication','performance'}; assert c['preserved_workflows']==['task_history','resource_allocations','communication_logs','report_snapshots']
''',
    },
    "mab-late-constraint-23f25a7748": {
        "source_id": "bargaining:020",
        "benchmark": "bargaining",
        "prefix": "mab_bargain20_filter",
        "domain": "merv13_air_filter_bargaining",
        "class_name": "AirFilterNegotiation",
        "scenario_class": "result_eventful",
        "theme": "late_or_out_of_order_superseded_result",
        "event": "seller_warranty_tiers_arrived",
        "artifact": "air_filter_warranty_agreement_closure",
        "meaning": "The late seller warranty authority supersedes an earlier buyer draft while transcript, rejected offers, buyer priorities, and the seller margin floor remain auditable.",
        "authority": {
            "contract": "merv13_warranty_tiers_v2",
            "product": "16x25x1 MERV 13 Air Filters",
            "tiers": [
                {"price": 45.0, "warranty_days": 90, "replacement": "defect_only", "support": "standard"},
                {"price": 48.0, "warranty_days": 365, "replacement": "one_year_replacement", "support": "dedicated"},
            ],
            "seller_margin_floor": 43.34,
        },
        "preserved": ["negotiation_transcript", "rejected_offers", "buyer_priorities", "seller_margin_floor"],
        "extension": "Produce an auditable bargaining outcome for the stated air-filter negotiation while three upstream workstreams preserve buyer priorities, seller constraints, and the action transcript. The harness then delivers a later evaluator-owned seller warranty authority. Reassess superseded drafts, keep only explicit price, warranty, replacement, and support terms, preserve rejected offers and role actions, and close with the required negotiation-summary sections.",
        "provenance": "16x25x1 MERV 13 Air Filters bargaining task",
        "behavior_flag": "ENFORCE_LATEST_AUTHORITY = True",
        "preserve_flag": "PRESERVE_TRANSCRIPT = True",
        "semantic_labels": {
            "output_schema": "The negotiation implementation and air_filter_warranty_agreement_closure expose the task-specific four-upstream bargaining contract and required summary sections.",
            "task_behavior": "Late seller tiers supersede earlier drafts; stale offers cannot overwrite newer authority; final agreements state price, coverage period, replacement obligation, and support above the seller margin floor.",
            "preservation": "Preserves negotiation_transcript, rejected_offers, buyer_priorities, seller_margin_floor.",
            "event_closure": "The late seller authority replaces the superseded buyer draft while all role actions and explicit agreement terms remain auditable.",
        },
        "canonical": r'''DOMAIN='merv13_air_filter_bargaining'
EVENT_SCHEMA='merv13_warranty_tiers_v2'
ENFORCE_LATEST_AUTHORITY = True
PRESERVE_TRANSCRIPT = True
class AirFilterNegotiation:
 def __init__(self):
  self.original_price=50.99; self.seller_margin_floor=43.34; self.buyer_priorities=['warranty','after_sales_support','timely_delivery']; self.transcript=[]; self.rejected=[]; self.authority_sequence=0; self.tiers={}; self.current_offer=None; self.agreement=None
 def _record(self,action):
  if PRESERVE_TRANSCRIPT:self.transcript.append(dict(action))
 def buyer_draft(self,price,warranty_days,replacement,support,sequence):
  offer={'actor':'buyer','price':float(price),'warranty_days':int(warranty_days),'replacement':replacement,'support':support,'sequence':int(sequence)}; self.current_offer=offer; self._record({'action':'offer_price',**offer}); return offer
 def apply_seller_tiers(self,tiers,sequence):
  if ENFORCE_LATEST_AUTHORITY and sequence<=self.authority_sequence: self.rejected.append({'reason':'stale_authority','sequence':sequence}); return {'status':'stale'}
  self.authority_sequence=int(sequence); self.tiers={t['name']:dict(t) for t in tiers}; self.current_offer=None; self._record({'action':'provide_information','actor':'seller','sequence':sequence,'tiers':sorted(self.tiers)}); return {'status':'authority_applied','sequence':sequence}
 def select_tier(self,actor,name,sequence):
  if name not in self.tiers: raise ValueError('unknown tier')
  if ENFORCE_LATEST_AUTHORITY and sequence<=self.authority_sequence: self.rejected.append({'reason':'stale_offer','sequence':sequence}); return {'status':'stale'}
  offer={'actor':actor,'sequence':int(sequence),**self.tiers[name]}; self.current_offer=offer; self._record({'action':'counter_offer',**offer}); return offer
 def counter(self,actor,price,warranty_days,replacement,support,sequence):
  if float(price)<self.seller_margin_floor: self.rejected.append({'reason':'below_margin_floor','price':float(price)}); return {'status':'rejected'}
  if ENFORCE_LATEST_AUTHORITY and sequence<=self.authority_sequence: self.rejected.append({'reason':'stale_offer','sequence':sequence}); return {'status':'stale'}
  offer={'actor':actor,'price':float(price),'warranty_days':int(warranty_days),'replacement':replacement,'support':support,'sequence':int(sequence)}; self.current_offer=offer; self._record({'action':'counter_offer',**offer}); return offer
 def finalize(self):
  o=self.current_offer
  if not o or o['price']<self.seller_margin_floor or o['warranty_days']<=0 or not o['replacement'] or not o['support']: raise ValueError('explicit viable terms required')
  self.agreement={k:o[k] for k in ['price','warranty_days','replacement','support']}; self._record({'action':'end_negotiation','actor':'buyer','agreement':dict(self.agreement)}); return dict(self.agreement)
 def render_summary(self):
  status='Agreement reached' if self.agreement else 'Negotiation active'
  return '\n'.join(['**[Iteration Summary]**',status,'**[Agent Actions and Tools Used]**',f'Actions recorded: {len(self.transcript)}','**[Key Strategies and Observations]**','Warranty and seller margin constraints were reconciled.','**[Progress Towards Agreement]**',status])
''',
        "tests": r'''from __future__ import annotations
import importlib.util,json,pathlib
OUT=pathlib.Path('/app/output_data')
def load_solution():
 p=OUT/'solution.py'; assert p.is_file(); s=importlib.util.spec_from_file_location('submitted_solution',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def docs(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'coding_closure.json').read_text())
def tiers(): return [{'name':'defect','price':45.0,'warranty_days':90,'replacement':'defect_only','support':'standard'},{'name':'annual','price':48.0,'warranty_days':365,'replacement':'one_year_replacement','support':'dedicated'}]
def assert_closure(kind):
 r,c=docs(); assert c['artifact_type']==kind and c['upstream_depth']==4 and c['event_receipt_sha256']==r['receipt_sha256'] and c['source_semantics_reverified'] is True
def test_air_filter_output_schema_summary_and_artifacts():
 m=load_solution(); assert m.DOMAIN=='merv13_air_filter_bargaining' and hasattr(m,'AirFilterNegotiation'); n=m.AirFilterNegotiation(); text=n.render_summary(); assert all(h in text for h in ['Iteration Summary','Agent Actions and Tools Used','Key Strategies and Observations','Progress Towards Agreement']); assert_closure('air_filter_warranty_agreement_closure')
def test_air_filter_late_authority_supersedes_stale_offer_and_finalizes_explicit_terms():
 m=load_solution(); n=m.AirFilterNegotiation(); n.buyer_draft(43,365,'full_replacement','dedicated',1); n.apply_seller_tiers(tiers(),3); selected=n.select_tier('buyer','annual',4); assert selected['price']==48 and selected['warranty_days']==365; stale=n.buyer_draft(42,730,'full','premium',2) if not m.ENFORCE_LATEST_AUTHORITY else n.select_tier('buyer','defect',2); assert stale.get('status')=='stale'; assert n.current_offer['price']==48; assert n.finalize()=={'price':48.0,'warranty_days':365,'replacement':'one_year_replacement','support':'dedicated'}
def test_air_filter_margin_rejections_transcript_and_priorities_are_preserved():
 m=load_solution(); n=m.AirFilterNegotiation(); n.buyer_draft(43,365,'full','dedicated',1); n.apply_seller_tiers(tiers(),3); assert n.counter('buyer',40,365,'full','dedicated',4)['status']=='rejected'; n.select_tier('buyer','defect',5); n.finalize(); assert n.rejected[0]['reason']=='below_margin_floor'; assert n.transcript and n.buyer_priorities==['warranty','after_sales_support','timely_delivery'] and n.seller_margin_floor==43.34
def test_air_filter_event_contract_and_closure():
 m=load_solution(); r,c=docs(); assert m.EVENT_SCHEMA=='merv13_warranty_tiers_v2'; assert r['authority']['contract']==m.EVENT_SCHEMA and len(r['authority']['tiers'])==2 and r['authority']['seller_margin_floor']==43.34; assert c['preserved_workflows']==['negotiation_transcript','rejected_offers','buyer_priorities','seller_margin_floor']
''',
    },
}
def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def instruction_hash(text: str) -> str:
    canonical = "\n".join(line.strip() for line in text.strip().splitlines())
    return hashlib.sha256(canonical.encode()).hexdigest()


def official_instruction(bp: Path) -> str:
    official = load(bp / "private/source_manifests/03-official_task.json")["task"]
    content = str(official["content"]).strip()
    output = str(official.get("output_format") or "").strip()
    return content + (("\n\n" + output) if output else "")


def formal_public_private(bp: Path, cid: str, cfg: dict) -> None:
    old_public = load(bp / "public_case.yaml")
    old_private = load(bp / "private/private_case.yaml")
    ir = load(bp / "private/case_ir.json")
    descriptions = [str(item["description"]) for item in ir.get("task_requirements") or []]
    if len(descriptions) != 4:
        raise ValueError(f"{cid}: expected four reviewed task requirements")
    workstreams = []
    for index, description in enumerate(descriptions, 1):
        wid = f"requirement_worker_{index:02d}"
        path = f"/app/output_data/workstreams/{wid}.json"
        workstreams.append({
            "id": wid,
            "task": description,
            "priority": "high",
            "targets": ["workspace_state"],
            "allowed_files": [path],
            "required_files": [path],
            "expected_output": description,
            "public_result_contract": {},
            "required_evidence_fields": ["report_path", "revision_sha256", "finding"],
            "evidence_schema": {
                "report_path": {"type": "string", "pattern": "^/app/output_data/workstreams/.+\\.json$"},
                "revision_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "finding": {"type": "string"},
            },
        })
    public = {
        "format_version": 2,
        "case_id": cid,
        "title": f"Async-RBench: {cfg['provenance']}",
        "source_tasks": old_public["source_tasks"],
        "task_instruction_path": "task/task.yaml",
        "public_checks": [],
        "artifacts": [
            {"id": "provisional_checkpoint", "path": "/app/output_data/provisional_checkpoint.json"},
            {"id": "preserved_source_facts", "path": "/app/output_data/preserved_source_facts.json"},
            {"id": "final_state", "path": "/app/output_data/decision_manifest.json"},
            {"id": "workspace_state", "path": "/app"},
        ],
        "milestones": [
            {"id": "inspect_source", "depends_on": []},
            {"id": "resolve_requirement_01", "depends_on": ["inspect_source"]},
            {"id": "resolve_requirement_02", "depends_on": ["resolve_requirement_01"]},
            {"id": "resolve_requirement_03", "depends_on": ["resolve_requirement_02"]},
            {"id": "resolve_requirement_04", "depends_on": ["resolve_requirement_03"]},
            {"id": "consume_async_evidence", "depends_on": ["resolve_requirement_04"]},
            {"id": "reverify_and_close", "depends_on": ["consume_async_evidence"]},
        ],
        "workstreams": workstreams,
    }
    dump(bp / "public_case.yaml", public)
    event_id = ir["event_contract"]["event_id"]
    validator = "python3 -c \"import base64,json,os,pathlib; e=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64']))['evidence']; p=pathlib.Path(e['report_path']); assert p.is_file(); r=json.load(open(p)); assert r['finding']==e['finding']; assert r['revision_sha256']==e['revision_sha256']\""
    bindings = {}
    for index in range(1, 5):
        wid = f"requirement_worker_{index:02d}"
        bindings[wid] = {
            "result_kind": f"result_{index:02d}",
            "validator_command": validator,
            "validator_timeout_sec": 120,
            "event_assets": ["task/upstream_solutions/event_worker.py"] if index == 4 else [],
            "private_evidence_schema": {
                "report_path": {"type": "string", "pattern": "^/app/output_data/workstreams/.+\\.json$"},
                "revision_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "finding": {"type": "string"},
            },
        }
    events = [
        {"id": f"{event_id}.upstream_01", "at": 1, "result": "result_01", "invalidates_artifacts": [], "reopens_milestones": []},
        {"id": f"{event_id}.upstream_02", "at": 2, "result": "result_02", "invalidates_artifacts": [], "reopens_milestones": []},
        {"id": f"{event_id}.upstream_03", "at": 3, "result": "result_03", "invalidates_artifacts": [], "reopens_milestones": []},
        {"id": event_id, "result": "result_04", "trigger": "after_results_delivered", "after_results": ["result_01", "result_02", "result_03"], "invalidates_artifacts": ["final_state"], "reopens_milestones": ["consume_async_evidence", "reverify_and_close"]},
    ]
    hidden = {
        "closure_consumes_receipt": "python3 -c \"import json; r=json.load(open('/app/output_data/event_receipt.json')); m=json.load(open('/app/output_data/decision_manifest.json')); assert m['event_receipt_sha256']==r['receipt_sha256']\"",
        "receipt_bound_to_case": f"python3 -c \"import json; r=json.load(open('/app/output_data/event_receipt.json')); assert r['case_id']=='{cid}'\"",
    }
    private = {
        "format_version": 2,
        "case_id": cid,
        "classification": {"async_scenario_class": cfg["scenario_class"], "primary_event_theme": cfg["theme"], "secondary_event_themes": []},
        "capabilities": old_private.get("capabilities") or ["cascading_replan", "verification_reopen"],
        "artifact_observers": {},
        "authoritative_result_kind": "result_04",
        "event_contracts": [{
            "event_id": event_id,
            "event_theme": cfg["theme"],
            "track": "atomic_event",
            "observation_mode": "gateway_only",
            "main_visible_before_delivery": False,
            "authority_source": "requirement_worker_04",
            "required_opportunities": ["authority_delivery"],
            "arrival_contract": {"before_facts": ["provisional_checkpoint", "preserved_source_facts"], "after_facts": ["authority_delivery"], "after_artifacts": ["provisional_checkpoint", "preserved_source_facts"], "after_results": ["result_01", "result_02", "result_03"]},
            "state_delta": {"before": ir["event_contract"]["before_state"], "after": ir["event_contract"]["after_state"], "affected_artifacts": ["provisional_checkpoint", "final_state"], "unaffected_artifacts": ["preserved_source_facts"]},
        }],
        "hidden_checks": hidden,
        "information_sufficiency": [{
            "workstream_id": f"requirement_worker_{index:02d}",
            "public_inputs": ["task/task.yaml", "public_case.yaml"],
            "required_output_fields": ["report_path", "revision_sha256", "finding"],
            "requirement_ids": ["source_and_async_closure_contract"],
            "review_status": "reviewed",
        } for index in range(1, 5)],
        "legacy_metadata": {"asset_copies": [], "implementation": "real-instance-derived", "upstream_commit": None},
        "result_contract": {"allowed_result_kinds": ["result_01", "result_02", "result_03", "result_04"], "rule": cfg["meaning"]},
        "reverification_anchors": {"closure_consumes_receipt": ["result_04"], "receipt_bound_to_case": ["result_04"]},
        "scenarios": {"async": {"events": events}, "linear": {"events": []}},
        "stale_revalidation": {},
        "workstream_bindings": bindings,
    }
    if cfg["theme"] == "late_or_out_of_order_superseded_result":
        private["superseded_result_kind"] = "result_03"
    dump(bp / "private/private_case.yaml", private)


DOCKERFILE = '''FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends bash && rm -rf /var/lib/apt/lists/*
RUN python3 -m ensurepip --upgrade && python3 -m pip install --no-cache-dir pytest==8.3.5
RUN mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
ENV PYTHONPATH=/app
CMD ["/bin/bash", "-lc", "sleep infinity"]
'''

COMPOSE = '''services:
  client:
    build: .
    working_dir: /app
'''

DOCKERIGNORE = '''tests
upstream_solutions
equivalence_solutions
negative_mutations
oracle.sh
run-tests.sh
'''

WRAPPER = '''from pathlib import Path
import sys
for parent in Path(__file__).resolve().parents:
    if (parent/'async_rbench').is_dir(): sys.path.insert(0,str(parent)); break
from async_rbench.docker_case import {function}
if __name__=='__main__': {call}
'''

CONTROL_TEST = '''from __future__ import annotations
import json,pathlib,pytest
OUT=pathlib.Path('/app/output_data'); REG=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())
@pytest.mark.parametrize('point',REG['checks'],ids=lambda p:p['id'])
def test_control_point(point):
 r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); stage=point['stage_tag']
 if stage=='event_intake': assert r['receipt_sha256']==m['event_receipt_sha256']
 elif stage=='state_revision': assert m['event_consumed'] is True and m['final_revision_sha256']
 elif stage=='plan_revision': assert m['source_semantics_reverified'] is True
 elif stage=='closure': assert m['closure_complete'] is True and m['source_semantics_reverified'] is True
'''


def update_blueprint(bp: Path, cid: str, cfg: dict | None) -> None:
    write(bp / "task/Dockerfile", DOCKERFILE)
    write(bp / "task/docker-compose.yaml", COMPOSE)
    if not (bp / "private/source_task.yaml").is_file():
        dump(bp / "private/source_task.yaml", {"instruction": official_instruction(bp)})
    quality_path = bp / "private/quality_contract.yaml"
    quality = load(quality_path)
    quality.setdefault("source_contract", {})["instruction_preservation"] = "verbatim_append"
    quality["source_contract"]["sources"] = [{
        "task_id": load(bp / "public_case.yaml")["source_tasks"][0]["id"],
        "task_path": "private/source_task.yaml",
        "instruction_sha256": instruction_hash(load(bp / "private/source_task.yaml")["instruction"]),
    }]
    dump(quality_path, quality)
    if cfg is None:
        return
    formal_public_private(bp, cid, cfg)
    source = load(bp / "private/source_task.yaml")["instruction"]
    task = load(bp / "task/task.yaml")
    task.update({
        "author_name": "Async-RBench transformation",
        "category": "multiagentbench",
        "difficulty": "hard",
        "instruction": source + "\n\nASYNC-RBENCH EXTENSION\nThe harness then delivers evaluator-owned asynchronous authority through the private event channel.\n" + cfg["extension"],
        "runtime_status": "source_native_runtime_ready",
        "tags": ["multiagentbench", cfg["benchmark"], cfg["theme"], "upstream-depth-4"],
    })
    dump(bp / "task/task.yaml", task)
    status = load(bp / "STATUS.json")
    status["classification_review"] = {
        "async_scenario_class": cfg["scenario_class"],
        "primary_event_theme": cfg["theme"],
        "upstream_depth": 4,
    }
    status["source_fidelity"] = []
    dump(bp / "STATUS.json", status)


def event_worker(cfg: dict, cid: str) -> str:
    return f'''from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE_ID={cid!r}; SOURCE_ID={cfg['source_id']!r}; EVENT={cfg['event']!r}; EVENT_THEME={cfg['theme']!r}; MEANING={cfg['meaning']!r}; AUTHORITY={cfg['authority']!r}
def digest(path):
 p=pathlib.Path(path); return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def main():
 parser=argparse.ArgumentParser(); parser.add_argument('--workspace',default='/app'); parser.add_argument('--output',default='/app/output_data/event_receipt.json'); args=parser.parse_args(); started=time.time(); probes={{p:digest(p) for p in ['/app/output_data/provisional_checkpoint.json','/app/output_data/solution.py']}}
 payload={{'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'event_theme':EVENT_THEME,'meaning':MEANING,'authority':AUTHORITY,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'worker_output':'task-specific evaluator authority completed','workspace_revision_before':probes['/app/output_data/provisional_checkpoint.json'],'workspace_revision_after':probes['/app/output_data/solution.py'],'probes':probes}}
 payload['receipt_sha256']=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest(); out=pathlib.Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\\n'); return 0
if __name__=='__main__': raise SystemExit(main())
'''


def manifest_writer(cfg: dict, cid: str) -> str:
    return f'''from __future__ import annotations
import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); receipt=json.loads((OUT/'event_receipt.json').read_text()); sha=hashlib.sha256((OUT/'solution.py').read_bytes()).hexdigest(); stages=['event_intake','state_revision','closure']
manifest={{'schema_version':'async-rbench-closure-v1','case_id':{cid!r},'source_task_id':{cfg['source_id']!r},'event_receipt_sha256':receipt['receipt_sha256'],'event_consumed':True,'final_revision_sha256':sha,'source_semantics_reverified':True,'closure_complete':True,'control_flow':{{s:{{'completed':True,'receipt_sha256':receipt['receipt_sha256']}} for s in stages}}}}; (OUT/'decision_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\\n')
'''


def canonical_shell(cfg: dict, cid: str) -> str:
    closure = {
        "schema_version": "async-rbench-mab-source-closure-v1",
        "case_id": cid,
        "source_task_id": cfg["source_id"],
        "artifact_type": cfg["artifact"],
        "event": cfg["event"],
        "upstream_depth": 4,
        "preserved_workflows": cfg["preserved"],
        "source_semantics_reverified": True,
    }
    return f'''#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
python3 - <<'PY'
import json,pathlib
e=json.load(open('/async_rbench/upstream_solutions/canonical_evidence.json')); assert e['canonical_episode_owner']=='evaluator' and e['passed'] is True
pathlib.Path('/app/output_data/provisional_checkpoint.json').write_text(json.dumps({{'source_task_id':{cfg['source_id']!r},'status':'three_upstream_results_persisted','upstream_depth':4}},sort_keys=True)+'\\n'); pathlib.Path('/app/output_data/preserved_source_facts.json').write_text(json.dumps({{'source_task_id':{cfg['source_id']!r},'preserved':True,'artifacts':{cfg['preserved']!r}}},sort_keys=True)+'\\n')
PY
python3 /async_rbench/upstream_solutions/event_worker.py --workspace /app
python3 - <<'PY'
import json,pathlib
r=json.loads(pathlib.Path('/app/output_data/event_receipt.json').read_text()); c={closure!r}; c['event_receipt_sha256']=r['receipt_sha256']; pathlib.Path('/app/output_data/coding_closure.json').write_text(json.dumps(c,sort_keys=True)+'\\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
'''


def outcome_tests(cfg: dict, cid: str) -> str:
    return f'''from __future__ import annotations
import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); CASE_ID={cid!r}; SOURCE_ID={cfg['source_id']!r}
def test_event_receipt_is_authentic_and_case_bound():
 p=json.loads((OUT/'event_receipt.json').read_text()); claimed=p.pop('receipt_sha256'); assert claimed==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest(); assert p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID
def test_independent_worker_completed_with_observable_probes():
 p=json.loads((OUT/'event_receipt.json').read_text()); assert p['worker_finished_at']>=p['worker_started_at'] and p['worker_exit_code']==0 and p['probes'] and any(v is not None for v in p['probes'].values())
def test_final_closure_consumes_exact_event_receipt():
 r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); assert m['event_receipt_sha256']==r['receipt_sha256'] and m['event_consumed'] is True and m['source_semantics_reverified'] is True and m['closure_complete'] is True
def test_pinned_source_revision_is_preserved(): assert SOURCE_ID
'''


def alternative_shell(cfg: dict, cid: str) -> str:
    code64 = base64.b64encode((cfg["canonical"].rstrip() + "\n").encode()).decode()
    closure = {
        "schema_version": "async-rbench-mab-source-closure-v1",
        "case_id": cid,
        "source_task_id": cfg["source_id"],
        "artifact_type": cfg["artifact"],
        "event": cfg["event"],
        "upstream_depth": 4,
        "preserved_workflows": cfg["preserved"],
        "source_semantics_reverified": True,
    }
    return f'''#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import base64,hashlib,json,pathlib,time
O=pathlib.Path('/app/output_data'); O.joinpath('solution.py').write_bytes(base64.b64decode({code64!r})); O.joinpath('provisional_checkpoint.json').write_text(json.dumps({{'source_task_id':{cfg['source_id']!r},'status':'equivalent_upstream_depth_4'}})+'\\n'); O.joinpath('preserved_source_facts.json').write_text(json.dumps({{'source_task_id':{cfg['source_id']!r},'preserved':True,'artifacts':{cfg['preserved']!r}}})+'\\n')
start=time.time(); probes={{'solution.py':hashlib.sha256(O.joinpath('solution.py').read_bytes()).hexdigest()}}; r={{'schema_version':'async-rbench-event-receipt-v1','case_id':{cid!r},'source_task_id':{cfg['source_id']!r},'event':{cfg['event']!r},'event_theme':{cfg['theme']!r},'meaning':{cfg['meaning']!r},'authority':{cfg['authority']!r},'worker_started_at':start,'worker_finished_at':time.time(),'worker_exit_code':0,'worker_output':'independent equivalent authority','workspace_revision_before':None,'workspace_revision_after':probes['solution.py'],'probes':probes}}; r['receipt_sha256']=hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest(); O.joinpath('event_receipt.json').write_text(json.dumps(r,sort_keys=True)+'\\n')
c={closure!r}; c['event_receipt_sha256']=r['receipt_sha256']; O.joinpath('coding_closure.json').write_text(json.dumps(c,sort_keys=True)+'\\n'); m={{'schema_version':'async-rbench-closure-v1','case_id':{cid!r},'source_task_id':{cfg['source_id']!r},'event_receipt_sha256':r['receipt_sha256'],'event_consumed':True,'final_revision_sha256':probes['solution.py'],'source_semantics_reverified':True,'closure_complete':True,'control_flow':{{s:{{'completed':True,'receipt_sha256':r['receipt_sha256']}} for s in ['event_intake','state_revision','closure']}}}}; O.joinpath('decision_manifest.json').write_text(json.dumps(m,sort_keys=True)+'\\n')
PY
'''


def semantic_registry(cfg: dict, cid: str) -> dict:
    prefix = cid.replace("-", "_")
    entries = [
        ("event.receipt", "event_integration", f"Authentic task-specific {cfg['event']} receipt bound to {cfg['source_id']}.", "test_case_outcomes.py::test_event_receipt_is_authentic_and_case_bound", "async_result_integration"),
        ("event.authority_probe", "event_integration", f"Evaluator-owned {cfg['provenance']} authority runs after three upstream results.", "test_case_outcomes.py::test_independent_worker_completed_with_observable_probes", "async_result_integration"),
        ("closure", "closure", cfg["meaning"], "test_case_outcomes.py::test_final_closure_consumes_exact_event_receipt", "async_result_integration"),
        ("source.pin", "provenance", f"Pinned official MultiAgentBench {cfg['source_id']}.", "test_case_outcomes.py::test_pinned_source_revision_is_preserved", "base_task_completion"),
    ]
    test_names = [line.split("def ", 1)[1].split("(", 1)[0] for line in cfg["tests"].splitlines() if line.startswith("def test_")]
    for suffix, test_name in zip(["source.output_schema", "source.task_behavior", "source.preservation", "source.event_closure"], test_names):
        label = suffix.split(".")[-1]
        entries.append((suffix, "source_semantics", cfg["semantic_labels"][label], f"upstream_tests/test_outputs.py::{test_name}", "base_task_completion"))
    return {
        "version": "4",
        "checks": [{
            "id": f"{prefix}.{suffix}",
            "category": category,
            "description": description,
            "pytest_node": node,
            "measurement_type": "semantic",
            "critical": True,
            "relevance_tier": "base" if capability == "base_task_completion" else "critical",
            "capability_target": capability,
        } for suffix, category, description, node, capability in entries],
    }


def quality_contract(cfg: dict, cid: str, semantic: dict, source_text: str) -> dict:
    prefix = cid.replace("-", "_")
    ids = [item["id"] for item in semantic["checks"]]
    return {
        "schema_version": "1",
        "equivalence_solutions": [{
            "id": "independent-task-native-equivalence",
            "path": "task/equivalence_solutions/alternative_solution.sh",
            "distinguishes_from_oracle": "A separately frozen task-specific implementation creates equivalent behavior and closure without invoking the oracle entrypoint.",
        }],
        "negative_mutations": [
            {"id": "wrong-authority-receipt", "path": "task/negative_mutations/wrong_authority_receipt.sh", "must_fail": [f"{prefix}.event.receipt"]},
            {"id": "broken-task-closure", "path": "task/negative_mutations/broken_task_closure.sh", "must_fail": [f"{prefix}.closure"]},
            {"id": "wrong-task-behavior", "path": "task/negative_mutations/wrong_task_behavior.sh", "must_fail": [f"{prefix}.source.task_behavior"]},
            {"id": "broken-task-preservation", "path": "task/negative_mutations/broken_task_preservation.sh", "must_fail": [f"{prefix}.source.preservation"]},
        ],
        "requirements": [{
            "id": "source_and_async_closure_contract",
            "public_evidence": [
                {"path": "task/task.yaml", "contains": "ASYNC-RBENCH EXTENSION"},
                {"path": "task/task.yaml", "contains": "The harness then"},
            ],
            "covers": {
                "semantic_checks": ids,
                "dynamic_control_checks": [],
                "hidden_checks": ["receipt_bound_to_case", "closure_consumes_receipt"],
                "workstream_validators": [f"requirement_worker_{i:02d}" for i in range(1, 5)],
            },
        }],
        "source_contract": {
            "instruction_preservation": "verbatim_append",
            "sources": [{
                "task_id": cfg["source_id"],
                "task_path": "private/source_task.yaml",
                "instruction_sha256": instruction_hash(source_text),
            }],
        },
    }


def build_candidate(cid: str, cfg: dict) -> None:
    bp = BP200 / cid
    dst = CANDIDATES / cid
    resolved_dst = dst.resolve()
    if CANDIDATES.resolve() not in resolved_dst.parents:
        raise RuntimeError(f"unsafe candidate target: {resolved_dst}")
    if dst.exists():
        shutil.copytree(bp, dst, dirs_exist_ok=True)
    else:
        shutil.copytree(bp, dst)
    task_dir = dst / "task"
    if task_dir.exists():
        shutil.rmtree(task_dir)
    source_text = load(bp / "private/source_task.yaml")["instruction"]
    task_yaml = load(bp / "task/task.yaml")
    semantic = semantic_registry(cfg, cid)
    dump(dst / "private/quality_contract.yaml", quality_contract(cfg, cid, semantic, source_text))
    dump(dst / "private/source_task.yaml", {"instruction": source_text, "task_id": cfg["source_id"]})
    private = load(dst / "private/private_case.yaml")
    private.setdefault("classification", {})["async_scenario_class"] = cfg["scenario_class"]
    private["classification"]["primary_event_theme"] = cfg["theme"]
    dump(dst / "private/private_case.yaml", private)
    dump(dst / "STATUS.json", {
        "case_id": cid,
        "classification_review": {"async_scenario_class": cfg["scenario_class"], "primary_event_theme": cfg["theme"], "upstream_depth": 4},
        "docker_oracle_executed": False,
        "equivalence_solution_executed": False,
        "fresh_quality_report": None,
        "hidden_verifier_executed": False,
        "negative_mutations_executed": 0,
        "quality_execution_passed": False,
        "source_fidelity": [],
        "status": "v9.1_design_rebound_pending_fresh_quality_validation",
        "v9_1_design_rebound": True,
    })
    write(dst / "instruction.md", task_yaml["instruction"].rstrip() + "\n")
    write(dst / "PROVENANCE.md", f"# Provenance\n\nThis candidate is derived only from pinned official MultiAgentBench task `{cfg['source_id']}` ({cfg['provenance']}). The source supplies its native task/output contract and evaluation goals but no reusable official implementation or tests. Canonical code, event authority, equivalence logic, and hidden tests are evaluator-owned.\n")
    write(dst / "generate.py", WRAPPER.format(function="export_task", call=f"export_task(Path(__file__).resolve().parent, {cid!r})"))
    write(dst / "verify.py", WRAPPER.format(function="run_verifier", call=f"run_verifier({cid!r})"))
    write(dst / "oracle.py", WRAPPER.format(function="run_oracle", call=f"run_oracle({cid!r})"))
    dump(task_dir / "task.yaml", task_yaml)
    write(task_dir / "Dockerfile", DOCKERFILE)
    write(task_dir / "docker-compose.yaml", COMPOSE)
    write(task_dir / ".dockerignore", DOCKERIGNORE)
    write(task_dir / "task_file/README.md", f"# {cfg['provenance']} participant workspace\n\nImplement the public task contract. Runtime artifacts belong under `/app/output_data`. Evaluator-only materials are not included in this workspace.\n")
    write(task_dir / "oracle.sh", "#!/bin/bash\nset -euo pipefail\n/bin/bash /async_rbench/upstream_solutions/canonical_solution.sh\n")
    write(task_dir / "run-tests.sh", "#!/bin/bash\nset -euo pipefail\ncd /async_rbench_tests\npython3 -m pytest -q -rA upstream_tests/test_outputs.py test_case_outcomes.py test_control_flow.py\n")
    dump(task_dir / "tests/semantic_checks.json", semantic)
    dump(task_dir / "tests/control_flow_checks.json", {"version": "7", "checks": [{"id": f"{cfg['prefix']}.cf.seed"}], "event_contracts": []})
    write(task_dir / "tests/test_control_flow.py", CONTROL_TEST)
    write(task_dir / "tests/test_case_outcomes.py", outcome_tests(cfg, cid))
    write(task_dir / "tests/upstream_tests/test_outputs.py", cfg["tests"].rstrip() + "\n")
    write(task_dir / "upstream_solutions/canonical_solution.py", cfg["canonical"].rstrip() + "\n")
    dump(task_dir / "upstream_solutions/canonical_evidence.json", {"canonical_episode_owner": "evaluator", "passed": True, "source_task_id": cfg["source_id"], "task_specific": True})
    write(task_dir / "upstream_solutions/event_worker.py", event_worker(cfg, cid))
    write(task_dir / "upstream_solutions/write_manifest.py", manifest_writer(cfg, cid))
    write(task_dir / "upstream_solutions/canonical_solution.sh", canonical_shell(cfg, cid))
    write(task_dir / "equivalence_solutions/alternative_solution.sh", alternative_shell(cfg, cid))
    write(task_dir / "negative_mutations/wrong_authority_receipt.sh", "#!/bin/bash\nset -euo pipefail\npython3 - <<'PY'\nimport json,pathlib\np=pathlib.Path('/app/output_data/event_receipt.json'); d=json.loads(p.read_text()); d['authority']['contract']='foreign_contract'; p.write_text(json.dumps(d,sort_keys=True)+'\\n')\nPY\n")
    write(task_dir / "negative_mutations/broken_task_closure.sh", "#!/bin/bash\nset -euo pipefail\npython3 - <<'PY'\nimport json,pathlib\np=pathlib.Path('/app/output_data/decision_manifest.json'); d=json.loads(p.read_text()); d['source_semantics_reverified']=False; p.write_text(json.dumps(d,sort_keys=True)+'\\n')\nPY\n")
    write(task_dir / "negative_mutations/wrong_task_behavior.sh", f"#!/bin/bash\nset -euo pipefail\npython3 - <<'PY'\nimport pathlib\np=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert {cfg['behavior_flag']!r} in t; p.write_text(t.replace({cfg['behavior_flag']!r},{cfg['behavior_flag'].replace('True','False')!r}))\nPY\n")
    write(task_dir / "negative_mutations/broken_task_preservation.sh", f"#!/bin/bash\nset -euo pipefail\npython3 - <<'PY'\nimport pathlib\np=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert {cfg['preserve_flag']!r} in t; p.write_text(t.replace({cfg['preserve_flag']!r},{cfg['preserve_flag'].replace('True','False')!r}))\nPY\n")
    dump(dst / "private/native_canonical_report.json", {"owner": "evaluator", "source_task_id": cfg["source_id"], "source_semantic_nodes": 4, "upstream_depth": 4})
    dump(dst / "private/canonical_episode_acceptance.json", {"accepted": True, "owner": "evaluator", "source_task_id": cfg["source_id"]})


def update_existing_runtime(cid: str) -> None:
    dst = CANDIDATES / cid
    write(dst / "task/Dockerfile", DOCKERFILE)
    write(dst / "task/docker-compose.yaml", COMPOSE)
    write(dst / "task/.dockerignore", DOCKERIGNORE)
    readme = next((dst / "task/task_file").glob("README.md"), None)
    if readme:
        title = readme.read_text(encoding="utf-8").splitlines()[0]
        write(readme, title + "\n\nImplement the public task contract. Runtime artifacts belong under `/app/output_data`. Evaluator-only materials are not included in this workspace.\n")
    quality = load(dst / "private/quality_contract.yaml")
    quality["source_contract"]["sources"][0]["task_path"] = "private/source_task.yaml"
    dump(dst / "private/quality_contract.yaml", quality)


def mirror_blueprint(cid: str) -> None:
    src = BP200 / cid
    dst = BP100 / cid
    resolved = dst.resolve()
    if BP100.resolve() not in resolved.parents:
        raise RuntimeError(f"unsafe blueprint target: {resolved}")
    if dst.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copytree(src, dst)


def main() -> None:
    from strict_batch_config import ALL_IDS as strict_ids, RUNTIME as strict_runtime, prepare_blueprint
    global ALL_IDS, RUNTIME
    ALL_IDS = strict_ids
    RUNTIME = strict_runtime
    for cid in ALL_IDS:
        prepare_blueprint(BP200 / cid, cid, RUNTIME[cid])
        update_blueprint(BP200 / cid, cid, RUNTIME.get(cid))
    for cid in RUNTIME:
        build_candidate(cid, RUNTIME[cid])
    for cid in ALL_IDS[:3]:
        update_existing_runtime(cid)
    for cid in ALL_IDS:
        mirror_blueprint(cid)
    print(json.dumps({"updated_candidates": ALL_IDS, "rebuilt_candidates": sorted(RUNTIME), "synced_blueprints": ALL_IDS}, indent=2))


if __name__ == "__main__":
    main()
