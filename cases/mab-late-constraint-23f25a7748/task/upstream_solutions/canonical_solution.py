DOMAIN='merv13_air_filter_bargaining'
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
