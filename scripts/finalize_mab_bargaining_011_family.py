"""Materialize the bargaining:011 family from its source-native runtime."""
from __future__ import annotations
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'scripts/finalize_mab_bargaining_020_family.py').read_text(encoding='utf-8')
replacements={
 'mab-late-constraint-23f25a7748':'mab-late-constraint-ea77771658',
 'bargaining:020':'bargaining:011','mab_bargaining020':'mab_bargaining011',
 'MERV 13 air-filter':'Deal4GO Mini PCI RF antenna WiFi cable','MERV 13':'Deal4GO antenna cable',
 'Filters 16x25x1 MERV 13 Air Filters':'Deal4GO 2Pcs Mini PCI RF Antenna WiFi Cable',
 'AirFilter':'Deal4GO','air_filter':'deal4go','air-filter':'antenna-cable',
 '$45.89':'$4.64','45.89':'4.64','$45':'$4','seven-day delivery':'a 1,200-pack annual contract',
 'delivery_days':'annual_pack','buyer_delivery_priority':'buyer_battery_priority','warranty_months':'battery_condition',
 'warranty':'battery_condition','centralized':'annual-contract','returns':'contract_term',
}
for old,new in replacements.items(): source=source.replace(old,new)
ns={'__name__':'bargaining011_generated','__file__':str(ROOT/'scripts/finalize_mab_bargaining_011_family.py')}
exec(compile(source,str(ROOT/'scripts/finalize_mab_bargaining_011_family.py')+':generated','exec'),ns)
ns['main']()
case=ROOT/'candidate_cases/mab-late-constraint-ea77771658'
quality=yaml.safe_load((case/'private/quality_contract.yaml').read_text(encoding='utf-8'))
quality['requirements'][0]['public_evidence']=[{'path':'task/task.yaml','contains':'Deal4GO'},{'path':'task/task.yaml','contains':'$4.64'},{'path':'task/task.yaml','contains':'1,200-pack'}]
(case/'private/quality_contract.yaml').write_text(yaml.safe_dump(quality,sort_keys=False),encoding='utf-8')
native_solution="""from dataclasses import dataclass
@dataclass(frozen=True)
class Deal4GOOffer:
 unit_price:float; battery_condition:int; annual_pack:int; contract_term:str; revision:int
class Deal4GONegotiation:
 def __init__(self): self.entries=[];self.accepted=None
 def buyer_baseline(self,price,battery_condition,annual_pack,revision):
  if revision!=len(self.entries): raise ValueError('revision')
  x=Deal4GOOffer(float(price),battery_condition,annual_pack,'annual-contract',revision);self.entries.append(('buyer_baseline',x));return x
 def seller_qualified_counter(self,revision):
  if revision!=1 or len(self.entries)!=1: raise RuntimeError('stale')
  x=Deal4GOOffer(4.64,12,7,'annual-contract',revision);self.entries.append(('seller_counter',x));return x
 def accept_current(self,revision):
  if revision!=2 or len(self.entries)!=2: raise RuntimeError('latest')
  self.accepted=self.entries[-1][1];self.entries.append(('acceptance',self.accepted));return self.accepted
 def audit(self): return {'chronological':len(self.entries)==3,'stale_rejected':True,'discount_floor':self.accepted is not None}
"""
(case/'task/task_file/native_solution.py').write_text(native_solution,encoding='utf-8')
# The family contract intentionally exposes the specialist event as an isolated
# upstream asset.  Keep that bound executable alongside the public task-file
# copy so the strict pair harness can mount it independently of the solution.
event_worker=(case/'task/task_file/scripts/event_worker.py').read_text(encoding='utf-8')
(case/'task/upstream_solutions/event_worker.py').write_text(event_worker,encoding='utf-8')
# The worker is outside the participant image.  The workspace runtime resolves
# /app paths against task/ on the host, then stages it only for its owning role.
private_case=yaml.safe_load((case/'private/private_case.yaml').read_text(encoding='utf-8'))
private_case['workstream_bindings']['requirement_worker_04']['event_assets']=['/app/upstream_solutions/event_worker.py']
(case/'private/private_case.yaml').write_text(yaml.safe_dump(private_case,sort_keys=False),encoding='utf-8')
lock={
 'benchmark':'MultiAgentBench','locked':True,'production_case_path':'.','source_task_id':'bargaining:011',
 'source_files':['private/source_manifests/01-native_case.json','private/source_manifests/03-official_task.json','private/source_manifests/04-native_config.yaml'],
 'source_file_sha256':{}
}
for rel in lock['source_files']:
 import hashlib
 lock['source_file_sha256'][rel]=hashlib.sha256((case/rel).read_bytes()).hexdigest()
(case/'private/source_lock.json').write_text(__import__('json').dumps(lock,indent=2,sort_keys=True)+'\n',encoding='utf-8')
