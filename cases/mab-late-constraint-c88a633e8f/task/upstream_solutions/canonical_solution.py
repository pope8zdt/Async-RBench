DOMAIN='rhapsody_bag_bargaining'
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
