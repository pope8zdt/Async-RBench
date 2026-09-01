from __future__ import annotations
DOMAIN='bargaining:028'
EVENT_SCHEMA='size_run_capacity_constraint_added'
AUTHORITY={'minimum_batch': 120, 'unit_price': 16.5, 'size_run': 'assorted_youth', 'defect_replacement_days': 30}
CANONICAL_CHOICE={'minimum_batch': 120, 'unit_price': 16.5, 'size_run': 'assorted_youth', 'defect_replacement_days': 30}
PROVISIONAL={'minimum_batch': 40, 'unit_price': 14.0, 'size_run': 'unspecified'}
class YouthShirtProductionNegotiation:
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
