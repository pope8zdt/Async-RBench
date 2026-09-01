from __future__ import annotations
DOMAIN='bargaining:029'
EVENT_SCHEMA='freight_finish_counter_supersedes_quote'
AUTHORITY={'current_counter': {'unit_price': 25.49, 'finish': 'heavy_duty_rustic', 'delivery_days': 7}, 'supersedes': {'unit_price': 22.0, 'freight': 'unverified'}}
CANONICAL_CHOICE={'unit_price': 25.49, 'finish': 'heavy_duty_rustic', 'delivery_days': 7}
PROVISIONAL={'unit_price': 22.0, 'freight': 'unverified'}
class TurtleDoorStopNegotiation:
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
