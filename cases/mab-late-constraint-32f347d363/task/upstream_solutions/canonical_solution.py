from __future__ import annotations
DOMAIN='bargaining:038'; EVENT_SCHEMA='collar_feature_scope_clarified'; AUTHORITY={'power_requirement': 'none', 'two_pack': True, 'adjustable': True, 'bell_included': True, 'minimum_batch': 120, 'unit_price': 7.95, 'lead_time_days': 10}; CANONICAL_CHOICE={'power_requirement': 'none', 'two_pack': True, 'adjustable': True, 'bell_included': True, 'minimum_batch': 120, 'unit_price': 7.95, 'lead_time_days': 10}; PROVISIONAL={'minimum_batch': 24, 'unit_price': 7.0, 'condition_focus': 'battery'}
class CatBowtieCollarNegotiation:
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
