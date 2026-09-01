from __future__ import annotations
DOMAIN='bargaining:046';EVENT_SCHEMA='current_genuine_part_delivery_counter';AUTHORITY={'current_counter': {'unit_price': 10.5, 'part_number': '1266657', 'genuine_kohler': True, 'delivery_days': 2, 'warranty_months': 12}, 'supersedes': {'unit_price': 9.0, 'part_authenticity': 'unverified'}};CANONICAL_CHOICE={'unit_price': 10.5, 'part_number': '1266657', 'genuine_kohler': True, 'delivery_days': 2, 'warranty_months': 12};PROVISIONAL={'unit_price': 9.0, 'part_authenticity': 'unverified'}
class KohlerValveKitNegotiation:
    def __init__(self):self.revision=0;self.history=[];self.authority=None;self.final=None
    def _record(self,action,terms):
        self.revision+=1;self.history.append({'revision':self.revision,'action':action,'terms':dict(terms)});return self.revision
    def offer(self,terms):return self._record('offer',terms)
    def apply_authority(self,base_revision,payload):
        if base_revision!=self.revision:raise RuntimeError('stale authority')
        if payload!=AUTHORITY:raise ValueError('unauthorized authority')
        self.authority=dict(payload);return self._record('authority',payload)
    def counter(self,base_revision,terms):
        if base_revision!=self.revision or self.authority is None:raise RuntimeError('authority not current')
        if terms!=CANONICAL_CHOICE:raise ValueError('wrong terms')
        return self._record('counter',terms)
    def finalize(self,base_revision):
        if base_revision!=self.revision or self.history[-1]['terms']!=CANONICAL_CHOICE:raise RuntimeError('cannot finalize')
        self._record('finalize',CANONICAL_CHOICE);self.final={'status':'agreement','terms':dict(CANONICAL_CHOICE)};return self.final
    def audit(self):return {'chronological':[x['revision'] for x in self.history]==list(range(1,len(self.history)+1)),'actions':[x['action'] for x in self.history],'provisional_excluded':bool(self.final and self.final['terms']!=PROVISIONAL),'final':self.final}
