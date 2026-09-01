from __future__ import annotations
DOMAIN='bargaining:030'
EVENT_SCHEMA='product_quality_scope_clarified'
AUTHORITY={'power_requirement': 'none', 'material': 'velvet_ring_holder', 'unit_price': 17.49, 'minimum_batch': 60}
CANONICAL_CHOICE={'power_requirement': 'none', 'material': 'velvet_ring_holder', 'unit_price': 17.49, 'minimum_batch': 60}
PROVISIONAL={'unit_price': 15.0, 'condition_focus': 'battery'}
class JewelryOrganizerNegotiation:
    def __init__(self):
        self.revision=0; self.history=[]; self.authority=None; self.final=None
    def offer(self,terms):
        self.revision+=1; self.history.append({"revision":self.revision,"action":"offer","terms":dict(terms)}); return self.revision
    def apply_authority(self,base_revision,payload):
        if base_revision!=self.revision: raise RuntimeError("stale authority")
        if payload!=AUTHORITY: raise ValueError("unauthorized authority")
        self.revision+=1; self.authority=dict(payload); self.history.append({"revision":self.revision,"action":"authority","terms":dict(payload)}); return self.revision
    def counter(self,base_revision,terms):
        if base_revision!=self.revision or self.authority is None: raise RuntimeError("authority not current")
        if terms!=CANONICAL_CHOICE: raise ValueError("wrong terms")
        self.revision+=1; self.history.append({"revision":self.revision,"action":"counter","terms":dict(terms)}); return self.revision
    def finalize(self,base_revision):
        if base_revision!=self.revision or self.history[-1]["terms"]!=CANONICAL_CHOICE: raise RuntimeError("cannot finalize")
        self.revision+=1; self.history.append({"revision":self.revision,"action":"finalize","terms":dict(CANONICAL_CHOICE)}); self.final={"status":"agreement","terms":dict(CANONICAL_CHOICE)}; return self.final
    def audit(self):
        return {"chronological":[x["revision"] for x in self.history]==list(range(1,len(self.history)+1)),"actions":[x["action"] for x in self.history],"provisional_excluded":self.final is not None and self.final["terms"]!=PROVISIONAL,"final":self.final}
