from __future__ import annotations
DOMAIN='bargaining:010'; EVENT_SCHEMA='quality_evidence_and_contract_tier_delivered'; AUTHORITY={'quality_checks': ['write_on', 'transparency'], 'sample_rolls': 20, 'unit_price': 14.75, 'term_months': 12, 'quarterly_rolls': 100}; CANONICAL_CHOICE={'sample_rolls': 20, 'quality_approved': True, 'unit_price': 14.75, 'term_months': 12, 'quarterly_rolls': 100}; STALE_PLAN='unrated_product_commitment'
class OHPFilmNegotiation:
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
