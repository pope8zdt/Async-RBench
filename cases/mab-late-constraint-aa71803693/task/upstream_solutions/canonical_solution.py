DOMAIN='elephant_baby_shower_bargaining'
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
