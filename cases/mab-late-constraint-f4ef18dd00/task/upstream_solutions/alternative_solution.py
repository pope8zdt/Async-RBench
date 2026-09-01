from __future__ import annotations
DOMAIN='bargaining:032'; EVENT_SCHEMA='production_delivery_slot_confirmed'; AUTHORITY={'unit_price': 21.95, 'production_slot': 'confirmed', 'delivery_days': 4, 'warranty_months': 12, 'logistics': 'consolidated'}; CANONICAL_CHOICE={'unit_price': 21.95, 'production_slot': 'confirmed', 'delivery_days': 4, 'warranty_months': 12, 'logistics': 'consolidated'}; PROVISIONAL={'unit_price': 19.0, 'delivery_days': 'pending'}
class PneumaticChiselNegotiation:
    def __init__(self): self.revision=0; self.history=[]; self.authority=None; self.final=None
    def _record(self,action,terms):
        self.revision+=1; self.history.append({'revision':self.revision,'action':action,'terms':dict(terms)}); return self.revision
    def offer(self,terms): return self._record('offer',terms)
    def apply_authority(self,base_revision,payload):
        if base_revision!=self.revision: raise RuntimeError('stale authority')
        if payload!=AUTHORITY: raise ValueError('unauthorized authority')
        self.authority=dict(payload); return self._record('authority',payload)
    def counter(self,base_revision,terms):
        if base_revision!=self.revision or self.authority is None: raise RuntimeError('authority not current')
        if terms!=CANONICAL_CHOICE: raise ValueError('wrong terms')
        return self._record('counter',terms)
    def finalize(self,base_revision):
        if base_revision!=self.revision or self.history[-1]['terms']!=CANONICAL_CHOICE: raise RuntimeError('cannot finalize')
        self._record('finalize',CANONICAL_CHOICE); self.final={'status':'agreement','terms':dict(CANONICAL_CHOICE)}; return self.final
    def audit(self): return {'chronological':[x['revision'] for x in self.history]==list(range(1,len(self.history)+1)),'actions':[x['action'] for x in self.history],'provisional_excluded':bool(self.final and self.final['terms']!=PROVISIONAL),'final':self.final}
