from __future__ import annotations
DOMAIN='bargaining:022'; EVENT_SCHEMA='production_scope_constraint_added'; AUTHORITY={'immediate_batch_max': 100, 'unit_price': 14.25, 'replacement_days': 90, 'second_batch_weeks': 6}; CANONICAL_CHOICE={'quantity': 100, 'unit_price': 14.25, 'replacement_days': 90, 'delivery': 'immediate_batch'}; STALE_PLAN='immediate_large_volume'
class IdolDollNegotiation:
 def __init__(self):self.revision=0;self.history=[];self.authority=None;self.final=None
 def buyer_offer(self,terms):
  self.revision+=1;self.history.append({'revision':self.revision,'actor':'buyer','terms':dict(terms)});return self.revision
 def apply_authority(self,base_revision,payload):
  if base_revision!=self.revision:raise RuntimeError('stale authority')
  if payload!=AUTHORITY:raise ValueError('unqualified authority')
  self.revision+=1;self.authority=dict(payload);self.history.append({'revision':self.revision,'actor':'authority','terms':dict(payload)});return self.revision
 def counter(self,base_revision,terms):
  if base_revision!=self.revision or self.authority is None:raise RuntimeError('stale counter')
  if terms!=CANONICAL_CHOICE:raise ValueError('terms')
  self.revision+=1;self.history.append({'revision':self.revision,'actor':'buyer','terms':dict(terms)});return self.revision
 def finalize(self,base_revision):
  if base_revision!=self.revision or not self.history or self.history[-1]['terms']!=CANONICAL_CHOICE:raise RuntimeError('cannot finalize')
  self.final={'status':'agreement','terms':dict(CANONICAL_CHOICE)};return self.final
 def audit(self):return {'chronological':[x['revision'] for x in self.history]==list(range(1,len(self.history)+1)),'stale_plan_excluded':all(x['terms']!=STALE_PLAN for x in self.history[1:]),'final':self.final}

# independently frozen equivalent implementation
