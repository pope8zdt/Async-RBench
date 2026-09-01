from __future__ import annotations
DOMAIN='bargaining:037'; EVENT_SCHEMA='sock_assortment_scope_clarified'; AUTHORITY={'power_requirement': 'none', 'material': 'cotton_blend', 'patterns': 'assorted_bear_cat_fox', 'minimum_batch': 100, 'unit_price': 7.49, 'lead_time_days': 8}; CANONICAL_CHOICE={'power_requirement': 'none', 'material': 'cotton_blend', 'patterns': 'assorted_bear_cat_fox', 'minimum_batch': 100, 'unit_price': 7.49, 'lead_time_days': 8}; PROVISIONAL={'minimum_batch': 20, 'unit_price': 7.0, 'condition_focus': 'battery'}
class AnimalSockNegotiation:
    def __init__(self): self.revision=0; self.history=[]; self.authority=None; self.final=None
    def offer(self,terms): self.revision+=1; self.history.append({'revision':self.revision,'action':'offer','terms':dict(terms)}); return self.revision
    def apply_authority(self,base_revision,payload):
        if base_revision!=self.revision: raise RuntimeError('stale authority')
        if payload!=AUTHORITY: raise ValueError('unauthorized authority')
        self.authority=dict(payload); self.revision+=1; self.history.append({'revision':self.revision,'action':'authority','terms':dict(payload)}); return self.revision
    def counter(self,base_revision,terms):
        if base_revision!=self.revision or self.authority is None: raise RuntimeError('authority not current')
        if terms!=CANONICAL_CHOICE: raise ValueError('wrong terms')
        self.revision+=1; self.history.append({'revision':self.revision,'action':'counter','terms':dict(terms)}); return self.revision
    def finalize(self,base_revision):
        if base_revision!=self.revision or self.history[-1]['terms']!=CANONICAL_CHOICE: raise RuntimeError('cannot finalize')
        self.revision+=1; self.history.append({'revision':self.revision,'action':'finalize','terms':dict(CANONICAL_CHOICE)}); self.final={'status':'agreement','terms':dict(CANONICAL_CHOICE)}; return self.final
    def audit(self): return {'chronological':[x['revision'] for x in self.history]==list(range(1,len(self.history)+1)),'actions':[x['action'] for x in self.history],'provisional_excluded':bool(self.final and self.final['terms']!=PROVISIONAL),'final':self.final}
