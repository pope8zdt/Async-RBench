from __future__ import annotations
DOMAIN='bargaining:030'
EVENT_SCHEMA='product_quality_scope_clarified'
AUTHORITY={'power_requirement': 'none', 'material': 'velvet_ring_holder', 'unit_price': 17.49, 'minimum_batch': 60}
CANONICAL_CHOICE={'power_requirement': 'none', 'material': 'velvet_ring_holder', 'unit_price': 17.49, 'minimum_batch': 60}
PROVISIONAL={'unit_price': 15.0, 'condition_focus': 'battery'}
class JewelryOrganizerNegotiation:
    def __init__(self):
        self.revision=0; self.history=list(); self.authority=None; self.final=None
    def _record(self,action,terms):
        self.revision+=1; self.history.append({"revision":self.revision,"action":action,"terms":dict(terms)}); return self.revision
    def offer(self,terms): return self._record("offer",terms)
    def apply_authority(self,base_revision,payload):
        if (base_revision,payload)!=(self.revision,AUTHORITY):
            if base_revision!=self.revision: raise RuntimeError("stale authority")
            raise ValueError("unauthorized authority")
        self.authority=dict(payload); return self._record("authority",payload)
    def counter(self,base_revision,terms):
        if base_revision!=self.revision or self.authority is None: raise RuntimeError("authority not current")
        if dict(terms)!=CANONICAL_CHOICE: raise ValueError("wrong terms")
        return self._record("counter",terms)
    def finalize(self,base_revision):
        if base_revision!=self.revision or self.history[-1]["terms"]!=CANONICAL_CHOICE: raise RuntimeError("cannot finalize")
        self._record("finalize",CANONICAL_CHOICE); self.final={"terms":dict(CANONICAL_CHOICE),"status":"agreement"}; return self.final
    def audit(self):
        revisions=[row["revision"] for row in self.history]
        return {"chronological":revisions==list(range(1,len(revisions)+1)),"actions":[row["action"] for row in self.history],"provisional_excluded":bool(self.final and self.final["terms"]!=PROVISIONAL),"final":self.final}
